import datetime
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional
import pandas as pd
from django.db.models import Sum
from dateutil.relativedelta import relativedelta
from ledger.models import Ledger
from custom.classes import Ikea
from report.models import SalesRegisterReport
from ledger.logic import LedgerType

@dataclass
class MOC:
    month: int
    year: int

    @property
    def start_date(self) -> datetime.date:
        # 21st of previous month
        prev_month = datetime.date(self.year, self.month, 1) - relativedelta(months=1)
        return prev_month.replace(day=21)

    @property
    def end_date(self) -> datetime.date:
        # 20th of current month
        return datetime.date(self.year, self.month, 20)

    def __str__(self):
        return f"{self.month:02d}/{self.year}"
    
    def __hash__(self):
        return hash((self.month, self.year))
    
    @staticmethod
    def from_str(moc_str: str) -> 'MOC':
        # Expects "MM/YYYY" or "MMYYYY"
        if "/" in moc_str:
            month, year = map(int, moc_str.split("/"))
        else:
            month = int(moc_str[:2])
            year = int(moc_str[2:])
        return MOC(month, year)

    @staticmethod
    def get_moc_for_date(d: datetime.date) -> 'MOC':
        if d.day >= 21:
            # Next month
            nm = d + relativedelta(months=1)
            return MOC(nm.month, nm.year)
        else:
            # Current month
            return MOC(d.month, d.year)

    @staticmethod
    def get_mocs_in_range(fromd: datetime.date, tod: datetime.date) -> List['MOC']:
        start_moc = MOC.get_moc_for_date(fromd)
        end_moc = MOC.get_moc_for_date(tod)
        
        mocs = []
        current = datetime.date(start_moc.year, start_moc.month, 1)
        end_date = datetime.date(end_moc.year, end_moc.month, 1)
        
        while current <= end_date:
            mocs.append(MOC(current.month, current.year))
            current += relativedelta(months=1)
            
        return mocs



import pickle
import os

class VerificationDataLoader:
    def __init__(self, ikea_client: Ikea):
        self.ikea = ikea_client
        self.claim_status: Optional[pd.DataFrame] = None
        self.damage_proposals: Optional[pd.DataFrame] = None
        self.damage_debit_notes: Optional[pd.DataFrame] = None

    def get_cache_path(self, fromd, tod):
         # store in .cache dir
         os.makedirs(".cache", exist_ok=True)
         # Ikea class stores company_id in self.company_id?
         # Checked custom/classes.py: __init__(self, company_id). It sets self.company_id = company_id
         return f".cache/verification_data_{self.ikea.user.username}_{fromd}_{tod}.pkl"

    def download_all(self, fromd: datetime.date, tod: datetime.date):
        cache_path = self.get_cache_path(fromd, tod)
        if os.path.exists(cache_path):
            print(f"Loading from cache: {cache_path}")
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
                self.claim_status = data.get('claim_status')
                self.damage_proposals = data.get('damage_proposals')
                self.damage_debit_notes = data.get('damage_debit_notes')
                self.ushop_ledger_salesreturn = data.get('ushop_ledger_salesreturn')
                self.ushop_ledger_sales = data.get('ushop_ledger_sales')
            return

        print("Downloading Claim Status...")
        # self.claim_status = self.ikea.claim_status(fromd, tod)
        print("Downloading Damage Proposals...")
        # self.damage_proposals = self.ikea.raw_damage_proposal(fromd, tod, sheet_name="PROPOSAL DETAILS")
        print("Downloading Damage Debit Notes...")
        # self.damage_debit_notes = self.ikea.damage_debitnote(fromd, tod)
        print("Downloading UShop Ledger...")
        ushop_bytesio = self.ikea.ushop_ledger(fromd, tod)
        self.ushop_ledger_salesreturn = pd.read_excel(ushop_bytesio,sheet_name="Sales Return Ushop Ledger")
        self.ushop_ledger_sales = pd.read_excel(ushop_bytesio,sheet_name="Ushop Ledger")
        
        # Save to cache
        with open(cache_path, 'wb') as f:
            pickle.dump({
                'claim_status': self.claim_status,
                'damage_proposals': self.damage_proposals,
                'damage_debit_notes': self.damage_debit_notes,
                'ushop_ledger_salesreturn': self.ushop_ledger_salesreturn,
                'ushop_ledger_sales': self.ushop_ledger_sales
            }, f)

class BaseVerification:
    source_total_col: str = "source_value"
    ledger_total_col: str = "ledger_value"
    only_ledger = False

    def __init__(self, company_id: int, fromd: datetime.date, tod: datetime.date, loader: VerificationDataLoader):
        self.company_id = company_id
        self.fromd = fromd
        self.tod = tod
        self.loader = loader
        self.qs = Ledger.objects.filter(company_id=company_id, date__range=[fromd, tod])

    def fetch_source_data(self) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_ledger_data(self) -> pd.DataFrame:
        raise NotImplementedError

    def verify(self) -> pd.DataFrame:
        df_ledger = self.fetch_ledger_data()
        if self.only_ledger:
            return df_ledger
        df_source = self.fetch_source_data()
        combined = pd.merge(df_source, df_ledger, left_index=True, right_index=True, how='left').fillna(0)
        combined['diff'] = (combined[self.source_total_col] - combined[self.ledger_total_col])
        combined = combined.round()
        return combined

