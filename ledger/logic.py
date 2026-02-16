import enum
import pandas as pd
from core.models import Company
from ledger.models import Ledger
import datetime
import os

class LedgerType(str,enum.Enum):
    TDS = "tds"
    NMSM = "nmsm"
    DSE = "dse"
    CDTSR = "cdtsr"
    USHOP_SI = "ushop_si"
    DAMAGE = "damage"
    SHORTAGE = "shortage"
    PURCHASE = "purchase"
    SOFTWARE_CHARGES = "software_charges"
    CDTSL = "cdtsl"
    CLAIMS = "claims"
    CHEQUES = "cheques"
    OTHERS = "others"

def parse_row(row):
    doc_type = row["Document Details"]
    remarks = row["Remarks"]
    remarks2 = row["Remarks2"]
    refernce = row["Reference"]
    text = row["Text"]
    if doc_type == "AR TDS Receivable": 
        return Ledger(type=LedgerType.TDS,ref=text.split("-")[1])
    elif doc_type == "Credit invoice":
        if remarks :
            return Ledger(type=LedgerType.NMSM,ref=remarks)
        else : 
            return Ledger(type=LedgerType.DSE,ref=remarks2)
    elif doc_type == "G/L account document":
        activity = text.split("-")[0]
        return Ledger(type=LedgerType.CDTSR if activity == "CDTSR" else LedgerType.USHOP_SI,ref=activity,moc=remarks2)
    elif doc_type == "GT Rtn Bill No Tax":
        return Ledger(type=LedgerType.DAMAGE,ref=remarks)
    elif doc_type == "HLLDirDisRtnBilling":
        return Ledger(type=LedgerType.DSE)
    elif doc_type in ["HUL New Manual Bill","Invoice"]:
        return Ledger(type=LedgerType.PURCHASE,ref=refernce) 
    elif doc_type == "HUL Services Debit":
        return Ledger(type=LedgerType.SOFTWARE_CHARGES,ref=refernce)
    elif doc_type == "Opening Balance": 
        return None
    elif doc_type == "Post-tax claim":
        type = None
        if remarks == "CDTSL": type = LedgerType.CDTSL
        elif remarks.startswith("SHT_HUL"): type = LedgerType.SHORTAGE
        else: type = LedgerType.CLAIMS
        return Ledger(type=type,moc=remarks2,ref=remarks)
    elif doc_type == "Rcpt doc - Cheques":
        return Ledger(type=LedgerType.CHEQUES,ref=refernce)
    else :
        return Ledger(type=LedgerType.OTHERS,ref=refernce)
         
def import_ledger_data(company, file_path):
    """
    Imports ledger data from a file (CSV/Excel) for a specific company.
    Returns a tuple: (success: bool, message: str)
    """
    if not os.path.exists(file_path):
        return False, f'File "{file_path}" does not exist'

    try:
        dtypes = {
            "Document Details": str,
            "Doc. No": str,
            "Debit (Rs).": float,
            "Credit (Rs)": float,
            "Remarks": str,
            "Remarks2": str,
            "Text": str
        }
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path,dtype=dtypes)
        else:
            df = pd.read_excel(file_path,dtype=dtypes)
        
        # Map columns
        required_columns = ['Date', 'Document Details', 'Doc. No', 'Debit (Rs).', 'Credit (Rs)','Remarks','Remarks2','Text']
        if not all(col in df.columns for col in required_columns):
             print( set(required_columns) - set(df.columns.tolist()) )
             return False, f'Missing columns. Required: {required_columns}. Found: {df.columns.tolist()}'

        fillna_columns = ['Remarks','Remarks2','Text']
        df[fillna_columns] = df[fillna_columns].fillna('')

        # Parse dates
        df = df[df["Adj. Amt. (Rs.)"] == 0]
        df['Date'] = pd.to_datetime(df['Date'],format = "%d/%m/%y")
        
        if df.empty:
            return False, 'File is empty'

        min_date = df['Date'].min().date()
        max_date = df['Date'].max().date()

        # Delete existing entries in range
        deleted_count, _ = Ledger.objects.filter(
            company=company,
            date__range=[min_date, max_date]
        ).delete()

        # Prepare new entries
        ledger_entries = []
        for _, row in df.iterrows():
            debit = float(row['Debit (Rs).']) if pd.notnull(row['Debit (Rs).']) else 0.0
            credit = float(row['Credit (Rs)']) if pd.notnull(row['Credit (Rs)']) else 0.0
            amt = credit - debit
            ledger:Ledger|None = parse_row(row)
            if not ledger:
                continue

            ledger.company = company
            ledger.date = row['Date'].date()
            ledger.amt=amt
            ledger.doc_no = row['Doc. No']
            if ledger.moc :
                ledger.moc = datetime.datetime.strptime(ledger.moc, "%Y-%m-%d %H:%M:%S").strftime("%m/%Y")
            ledger_entries.append(ledger)
        
        Ledger.objects.bulk_create(ledger_entries)
        return True, f'Successfully imported {len(ledger_entries)} entries. Deleted {deleted_count} existing entries.'

    except Exception as e:
        return False, f'Error importing ledger: {str(e)}'