class ClaimsVerification(BaseVerification):
    source_total_col = "total_paid"
    ledger_total_col = "total_received"

    def fetch_source_data(self) -> pd.DataFrame:
        ushop_reversal = self.loader.ushop_ledger_salesreturn
        ushop_reversal["moc"] = ushop_reversal["REDEEM REQ DATE"].apply(lambda x: str(MOC.get_moc_for_date(x)))
        ushop_reversal = ushop_reversal.groupby("moc")["REVERSAL_VALUES"].sum().to_dict()

        mocs = MOC.get_mocs_in_range(self.fromd, self.tod)
        rows = []
        for moc in mocs:
            # SalesRegisterReport is stored day-wise. Sum for the MOC range.
            qs = SalesRegisterReport.objects.filter(
                date__gte=moc.start_date,
                date__lte=moc.end_date,
                company_id=self.company_id 
            )
            # Sum columns
            agg = qs.aggregate(
                sch_dic=Sum('schdisc'),
                btpr=Sum('btpr'),
                output_vat=Sum('outpyt'),  
                ushop=Sum('ushop'),
                pecom=Sum('pecom'),
                shikhar=Sum('shikhar_scheme'),
            )
            agg["ushop_reversal"] = -ushop_reversal.get(str(moc), 0)
            data = {k: int(v or 0) for k, v in agg.items()}
            data[self.source_total_col] = int(sum(data.values()))
            data['moc'] = str(moc)
            rows.append(data)
        
        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index('moc', inplace=True)
        return df

    def fetch_ledger_data(self) -> pd.DataFrame:
        # 1. Claims
        claims = self.loader.claim_status
        x = claims[claims["CLAIM TYPE DESCRIPTION"].isin(["Ushop","SHIKHAR NONCOUPON"])]

        ushop = self.loader.ushop_ledger_sales
        ushop["moc"] = ushop["REDEEM REQ DATE"].apply(lambda x: str(MOC.get_moc_for_date(x)))
        ushop = ushop[ushop["moc"] == "06/2025"]
        ushop = ushop.groupby("ACTIVITY CODE")["ADJUSTED VALUE"].sum().to_dict()
        print(sum(ushop.values()))

        ushop_reversal = self.loader.ushop_ledger_salesreturn
        ushop_reversal["moc"] = ushop_reversal["REDEEM REQ DATE"].apply(lambda x: str(MOC.get_moc_for_date(x)))
        ushop_reversal = ushop_reversal[ushop_reversal["moc"] == "06/2025"]
        print(ushop_reversal[["BILL NUMBER","REDEEM REQ DATE","REVERSAL_POINTS"]])
        ushop_reversal = (-ushop_reversal.groupby("ACTIVITY CODE")["REVERSAL_VALUES"].sum()).to_dict()
        ushop = {str(k).split(".")[0]: ushop.get(k, 0) + ushop_reversal.get(k, 0) for k in set(ushop.keys()) | set(ushop_reversal.keys())}
        print(sum(ushop.values()))

        activites_to_type = claims.groupby("ACTIVITY CODE")["CLAIM TYPE DESCRIPTION"].first().to_dict()
        
        claims = claims[claims["CLAIM TYPE DESCRIPTION"] == "OTHERS-CLAIM"]
        other_claims_activites = claims["ACTIVITY CODE"].unique().tolist()
        claims_qs = self.qs.filter(type__in = [LedgerType.CLAIMS,LedgerType.USHOP_SI]).exclude(ref__in = other_claims_activites)
        df = pd.DataFrame(list(claims_qs.values('type','ref','moc','amt')))
        
        # moc10 = df[df['moc'] == '08/2025']
        # moc10["types"] = moc10['ref'].replace(activites_to_type)
        # # y = moc10.groupby("types")["amt"].sum().to_dict()
        # y = moc10.groupby("ref")["amt"].sum().to_dict()
        y = self.loader.claim_status
        y = y[y["CLAIM MOC REF"] == "06/2025"]
        y = y[
            ((y["CLAIM TYPE DESCRIPTION"] == "SHIKHAR NONCOUPON"))
            | (y["CLAIM TYPE DESCRIPTION"] == "Ushop")
        ]
        y = y.groupby("ACTIVITY CODE")["DN/SI AMOUNT"].sum().to_dict()
        for code in set(ushop.keys()) | set(y.keys()): 
            if abs(y.get(code,0) - ushop.get(code,0)) > 10:
                print(code,ushop.get(code,0),y.get(code,0), y.get(code,0) - ushop.get(code,0))


        if df.empty:
            return pd.DataFrame(columns=[self.ledger_total_col])
        df = df.pivot_table(index='moc', columns='type', values='amt', aggfunc='sum', fill_value=0)
        df.columns.name = None
        df.index.name = None
        if LedgerType.USHOP_SI in df.columns:
            df[LedgerType.USHOP_SI] = (df[LedgerType.USHOP_SI] / 1.16).round()
        df[self.ledger_total_col] = df[LedgerType.CLAIMS] + df[LedgerType.USHOP_SI]
        return df

class ShortageVerification(BaseVerification):
    source_total_col = "proposal_value"
    ledger_total_col = "shortage_received"

    def fetch_source_data(self) -> pd.DataFrame:
        df = self.loader.damage_proposals
        if df is None or df.empty:
             return pd.DataFrame(columns=[self.source_total_col])
        df = df.dropna(subset=['PROP REF NO'])
        df = df[df['PROP REF NO'].str.startswith('SHT')]
        df = df[df["PROP DATE"].dt.date >= self.fromd]
        result = df.groupby('PROP REF NO',sort=False)['PROPOSED  VALUE'].sum().rename(self.source_total_col)
        return result.to_frame()

    def fetch_ledger_data(self) -> pd.DataFrame:
        qs = self.qs.filter(type=LedgerType.SHORTAGE)
        df = pd.DataFrame(list(qs.values('ref', 'amt')))
        if df.empty:
            return pd.DataFrame(columns=[self.ledger_total_col])
        result = df.groupby('ref')['amt'].sum().rename(self.ledger_total_col)
        return result.to_frame()

class CDTStats(BaseVerification):
    source_total_col = "" 
    ledger_total_col = "total_cdt" 
    only_ledger = True

    def fetch_source_data(self) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_ledger_data(self) -> pd.DataFrame:
        qs = self.qs.filter(type__in=[LedgerType.CDTSL,LedgerType.CDTSR])
        df = pd.DataFrame(list(qs.values('type','moc', 'amt')))
        if df.empty:
            return pd.DataFrame(columns=[self.ledger_total_col])
        df = df.pivot_table(index='moc', columns='type', values='amt', aggfunc='sum', fill_value=0)
        df.columns.name = None
        df.index.name = None
        df[self.ledger_total_col] = df[LedgerType.CDTSL] + df[LedgerType.CDTSR]
        return df

class DamageVerification(BaseVerification):
    source_total_col = "damage_sent"
    ledger_total_col = "damage_received"

    def fetch_source_data(self) -> pd.DataFrame:
        df = self.loader.damage_debit_notes
        if df is None or df.empty:
            return pd.DataFrame(columns=[self.source_total_col])
        
        filtered = df[df["PROPOSAL NO"].notna()]
        result = filtered.groupby('REFR NO',sort=False).agg({
            'DEBIT NOTE DATE' : 'first',
            'PROPOSAL NO': 'first',
            'TOTAL AMOUNT': 'sum',  
        }).rename(columns={'TOTAL AMOUNT': self.source_total_col,'DEBIT NOTE DATE':'date'})
        return result

    def fetch_ledger_data(self) -> pd.DataFrame:
        qs = self.qs.filter(type=LedgerType.DAMAGE)
        df = pd.DataFrame(list(qs.values('ref', 'amt')))
        if df.empty:
            return pd.DataFrame(columns=[self.ledger_total_col])
        result = df.groupby('ref')['amt'].sum().rename(self.ledger_total_col)
        return result.to_frame()

class NMSMVerification(BaseVerification):
    source_total_col = "nmsm_sent"
    ledger_total_col = "nmsm_received"

    def fetch_source_data(self) -> pd.DataFrame:
        df = self.loader.damage_debit_notes
        if df is None or df.empty:
            return pd.DataFrame(columns=[self.source_total_col])
        
        filtered = df[df['PROPOSAL NO'].isna()]
        result = filtered.groupby('DEBIT NOTE NO',sort=False).agg({
            'DEBIT NOTE DATE' : 'first',
            'MATERIAL/ACTIVITY DESC': 'first',
            'TOTAL AMOUNT': 'sum',  
        }).rename(columns={'TOTAL AMOUNT': self.source_total_col,'DEBIT NOTE DATE':'Date','MATERIAL/ACTIVITY DESC':'Product'})
        return result

    def fetch_ledger_data(self) -> pd.DataFrame:
        qs = self.qs.filter(type=LedgerType.DSE,ref__startswith="DN")
        df = pd.DataFrame(list(qs.values('ref', 'amt')))
        if df.empty:
            return pd.DataFrame(columns=[self.ledger_total_col])
        result = df.groupby('ref')['amt'].sum().rename(self.ledger_total_col)
        return result.to_frame()
