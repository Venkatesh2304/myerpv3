import functools
from requests.adapters import HTTPAdapter
import  urllib.parse
from urllib3 import Retry
from requests import session
import calendar
from requests import get
from collections import defaultdict
from typing import Literal
import copy
import datetime
from io import BytesIO
import warnings
import dateutil.relativedelta as relativedelta
import json
import uuid
import random
import numpy as np
import pandas as pd 
import base64
from .std import moc_range
from pathlib import Path
import zipfile
from dateutil.parser import parse as date_parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
from pathlib import Path    
from urllib.parse import parse_qsl, urljoin
import hashlib
import json
import os
from io import StringIO
from .curl import get_curl , curl_replace 
from .Session import Session,StatusCodeError
from bs4 import BeautifulSoup
from PyPDF2 import PdfMerger
from urllib.parse import urlencode
import requests
from PyPDF2 import PdfReader
import os

warnings.filterwarnings("ignore", category=UserWarning, module=re.escape('openpyxl.styles.stylesheet'))



def ikea_screen(screen_name: str):
    
    def ikea_screen_remove(self,screen_name: str):
        files = {
            'strJsonParams': (None, '{"screenName":"' + screen_name + '"}'),
        }
        res = self.post(
            "/rsunify/app/ikeaCommonUtilController/removeScreenNameFromSession",
            files=files,
        )
        return res 

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            data = {"screenName": screen_name, "pbayoutUpdate": "1","enfSyncFlag": "0"}
            for i in range(2) :
                screen = self.post("/rsunify/app/ikeaCommonUtilController/updateScreenNameIntoSession", data={
                    'strJsonParams': urllib.parse.quote(json.dumps(data)),
                }).json()
                if screen["status"] == "SUCCESS": 
                    break
                #Something is not logged out correctly
                print(f"Update screen status not success, retrying after removing {screen['message']}")
                ikea_screen_remove(self,screen["message"])
            print("Updated Screen : ",screen_name)
            
            try:
                return func(self, *args, **kwargs)
            finally:
                try:
                    ikea_screen_remove(self,screen_name)        
                    print("Removed screen : ",screen_name)
                except Exception as e:
                    print(f"Failed to remove screen {screen_name}: {e}")
        
        return wrapper
    
    return decorator

class WrongCredentials(Exception) :
    pass

class IkeaPasswordExpired(WrongCredentials) :
    pass

class IkeaWrongCredentails(WrongCredentials) :
    pass

class ReportFetchError(Exception):
    pass

class ReportParseError(Exception):
    pass

class BaseIkea(Session):       
    key = "ikea"
    load_cookies = True 
    force_base_url = True
    
    IKEA_GENERATE_REPORT_URL = "/rsunify/app/reportsController/generatereport"
    IKEA_DOWNLOAD_REPORT_URL = "/rsunify/app/reportsController/downloadReport?filePath="
    
    def __init__(self,user:str) : 
        super().__init__(user)
        self.headers.update({'accept': 'application/json, text/javascript, */*; q=0.01'})
        self.base_url = self.config["home"]
        self.user_id = None
        if not self.is_logged_in() : 
            raise Exception("Ikea is Not Logged In")
            # self.login()
            # if not self.is_logged_in() : 
            #     raise Exception("Ikea Login Failed")

    def is_logged_in(self) -> bool:
        try : 
            res = self.get("/rsunify/app/billing/getUserId",timeout=15)
            check = "Something went wrong, please try again later" in res.text
            if check : 
                self.logger.error("Login Check : Failed")
                return False
            self.user_id = res.json()["userId"]
            self.logger.info("Login Check : Passed")
            return True 
        except StatusCodeError as e :
            self.logger.error("Login Check : Failed")
            return False 

    def _get_token_from_redis(self):
        import redis
        import uuid
        import time
        import json
        r = redis.Redis(host='localhost', port=6379, db=0)
        req_id = str(uuid.uuid4())
        
        self.logger.info(f"Requesting token from Redis worker (req_id: {req_id})...")
        r.rpush('token_requests', req_id)
        
        start_time = time.time()
        while time.time() - start_time < 120:
            res = r.get(f'token_response:{req_id}')
            if res:
                r.delete(f'token_response:{req_id}')
                data = json.loads(res.decode('utf-8'))
                return data['token']
            time.sleep(1)
            
        raise Exception("Timeout waiting for token from Redis worker. Is the worker running?")

    def login(self) -> None: 
        self.logger.info("Login Initiated")
        self.cookies.clear()
        time_epochs = self._date_epochs()
        token = input("Token : ")
        # token = self._get_token_from_redis()  #Need to get token 
        #Example:token = "0cAFcWeA7NTbAekCLlLHrXkrBFYP7pe0NOiwQHj1CTKAtyWPSaszXPmgxMGbnwUmTwt3sR27ih7pQcfw05IRMXwNaX_QZPX4LIGPVKNPakvAjjcTJzoLZ1jRy4N1czV6u6HhkJe8SwQOz_51qDBek_86LC1MbutZiac05fQkMRn7OkcLA3ThWtNN1F0wKu9Vr2WV3rEOv4CQdCD9X23z5LGM57RzN9Uq4UYKLFoGurYC-XLtSBOJtg_zhX9Plje4otoCs6AyJnqn_oWE2emvWD1fOjtvq062etu34jmByGpr4ZjHpbYZUp5f7UsGzcbCQOf9T3kpphm8FXAtQKRYrEdIn8oRORrYiaSzEaEBndQeQKHjs_dCinwNkoHgEp69eyTN_Cgg811-C2--A27SqrU7MFv_OI2fN4MelJcvb5WJQVG6oAdsmToRQBbaiQALTgTU7w0rSCMQYFQ3IftYg_zs8cvYm4t9BeWfbgFYvOjU7unfOmraINgMpHoAqqwYeSs-r-kue899mSDU3286Bk6hRmZVtFGxpoSk2f6dOc7CIu3CJxRFl7mQqSYa0QdhVVTGhtGm-LwOVHeQ94U8VJVps0BKeAUHeRIrUIcuN1qMspzgldbV8dDVGST5MVVPpnorf08MY4GGd85uXXA4X9zRsVAPG3Ck0QKtn8iBj3go9nd-B-j2zBlqLTwrpWMKnQeVEcxJoxkfXXVagKnqydvtc-MAlgkBZF5zYDDYGnudiRBht6O58F3D7Zz9HK94ppEKHpwzlZL94q6xfKgyoRXTXtne9GQwSPmo3ESVf7gnMj7dVV3uMyStNeWs0GeLEINGS0bKniFk69G41IrlEFApqV6tq-MobRB574wvN68MEberJSpRkZp5BSGc-O3nJakOzxvDjYoQ0jKKHYLUR3jBYntTLjqUUmi2yTtREhaodU86BNFJKX9EKFjQhktepRtqrlre01tkc6sNjm-Pdj2lJ04Yy7ujN8GAjngrSVRPL0phLEDQ_YlOqjxrdAounvoKYgrNhaXYPrK4vlJZ6bOe1VShV6JkYVbjj4_tqoFtp9FOln4iJdbPvEjogXg-qxk2WdBl8QX684mVGyuR-q1w_jD98jDencUlfGkuPBi9ZoFDQ24cCzsBNCTmusTrUnMrBcctvGIbqyHJSZOL99bkVKkoVCG_Jz_ak0yNE05vm0GR8zbe7eBg4LtWoPDin3TXsu2BS5utC_KCiZKRkDXFXjUQRcBfRkqjLOeLx1HxTmglUjELaeUqwzxVJMdMTqEZpRGS7d7XUJEBdVyJCiZKcvspZ8iy0FLW3uR1d6gagjDtFP-Ups7R7yzFrM24IpSIRZ5VrmTRcfX7nMatb6ML6IsAVHwXZNnlvg1WdRWiSzYwnVencJdmG59pmmpT15dBCwsvdiSKjI4Kefy8VZ9-g3wSEk-LMREWoJSKg07Da37H4v_BbHt1xaLZRREf_xrCxS4RJPu8Rh2KEmxpumZfPACStAYZQ_6gbOoVkJN7SIzE6MLPPWZogKn8PI6k80HKC6rohkc7ldgrRVu5w8O9JB0NYupYAV_8FDJWa5PcfwUKmsahQ1GQNU_Q3tCFTeSi44SlSN-D5uDqqp6vqeBVG_jnhAXuIU7bW-AOaT_0UgLIbQQABmmknvn5vMISFJH-jP9meKhSYAqHYmBbcQ3p03CybNhEd0gpjanWSFiHHdPa_J72za5AOj7Dv1xvtXt6C9njvfZGXu7j-5aHprRen_ZL-Y-QLyBVaduEQbYCASZ0zKPZZ4Y6bK0BOS6i8kiLnvqGqxDw2vnia9f91GTWXO1lOnPkJ7-NWvlcVD9WEnsRYSq07N0DdCv7PIOSI3SfRtN0CwFk70nlExvPTp6hHrsOgzyEdLbF9W0jhlqVZF123tfl4oydnCxD9Qopt6UYsFsbJK-rkFuVJDTocxoLBS8-ApM9uVHxv0CQoPLAUgyD0bnHUEbk-h_yFrlonEQeogPYuD-nqi"
        preauth_res_text = self.post("/rsunify/app/user/authentication",data={'userId': self.username , "g-recaptcha-response" : token,
                        'password': self.password, 'dbName': self.config["dbName"], 'datetime': time_epochs , 'diff': -330},headers={"dbName": self.config["dbName"]}).text
        print(preauth_res_text[:30])
        if ("CLOUD_LOGIN_PASSWORD_EXPIRED" == preauth_res_text): 
            raise IkeaPasswordExpired("Ikea Password Expired")
        elif ("<body>" in preauth_res_text) or ("Invalid Password" == preauth_res_text) : 
            raise IkeaWrongCredentails("Ikea Wrong Credentials")
        else : 
            pass 
        response = self.post("/rsunify/app/user/authenSuccess",{"isDefaultPassword":False,"g-recaptcha-response":""})
        print(response.text[:30])
        if response.status_code == 200 : 
            self.logger.info("Logged in successfully")
            self.user.update_cookies(self.cookies)
        else : 
            self.logger.error(f"Login Failed with status code: {response.status_code}")
            raise Exception("Ikea Login Failed")

    def _date_epochs(self) :
        return int((datetime.datetime.now() - datetime.datetime(1970, 1, 1)
                        ).total_seconds() * 1000) - (330*60*1000)
    
    def fetch_durl_content(self, durl: str) -> BytesIO:
        if not durl:
            raise ValueError("Download URL is empty")
        return super().get_buffer(self.IKEA_DOWNLOAD_REPORT_URL + durl)

class IkeaReports(BaseIkea):
    MOC_PAT = r'(":val1":").{7}'

    def fetch_report_bytes(self, key: str, pat: str = "", replaces: tuple = tuple()) -> BytesIO:
        self.logger.debug(f"Fetching report bytes for key: {key}")
        r = get_curl(key)
        if isinstance(r.data, str) :
            r.data = dict(parse_qsl(r.data))
        if "jsonObjWhereClause" in r.data:
            r.data['jsonObjWhereClause'] = curl_replace(pat, replaces, r.data['jsonObjWhereClause'])
            if "jsonObjforheaders" in r.data: del r.data['jsonObjforheaders']
        print(r.data)
        durl = r.send(self).text 
        if not durl:
            raise ReportFetchError(f"Failed to generate report for key: {key}")        
        return self.fetch_durl_content(durl)

    def fetch_report_dataframe(self, key: str, pat: str = "", replaces: tuple = tuple(), **kwargs) -> pd.DataFrame:
        try:
            buffer = self.fetch_report_bytes(key, pat, replaces)
        except (ReportFetchError, ValueError) as e:
            self.logger.info(f"Failed to fetch report bytes for {key}: {e}. Returning empty DataFrame.")
            return pd.DataFrame()
        excel_kwargs = kwargs.copy()
        if "engine" not in excel_kwargs:
            excel_kwargs["engine"] = "openpyxl"
        df = pd.read_excel(buffer, **excel_kwargs)
        self.log_dataframe_metadata(df, f"Fetched report: {key}")
        return df

    def fetch_moc_reports(self, fromd: datetime.date, tod: datetime.date, key: str, pat: str, is_slash: bool = True, lookback: relativedelta.relativedelta|None = None, **kwargs) -> pd.DataFrame:
        if lookback:
            fromd = (fromd - lookback) #type: ignore
        dfs = []
        for moc in moc_range(fromd, tod, slash=is_slash):
            try:
                self.logger.debug(f"Fetching MOC report for {moc} (Key: {key})")
                dfs.append(self.fetch_report_dataframe(key, pat, (moc,), **kwargs))
            except Exception as e:
                self.logger.error(f"Failed to fetch MOC report for {moc} (Key: {key}): {e}", exc_info=True)
                pass
        
        if not dfs:
            return pd.DataFrame()
            
        return pd.concat(dfs)

    def filter_by_date(self, df: pd.DataFrame, date_column: str, fromd: datetime.date, tod: datetime.date, format: str|None = None) -> pd.DataFrame:
        if df.empty:
            return df
        if date_column not in df.columns:
            raise Exception(f"Date column {date_column} not found in DataFrame")
        df[date_column] = pd.to_datetime(df[date_column],format = format).dt.date
        return df[(df[date_column] >= fromd) & (df[date_column] <= tod)] #type: ignore

    @ikea_screen("gstReturnsReport")
    def gstr_report(self, fromd: datetime.date, tod: datetime.date, gstr_type: int = 1) -> pd.DataFrame:
        r = get_curl("ikea/gstr")
        r.url = curl_replace(r"(pramFromdate=).{10}(&paramToDate=).{10}(&gstrValue=).", 
                                (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y"), str(gstr_type)), r.url)

        durl = r.send(self).text
        if not durl:
            self.logger.info(f"GSTR report returned empty durl for {fromd} to {tod}. Returning empty DataFrame.")
            return pd.DataFrame()
        return pd.read_csv(self.fetch_durl_content(durl))

    @ikea_screen("Collection Summary")
    def collection(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        date_col = "Collection Date"
        df = self.fetch_report_dataframe("ikea/collection", r'(":val10":").{10}(",":val11":").{10}(",":val12":".{10}",":val13":").{10}(.*?":val20":).{2}', 
                        (fromd.strftime("%Y/%m/%d"), tod.strftime("%Y/%m/%d"), tod.strftime("%Y/%m/%d"),str(self.user_id)),
                        dtype = {date_col: "str"})
        if df.empty:
            return df
        
        df["raw_date"] = df[date_col].str.split(" ").str[0]
        df = df[df["raw_date"].notna()]
        df[date_col] = None

        uid = datetime.date.today().strftime("%d%m%Y")
        try: 
            formats = ["%d/%m/%Y","%Y-%m-%d"]
            for format_str in formats : 
                mask = df[date_col].isna()
                df.loc[mask, date_col] = pd.to_datetime(df.loc[mask,'raw_date'], format=format_str, errors='coerce')
            max_coll_date = df[date_col].max(skipna=True).date()
            if max_coll_date > tod : 
                raise Exception(f"Collection Date is greater than to date : {tod}")            
        except Exception as e: 
            self.logger.error(f"Failed to fetch collection report for {fromd} to {tod}: {e}", exc_info=True)
            df.to_excel(f"collection_date_exception_{uid}.xlsx",index = False)
            raise 
        return df 
    
    def crnote(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        crnote = self.fetch_report_dataframe("ikea/crnote", r'(":val3":").{10}(",":val4":").{10}', ((fromd - datetime.timedelta(weeks=12)).strftime("%d/%m/%Y"),
                                                                                    tod.strftime("%d/%m/%Y")))
        if crnote.empty:
            return crnote
        crnote = self.filter_by_date(crnote,"Adjusted/Collected/Cancelled Date",fromd,tod,format = "%Y-%m-%d")
        return crnote
    
    @ikea_screen("Outstanding Report")
    def outstanding(self, date: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/outstanding", r'(":val9":").{10}(.{34}).{10}', (date.strftime("%Y-%m-%d"), date.strftime("%Y-%m-%d")))
    
    def download_manual_collection(self) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/download_manual_collection", r'(":val10":").{10}', (datetime.date.today().strftime("%d/%m/%Y"),))
    
    def download_settle_cheque(self, type: str = "PENDING", fromd: datetime.date|None = None, tod: datetime.date|None = None) -> pd.DataFrame:
        fromd = fromd or datetime.date.today()
        tod = tod or datetime.date.today()
        return self.fetch_report_dataframe("ikea/download_settle_cheque", r'(":val1":").*(",":val2":").{10}(",":val3":").{10}(.{32}).{10}', 
                            (type, fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y"), datetime.date.today().strftime("%d/%m/%Y")))
    
    @ikea_screen("Product Wise Purchase")
    def product_wise_purchase(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/product_wise_purchase", r'(":val1":").{10}(",":val2":").{10}', (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y")))
    
    def product_wise_sales(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/product_wise_sales", r'(":val1":").{10}(",":val2":").{10}', (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y")))
    
    def stock_ledger(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/stock_ledger", r'(":val3":").{10}(",":val4":").{10}', (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y")))
    
    def current_stock(self, date: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/current_stock", r'(":val16":").{10}', (date.strftime("%Y-%m-%d"),))
    
    @ikea_screen("Sales Register")
    def sales_reg(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        df = self.fetch_report_dataframe("ikea/sales_reg", r'(":val1":").{10}(",":val2":").{10}',
                                                        (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y")))
        if df.empty:
            return df
        DATE_COLUMN = "BillDate/Sales Return Date"
        try:
            df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], format="%Y-%m-%d").dt.date
        except:
            try: 
                df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], format="%d/%m/%Y").dt.date
            except Exception as e: 
                print(df[DATE_COLUMN])
                raise Exception(f"Sales Register Date Format Not Supported : {e}")
        #Check if all the dates are within the fromd and tod
        wrong_dates_df = df[((df[DATE_COLUMN] < fromd) | (df[DATE_COLUMN] > tod)) & df[DATE_COLUMN].notna()]
        if not wrong_dates_df.empty:
            raise Exception(f"Sales Register Date are not within the fromd and tod : {fromd} to {tod} , but we found dates {set(wrong_dates_df[DATE_COLUMN].tolist())}")
        return df
    
    def raw_damage_proposal(self, fromd: datetime.date, tod: datetime.date, sheet_name: str) -> pd.DataFrame:
        df = self.fetch_moc_reports(fromd, tod, "ikea/damage_proposal", self.MOC_PAT, 
                                    sheet_name=sheet_name, lookback=relativedelta.relativedelta(months=3))
        return df
    
    def damage_proposals(self, fromd: datetime.date, tod: datetime.date, type: Literal["sales", "purchase"]) -> pd.DataFrame:
        column_map = {  "sales": (" TRANSACTION DETAILS", "TRANS DATE"),
                        "purchase": ("STOCK OUT WITH CLAIM", "TRANS REF DATE")}
        if type not in column_map: raise Exception("Type should be sales or purchase")
        
        sheet_name, date_column = column_map[type]
        df = self.fetch_moc_reports(fromd, tod, "ikea/damage_proposal", self.MOC_PAT, 
                                    sheet_name=sheet_name, lookback=relativedelta.relativedelta(months=3))
        return self.filter_by_date(df, date_column, fromd, tod)

    def claim_status(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        return self.fetch_moc_reports(fromd, tod, "ikea/claim_status",
                            self.MOC_PAT, sheet_name="SUMMARY", lookback=relativedelta.relativedelta(months=6))

    def ushop_ledger(self, fromd: datetime.date, tod: datetime.date) -> BytesIO:
        return self.fetch_report_bytes("ikea/ushop_ledger", r'(":val1":").{10}(",":val2":").{10}', 
                                (fromd.strftime("%Y/%m/%d"), tod.strftime("%Y/%m/%d")))
                            
    def product_hsn_master(self) -> pd.DataFrame:
        dfs = []
        for i in range(1, 11):
            try:
                dfs.append(self.fetch_report_dataframe("ikea/product_master", r'(val2":")[0-9]*', (str(i),)))
            except Exception as e: print(e)
        return pd.concat(dfs)
    
    def dse(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        return pd.read_excel(self.fetch_report_bytes("ikea/dse", r'(":val1":").{10}(",":val2":").{10}',
                                            (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y"))),
                                sheet_name="DSE")
    
    def damage_debitnote(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
        df = self.fetch_moc_reports(fromd, tod, "ikea/damage_debitnote", r'(":val1":").{6}', is_slash=False, sheet_name="Damage Debite Note Report")
        return self.filter_by_date(df, "DEBIT NOTE DATE", fromd, tod)
    
    def pending_bills(self, date: datetime.date) -> dict:
        return self.fetch_report_dataframe("ikea/pending_bills", r'(":val8":").{10}', (date.strftime("%Y-%m-%d"),))
    
    def bill_ageing(self,fromd: datetime.date,tod: datetime.date) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/bill_ageing", r'(":val7":").{10}(",":val8":").{10}', 
                (fromd.strftime("%Y-%m-%d"),tod.strftime("%Y-%m-%d")))
    
    def beat_mapping(self) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/beat_mapping", "", tuple())
    
    def party_master(self) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/party_master")
    
    def stock_master(self) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/stock_master", skiprows=9)
    
    def basepack(self) -> BytesIO:
        return self.fetch_report_bytes("ikea/basepack", "", tuple())
    
    def loading_sheet(self, bills=[]) -> tuple[pd.DataFrame,pd.DataFrame]:
        two_days_before = datetime.date.today() - datetime.timedelta(days=2)
        today = datetime.date.today()
        bytesio = self.fetch_report_bytes("ikea/loading_sheet", r'(":val12":"\').{10}(\'",":val13":"\').{10}(\'",":val14":").{0}',
                                            (two_days_before.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y"), ",".join(bills)))
        df1 = pd.read_excel(bytesio, dtype="str", sheet_name="Loading Sheet")
        df2 = pd.read_excel(bytesio, dtype="str", sheet_name="Party Wise Sales Report")
        return (df1, df2)
    
    def eway_excel(self,fromd: datetime.date,tod: datetime.date,bills: list[str]) -> pd.DataFrame:
        bills.sort()
        df = self.fetch_report_dataframe("ikea/eway_excel", r'(":val1":").{8}(",":val2":").{8}(.*":val5":")[^"]*(",":val6":")[^"]*',
                            (fromd.strftime("%Y%m%d"), tod.strftime("%Y%m%d"), bills[0], bills[-1]))
        return df[df["Doc.No"].isin(bills)] #type: ignore

    @ikea_screen("Pending statement")
    def pending_statement_excel(self, beats, date) -> pd.DataFrame:
        df = self.fetch_report_dataframe("ikea/pending_statement_excel", r'(":val5":").{0}(.*":val8":").{10}',
                            (",".join(beats), date.strftime("%Y-%m-%d")))
        return df

    @ikea_screen("UPI/Online Payment Details")
    def upi_statement(self, fromd, tod) -> pd.DataFrame:
        return self.fetch_report_dataframe("ikea/upi_statement", r'(":val3":"\').{10}(\'",":val4":"\').{10}',
                                                        (fromd.strftime("%Y-%m-%d"), tod.strftime("%Y-%m-%d")))
    
    def stock_movement_report(self,fromd,tod) -> pd.DataFrame:
        """This is based on the ikea Stock N Sales Report . 
        This provides for each stock (batch) opening , sales, pur, ... qtys during a period"""
        return self.fetch_report_dataframe("ikea/stock_movement", r'(":val10":").{10}(",":val11":").{10}',
                                                        (fromd.strftime("%Y-%m-%d"), tod.strftime("%Y-%m-%d")))

class Ikea(IkeaReports):

    def upload_manual_collection(self,file : BytesIO) -> dict :
        files = {
          'file': ('upload.xlsx', file , 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
         }
        return self.post("/rsunify/app/collection/collectionUpload",files = files,data = {}).json()
    
    def upload_settle_cheque(self,file : BytesIO) -> dict :
        files = {
          'file': ('upload.xlsx', file , 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
         }
        return self.post("/rsunify/app/chequeMaintenance/chequeUpload",files = files,data = {}).json()
    
    def get_collection_grid(self):
        today = datetime.date.today()
        data = {"ccl":["EXP00175","FL000001","FL000002","FL000003","FL000004","FL000005","FL000006","NME00001","SMN00001","SMN00002","SMN00003","SMN00004","SMN00005","SMN00006","SMN00007","SMN00008","SMN00009","SMN00010","SMN00011","SMN00012","SMN00013","SMN00014","SMN00015","SMN00016","SMN00017","SMN00018","SMN00019","SMN00020","SMN00021","SMN00022","SMN00023","SMN00024","SMN00025","SMN00026","SMN00027","SMN00028","SMN00029","SMN00030","SMN00031","SMN00032","SMN00033","TL000001","X00000001","X00000002","X00000003"],
                "sd":"","dd":"","bdl":[],"vdl":[],"md":"","pd":"","bf":"","bt":"","fd":"01/01/2026","td":today.strftime("%d/%m/%Y"),"cf":"","ct":"","af":True,"sf":"ALL","sfId":"-1"}
        return self.post("/rsunify/app/collection/collectionGrid",data={"jsonobjcollectionGrid":json.dumps(data)}).json()
    
    def post_collection_grid(self, data: dict):
        return self.post("/rsunify/app/collection/insertcollection",json=data).json()

    def beat_report(self) -> pd.DataFrame :
        #TODO: Clean the function
        html = self.get("/rsunify/app/rssmBeatPlgLink/loadRssmBeatPlgLink").text
        soup = BeautifulSoup(html,features="lxml") 
        
        salesman_ids = [ i.get("value") for i in soup.find("tbody", {"id" : "blockEvt"}).findChildren("input",recursive=True) ][::3]
        salesman_table = pd.read_html(StringIO(html))[0].rename(columns={"Salesperson Code":"salesman_code","Salesperson Name":"salesman_name"})
        salesman_table["salesman_id"] = pd.Series(salesman_ids).apply(int)

        plg_maps = soup.find("input", {"id" : "hiddenSmBeatLnkMap"}).get("value")
        plg_maps = json.loads(plg_maps)
        plg_maps = [ [sal_id] + beat_data for sal_id in plg_maps for beat_data in plg_maps[sal_id] ]         
        plg_maps = pd.DataFrame(plg_maps).astype({ 0  : int }).rename(columns={0:"salesman_id",1:"id",2:"name",3:"plg"})
        plg_maps["days"] = ""
        for col,day in zip(range(6,13),["monday","tuesday","wednesday","thursday","friday","saturday"]) : 
            plg_maps["days"] += plg_maps[col].apply(lambda x : day + "," if int(x) else "")
        plg_maps["days"] = plg_maps["days"].str.strip(",")
        beats = pd.merge(plg_maps,salesman_table,on="salesman_id",how="outer")
        beats = beats[["id","salesman_id","salesman_name","salesman_code","name","plg","days"]]
        beats = beats.dropna(subset="id")
        return beats
        
    @ikea_screen("E-Invoice")
    def einvoice_json(self,fromd,tod,bills) -> BytesIO: 
          return self.fetch_report_bytes("ikea/einvoice_json",r'(":val1":").{8}(",":val2":").{8}(.*":val9":")[^"]*' , 
                              (fromd.strftime("%Y%m%d"),tod.strftime("%Y%m%d"),",".join(bills)) )

    def retrive_bill(self,bill_no):
        self.post("/rsunify/app/ikeaCommonUtilController/removeScreenNameFromSession",data={"screenName":"Manual Billing"})
        data = self.get("/rsunify/app/billing/retrievebill",params={"billRef":bill_no}).json()
        if data.get("billHdVO") is None : return None
        sal_id = data["billHdVO"]["blhDsrId"]
        self.get("/rsunify/app/billing/deletemutable",params={"salesmanId":sal_id})
        return data

    def product_hsn(self) -> dict : 
        return get_curl("ikea/list_of_products").send(self).json()
    
    @ikea_screen("Pending Statement")
    def pending_statement_pdf(self,beats,date) : 
          r = get_curl("ikea/pending_statement_pdf")
          r.data["strJsonParams"] = curl_replace(r'(beatVal":").{0}(.*colToDate":").{10}(.*colToDateHdr":").{10}', 
                                (",".join(beats),date.strftime("%Y-%m-%d") ,date.strftime("%d/%m/%Y")) , r.data["strJsonParams"])
          durl = r.send(self).text
          return self.fetch_durl_content(durl)

    @ikea_screen("E-Invoice IRN Upload")
    def upload_irn(self,bytesio) : 
        files = {'file': ( "IRNGenByMe.xlsx" , bytesio )}
        res = self.post("/rsunify/app/stockmigration/eInvoiceIRNuploadFile",files=files)
        return res.json()
            
    def push_impact(self,fromd,tod,bills,vehicle_name) -> pd.DataFrame|None:
        """Pushes to Impact & returns the list of non pushed bills yet"""
        login_data = self.post("/rsunify/app/impactDeliveryUrl").json()
        url = login_data["url"]
        del login_data["url"]
        url = url + "ikealogin.do?" + urlencode(login_data)
        s = requests.Session() 
        s.get(url)
        s.get("https://shogunlite.com/")
        s.get("https://shogunlite.com/login.do") 
        html = s.get("https://shogunlite.com/deliveryupload_home.do?meth=viewscr_home_tripplan&hid_id=&dummy=").text 
        form = extractForm(html,all_forms=True)
        form =  {"org.apache.struts.taglib.html.TOKEN": form["org.apache.struts.taglib.html.TOKEN"],
                "actdate": fromd.strftime("%d-%m-%Y") + " - " + tod.strftime("%d-%m-%Y") , 
                "selectedspid": "493299",
                "meth":"ajxgetDetailsTrip"} #warning: spid is vehicle A1 (so we keep it default)
        html = s.get(f"https://shogunlite.com/deliveryupload_home.do",params=form).text
        #TODO: REMOVE PRINT
        print(form)
        dfs = pd.read_html(html)
        df = dfs[-1]
        print(df)
        soup = BeautifulSoup(html,"html.parser")
        vehicle_codes = { option.text.lower() : option.get("value")  for option in soup.find("select",{"id":"mspid"}).find_all("option") }
        all_bill_codes = [ code.get("value") for code in soup.find_all("input",{"name":"selectedOutlets"}) ]
        all_bill_numbers = list(df["BillNo"].values)
        bill_to_code_map = dict(zip(all_bill_numbers,all_bill_codes))
        form = extractForm(html)
        form["exedate"] = datetime.date.today().strftime("%d-%m-%Y")
        form["mspid"] = vehicle_codes[vehicle_name.lower()]
        form["meth"] = "ajxgetMovieBillnumber"
        form["selectedspid"] = "493299"
        form["selectedOutlets"] = [ bill_to_code_map[bill] for bill in bills if bill in bill_to_code_map ]
        del form["beat"]
        del form["sub"]
        if len(form["selectedOutlets"]) > 0 : 
            res = s.post("https://shogunlite.com/deliveryupload_home.do",data = form).text
            dfs = pd.read_html(res)
            if len(dfs) == 0 : 
                return None
            df = dfs[-1]
        return df

    @ikea_screen("Beat Export")
    def beat_export(self,fromd,tod):
        self.post("/rsunify/app/sfmIkeaIntegration/callSfmIkeaIntegrationSync")
        data = self.post("/rsunify/app/quantumExport/getSalesmanData",
                {"exportData" : f'{{"fromDate":"{fromd.strftime("%Y-%m-%d")}","toDate":"{tod.strftime("%Y-%m-%d")}"}}'}).json()
        salesman_ids = set([ i[0] for i in data ])
        self.post("/rsunify/app/ikeaCommonUtilController/qocRepopulation")
        exportPayload = f'{{"fromDate":"{fromd.strftime("%Y-%m-%d")}","toDate":"{tod.strftime("%Y-%m-%d")}","salesManId":"{",".join(salesman_ids)}","beatId":"-1"}}'
        export_id = self.post("/rsunify/app/quantumExport/startExport",{"exportData" : exportPayload}).json()
        for _ in range(60):
            status = self.post("/rsunify/app/quantumExport/getExportStatus",{"processId" : export_id}).json()
            print(status)
            if status[0] == "0" and status[1] == "0" and status[2] == "1" : 
                print("Exported")
                break
            time.sleep(10)
        self.post("/rsunify/app/sfmIkeaIntegration/callSfmIkeaIntegrationSync")
        self.post("/rsunify/app/api/callikeatocommoutletcreationallapimethods")
        self.post("/rsunify/app/fileUploadId/upload")

class Billing(Ikea) :

    def __init__(self,user):
        super().__init__(user)
        self.today = datetime.date.today()

    
    def log_order_status(self, df, status, additional_cols=[]):
        """Logs order status for a DataFrame of orders in a table format."""
        if df is None or df.empty:
            return
        try:
            value_col = None
            for col in ["ov", "val", "amt", "order_value", "value", "rate"]:
                if col in df.columns:
                    value_col = col
                    break
            
            cols = ["on", "pn"]
            if value_col:
                cols.append(value_col)
            cols += additional_cols
            
            # Check if columns exist
            cols = [c for c in cols if c in df.columns]
            
            log_lines = []
            for _, row in df[cols].iterrows():
                val_str = f" | Value: {row[value_col]}" if value_col else ""
                log_lines.append(f"Order: {row.get('on', 'N/A')} | Party: {row.get('pn', 'N/A')}{val_str} | Status: {status}")
            
            if log_lines:
                self.logger.info(f"Order Status [{status}]:\n" + "\n".join(log_lines))
        except Exception as e:
            self.logger.error(f"Failed to log order status: {e}")
        
    def _client_id_generator(self): 
        return np.base_repr(self._date_epochs(), base=36).lower() + np.base_repr(random.randint(pow(10, 17), pow(10, 18)),
                 base=36).lower()[:11]

    def _get_import_dates(self, order_date):
        dates = {"importDate": (self.today - datetime.timedelta(days=1)).strftime("%Y-%m-%d") + "T18:30:00.000Z", "orderDate": None}
        if order_date :
            dates["orderDate"] = (order_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d") + "T18:30:00.000Z"
        return dates
      
    def get_creditlock(self,party_data) : 
        params = {
            "partyCode" : party_data["partyCode"],
            "parCodeRef" : party_data["parCodeRef"],
            "parHllCode" : party_data["parHllCode"],
            "showPLG" : party_data["showPLG"],
            "plgFlag" : "true",
            "salChnlCode" : "",
            "isMigration" : "true"
        }
        res = self.get("/rsunify/app/billing/partyplgdatas",params = params).json()
        return res
    
    def release_creditlock(self, party_data):
        party_credit = self.get_creditlock(party_data)
        old_credit_value_limit = party_credit["creditLimit"] 
        old_credit_bills_limit = party_credit["creditBills"]
        credit_value_utilised = party_credit["creditLimitUtilised"]
        credit_bills_utilised = party_credit["creditBillsUtilised"]
        #10 is for buffer
        #Disable the creditvalue release for temporarily
        new_credit_limit = old_credit_value_limit #(credit_value_utilised + party_data["increase_value"] + 10) if old_credit_value_limit else 0 
        new_credit_bills = (credit_bills_utilised + party_data["increase_count"]) if old_credit_bills_limit else 0
        params = { 
            "partyCodeRef":party_data["partyCode"],
            "creditBills":new_credit_bills,
            "creditLimit":new_credit_limit,
            "creditDays":0,
            "panNumber":"",
            "servicingPlgValue":party_data["showPLG"],
            "plgPartyCredit":True,
            "parHllCode":party_data["parHllCode"]
        }
        self.logger.info(f"""Releasing Credit Lock for {party_data.get('partyCode')} , {party_data.get('parHllCode')} , {party_data.get('showPLG')}: 
                             UtilisedValue={credit_value_utilised}, UtilisedBills={credit_bills_utilised} -> New Limit={new_credit_limit}, New Bills={new_credit_bills}
                             {party_credit}""")
        self.get("/rsunify/app/billing/updatepartyinfo",params = params)

    def release_creditlocks(self,party_datas : list):
        for party_data in party_datas :
            self.release_creditlock(party_data)

    @ikea_screen("Order Sync")
    def Sync(self):     
        self.post("rsunify/app/sfmIkeaIntegration/callSfmIkeaIntegrationSync")
        self.post("/rsunify/app/api/callikeatocommoutletcreationallapimethods")
        #Order Sync
        res = self.post('/rsunify/app/fileUploadId/download')
        return res

    @ikea_screen("Delivery Process")
    def Prevbills(self):
        delivery_req = get_curl("ikea/billing/getdelivery")
        delivery = delivery_req.send(self).json()["billHdBeanList"] or []
        self.prevbills = [ bill['blhRefrNo'] for bill in delivery ]
        self.logger.info(f"Previous Delivery Bills: {self.prevbills}")

    @ikea_screen("Market Collection")
    def Collection(self, order_date):
        self.get("/rsunify/app/quantumImport/init")
        self.get("/rsunify/app/quantumImport/filterValidation")
        self.get(f"/rsunify/app/quantumImport/futureDataValidation?importDate={self.today.strftime('%d/%m/%Y')}")

        self.import_dates = self._get_import_dates(order_date)
        get_collection_req = get_curl("ikea/billing/getmarketorder")
        get_collection_req.url = self.base_url + "/rsunify/app/quantumImport/validateloadcollection"
        get_collection_req.json |= self.import_dates 
        self.market_collection = get_collection_req.send(self).json()
        self.get("/rsunify/app/quantumImport/processcheck")
        
        collection_data = self.market_collection["mcl"]
        for coll in collection_data : 
            coll["ck"] = True
            coll["bf"] = True

        self.pushed_collection_party_ids = [ coll["pc"] for coll in collection_data if coll["ck"]  ]
        coll_payload = {"mcl": collection_data, "id": self.today.strftime("%d/%m/%Y"), "CLIENT_REQ_UID": self._client_id_generator() , "ri" : 0}
        self.logger.info(f"Imported Collection Party IDs: {self.pushed_collection_party_ids}. Total items: {len(collection_data)}")
        postcollection = self.post("/rsunify/app/quantumImport/importSelectedCollection", json=coll_payload).json()
        self.logger.info(f"Post Collection Response: {postcollection}")
        
    @ikea_screen("Market Order Billing")
    def get_market_order(self, order_date: datetime.date|None, beat_type: Literal['retail', 'wholesale','all'],allow_partial_bills = False) -> list:
        is_beat_allowed =  lambda beat_name : (("WHOLESALE" in beat_name) == (beat_type == "wholesale")) or (beat_type == "all")
        self.logger.info(f"Processing Order for Date: {order_date}")
        #Get beats
        beats = self.post("/rsunify/app/quantumImport/beatlist", json={"uniqueId":0,"menu":"orderimport"}).json()
        beat_ids = [ str(beat_id) for beat_id,beat_name in beats[1:] if is_beat_allowed(beat_name)]

        get_shikhar = get_curl("ikea/billing/getshikhar")
        get_shikhar.json["importDate"] =  self.today.strftime("%d/%m/%Y")
        shikhar_data = get_shikhar.send(self).json()["shikharOrderList"]
        shikhar_ids = [order[11] for order in shikhar_data[1:] if is_beat_allowed(order[3])]
        self.logger.info(f"Found {len(shikhar_ids)} Shikhar IDs")
    
        self.import_dates = self._get_import_dates(order_date)

        get_order_req = get_curl("ikea/billing/getmarketorder")
        get_order_req.json |= (self.import_dates | {"qtmShikharList" : shikhar_ids, "qtmBeatList" : beat_ids})
        if allow_partial_bills:
            get_order_req.json |= {"isRaPartialBilled": 1,
                                    "isShikharAssistedPartialBilled": 1,
                                    "isShikharSelfPartialBilled": 1}
        self.market_order = get_order_req.send(self).json()
        
        # Return full raw response as requested
        return self.market_order.get("mol")

    @ikea_screen("Market Order Billing")
    def post_market_order(self, order_data: list, order_numbers: list[str], delete_order_numbers: list[str]):

        if delete_order_numbers :
            delete_orders_data = copy.deepcopy(order_data)
            for order in delete_orders_data :
                order["ck"] = (order["on"] in delete_order_numbers)
            delete_market_order = get_curl("ikea/billing/delete_orders")
            delete_market_order.json |= {"mol": delete_orders_data , "id": self.today.strftime("%d/%m/%Y")}
            delete_market_order.send(self).text
            order_data = [order for order in order_data if order["on"] not in delete_order_numbers]

        for item in order_data:
            item["ck"] = (item["on"] in order_numbers)
        
        uid = self._client_id_generator()
        post_market_order = get_curl("ikea/billing/postmarketorder")
    
        # reallocated_data = self.post("/rsunify/app/quantumImport/reAllocation",
        #             json={"mol": order_data , "id": self.today.strftime("%d/%m/%Y")}).json()
        
        # reallocated_data = reallocated_data["mol"]
        # for item in reallocated_data:
        #     item["ck"] = (item["on"] in order_numbers)

        # with open("post_market_order.json", "w") as f:
        #     json.dump(order_data, f)

        # with open("reallocated_data.json", "w") as f:
        #     json.dump(reallocated_data, f)

        post_market_order.json |= {"mol": order_data , 
                                        "id": self.today.strftime("%d/%m/%Y"), "CLIENT_REQ_UID": uid}
        res = post_market_order.send(self)
        
        try:
            log_durl = res.json()["filePath"]
            if log_durl:
                log_content = self.fetch_durl_content(log_durl).read()
                with open("log.txt", "wb") as f:
                    f.write(log_content)
        except Exception as e:
            self.logger.error(f"Failed to download/save log: {e}")

    @ikea_screen("Delivery Process")
    def Delivery(self):
        if not self.config["auto_delivery_process"] : 
            self.logger.info("Auto delivery process is disabled in config. Skipping delivery.")
            self.bills = []
            return 
        delivery = get_curl("ikea/billing/getdelivery").send(self).json()["billHdBeanList"] or []
        if len(delivery) == 0 : 
            self.logger.info("No delivery bills found.")
            self.bills = []
            return 
        delivery = pd.DataFrame(delivery)
        self.logger.debug(f"All Delivery Bills: {list(delivery.blhRefrNo)}")
        delivery = delivery[ ~delivery.blhRefrNo.isin(self.prevbills) ]
        self.bills = list(delivery.blhRefrNo)
        self.logger.info(f"Bills to be processed (New Delivery): {self.bills}")
        delivery["vehicleId"] = 1
        data = {"deliveryProcessVOList": delivery.to_dict(orient="records"), "returnPickList": []}
        save_res = self.post("/rsunify/app/deliveryprocess/savebill",json=data).json()

    def __group_consecutive_bills(self,bills:list[str]):

        def extract_serial(bill_number:str):
            match = re.search(r'(\D+)(\d{5})$', bill_number)
            if match:
                return match.group(1), int(match.group(2))  # Return prefix and serial number as a tuple
            return None, None

        sorted_bills = sorted(bills, key=lambda x: extract_serial(x))

        groups = []
        current_group = []
        prev_prefix: str|None = None
        prev_serial: int|None = None

        for bill in sorted_bills:
            prefix, serial = extract_serial(bill)
            if not prefix:
                continue

            if prev_prefix == prefix and prev_serial is not None and serial == prev_serial + 1:
                current_group.append(bill)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [bill]

            prev_prefix, prev_serial = prefix, serial

        if current_group:
            groups.append(current_group)

        return groups

    def get_bill_durl(self,billfrom,billto,report_type,**kwargs) :
        return self.get(f"/rsunify/app/commonPdfRptContrl/pdfRptGeneration?strJsonParams=%7B%22billFrom%22%3A%22{billfrom}%22%2C%22billTo%22%3A%22{billto}%22%2C%22reportType%22%3A%22{report_type}%22%2C%22blhVatFlag%22%3A2%2C%22shade%22%3A1%2C%22pack%22%3A%22910%22%2C%22damages%22%3Anull%2C%22halfPage%22%3A0%2C%22bp_division%22%3A%22%22%2C%22salesMan%22%3A%22%22%2C%22party%22%3A%22%22%2C%22market%22%3A%22%22%2C%22planset%22%3A%22%22%2C%22fromDate%22%3A%22%22%2C%22toDate%22%3A%22%22%2C%22veh_Name%22%3A%22%22%2C%22printId%22%3A0%2C%22printerName%22%3A%22TVS+MSP+250+Star%22%2C%22Lable_position%22%3A2%2C%22billType%22%3A2%2C%22printOption%22%3A%220%22%2C%22RptClassName%22%3A%22BILL_PRINT_REPORT%22%2C%22reptName%22%3A%22billPrint%22%2C%22RptId%22%3A%22910%22%2C%22freeProduct%22%3A%22Default%22%2C%22shikharQrCode%22%3Anull%2C%22rptTypOpt%22%3A%22pdf%22%2C%22gstTypeVal%22%3A%221%22%2C%22billPrint_isPrint%22%3A0%2C%22units_only%22%3A%22Y%22%7D",**kwargs).text

    def get_bill_new_pdf(self,billfrom,billto):
        r = get_curl("ikea/bill_pdf")
        r.json["payload"]["billFrom"] = billfrom
        r.json["payload"]["billTo"] = billto
        r.json["payload"]["bill_from"] = billfrom
        r.json["payload"]["bill_to"] = billto
        fileName = r.send(self).json()["payload"]
        print(fileName)
        return BytesIO(self.get("/rsunify/app/visualizer/rf/report/stream",params={"FILE":fileName}).content)

    def get_bill_old_pdf(self,billfrom,billto):
        return self.fetch_durl_content( self.get_bill_durl(billfrom,billto,"pdf") )
    
    def fetch_bill_pdfs(self, bills: list[str],ignore_checks = False,old_pdf = True) -> BytesIO:
        pdfs = []
        self.get_bill_pdf = self.get_bill_old_pdf if old_pdf else self.get_bill_new_pdf
        self.logger.info(f"Fetching bill PDFs for {len(bills)} bills")
        for group in self.__group_consecutive_bills(bills):
             self.logger.debug(f"Fetching PDF for group: {group[0]} to {group[-1]}")
             pdf1 = self.get_bill_pdf(group[0],group[-1])
             if (not ignore_checks) and old_pdf :
                pdf2 = self.get_bill_pdf(group[0],group[min(1,len(group)-1)])
                #PDF2 has only one bill and verifies if the pages of pdf2 and pdf1 are same (pdf2 is a subset of pdf1)
                
                reader1 = PdfReader(pdf1).pages
                reader2 = PdfReader(pdf2).pages
                for page_no in range(len(reader2)) :
                    if reader2[page_no].extract_text() != reader1[page_no].extract_text() :
                        self.logger.error(f"PDF Content Mismatch for group {group}. Saving debug files.")
                        self.logger.error(f"Page {page_no} content mismatch \n First Copy: {reader1[page_no].extract_text()} \n Second Copy: {reader2[page_no].extract_text()}")
                        pdf1.seek(0)
                        pdf2.seek(0) 
                        with open("first_copy_first_download.pdf","wb+") as f : 
                            f.write(pdf1.getvalue())
                        with open("first_copy_second_download.pdf","wb+") as f : 
                            f.write(pdf2.getvalue())        
                        raise Exception("Print PDF Problem. Canceled First Copy Printing")
             pdf1.seek(0)
             pdfs.append(pdf1)
        
        merger = PdfMerger()
        for pdf_bytesio in pdfs:
            pdf_bytesio.seek(0)
            merger.append(pdf_bytesio)
        
        output = BytesIO()
        merger.write(output)
        merger.close()
        output.seek(0)
        return output

    def fetch_bill_txts(self, bills: list[str]) -> BytesIO:
        txts = []
        for group in self.__group_consecutive_bills(bills):
            txts.append( self.fetch_durl_content( self.get_bill_durl(group[0],group[-1],"txt")) )
        
        output = BytesIO()
        for text_bytesio in txts:
            text_bytesio.seek(0)
            output.write(text_bytesio.read())
            output.write(b"\n")
        output.seek(0)
        return output

    def Printbill(self,bills = None,print_files = ["bill.pdf","bill.txt"]):
        if bills is not None : self.bills = bills 
        if len(self.bills) == 0 : 
            self.logger.info("No bills to print.")
            return
        
        if os.name != 'nt':
            self.logger.warning("Printing is only supported on Windows. Skipping print.")
            return False

        try:
            import win32api
            for print_file in print_files : 
                win32api.ShellExecute(0, 'print', print_file , None, '.', 0)
            return True
        except Exception as e:
            self.logger.error(f"Printing Failed: {e}", exc_info=True)
            print("Win32 Failed . Printing Failed")
            print(e)
            return False

class IkeaBank(Ikea):
    key = "ikea"

## Needs to checked 
class GstWrongCredentails(WrongCredentials) :
    pass

class GstExpiredCredentails(WrongCredentials) :
    pass

class GstMultipleWrongAttempts(WrongCredentials) :
    pass

class Gst(Session) : 
     key = "gst"
     base_url = "https://gst.gov.in"
     home = "https://gst.gov.in"
     load_cookies = True
     rtn_types_ext = {"gstr1":"zip","gstr2a":"zip","gstr2b":"json"}

     def __init__(self,user:str) : 
          super().__init__(user)
          base_path = Path(__file__).parent
          self.dir = str( (base_path / ("data/gst/" + self.user.user)).resolve() )
          connection_retry = Retry(
              total=3,                  # Max 3 retries
              connect=3,                # Specifically retry on connection errors
              read=3,                   # Retry if the server stops responding mid-download
              other=5,
              backoff_factor=1,         # Wait 2s, 4s, 8s (crucial for "Connection Reset")
              raise_on_status=False,    # Don't raise error if it's a 404/500, only on network fail
              status_forcelist=[]       # Empty list means don't retry on HTTP codes, only network
          )
  
          adapter = HTTPAdapter(max_retries=connection_retry)  
          self.mount('https://', adapter)


     def captcha(self) : 
          self.cookies.clear()
          res = self.get('https://services.gst.gov.in/services/login',
                        headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'})
          login = self.get('https://services.gst.gov.in/pages/services/userlogin.html',
                        headers={'Accept':'application/json, text/plain, */*'})
          captcha = self.get('https://services.gst.gov.in/services/captcha?rnd=0.7395713643528188').content
          self.user.update_cookies(self.cookies)
          return captcha
          
     def login(self,captcha) :
          data =  { "captcha": captcha , "deviceID": None ,"mFP": "{\"VERSION\":\"2.1\",\"MFP\":{\"Browser\":{\"UserAgent\":\"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36\",\"Vendor\":\"Google Inc.\",\"VendorSubID\":\"\",\"BuildID\":\"20030107\",\"CookieEnabled\":true},\"IEPlugins\":{},\"NetscapePlugins\":{\"PDF Viewer\":\"\",\"Chrome PDF Viewer\":\"\",\"Chromium PDF Viewer\":\"\",\"Microsoft Edge PDF Viewer\":\"\",\"WebKit built-in PDF\":\"\"},\"Screen\":{\"FullHeight\":1080,\"AvlHeight\":1080,\"FullWidth\":1920,\"AvlWidth\":1920,\"ColorDepth\":24,\"PixelDepth\":24},\"System\":{\"Platform\":\"Linux x86_64\",\"systemLanguage\":\"en-US\",\"Timezone\":-330}},\"ExternalIP\":\"\",\"MESC\":{\"mesc\":\"mi=2;cd=150;id=30;mesc=1555497;mesc=1560133\"}}" ,
                    "password": self.password , "type": "username" , "username": self.username }
          res = self.post("https://services.gst.gov.in/services/authenticate" ,
                                json = data)
          with open("a.html","wb+") as f : 
              f.write(res.content)
          res = res.json()
          if "errorCode" in res.keys() : 
              if res["errorCode"] == "SWEB_9000" : 
                 return False 
              elif res["errorCode"] == "AUTH_9002" : 
                  raise GstWrongCredentails("Invalid Username or Password")
              elif res["errorCode"] == "AUTH_9033" : 
                  raise GstExpiredCredentails("Password Expired , kindly change password")
              elif res["errorCode"] == "SWEB_9014" :
                  raise GstMultipleWrongAttempts("You have entered a wrong password for 3 consecutive times")
              else : 
                  print(res)
                  raise Exception("Unknown Exception")
          auth =  self.get("https://services.gst.gov.in/services/auth/",headers = {'Referer': 'https://services.gst.gov.in/services/login'})
          self.user.update_cookies(self.cookies)
     
     def is_logged_in(self) : 
         return len(self.getuser()) != 0 

     def getuser(self) : 
           try : 
            data = self.get("https://services.gst.gov.in/services/api/ustatus",
            headers = {"Referer": "https://services.gst.gov.in/services/auth/fowelcome"}).json()
           except Exception as e : 
               print("Exception Occured on get user :",e)
               print("Bypassing get_user and returning empty user list")
               return []
           return data 
     
     def getinvs(self,period,types,gstr_type="gstr1") :
         uploaded_by = 'OE' if 'B2CS' in types.upper()  else 'SU'
         data = self.get(f"https://return.gst.gov.in/returns/auth/api/{gstr_type}/invoice?rtn_prd={period}&sec_name={types.upper()}&uploaded_by={uploaded_by}",
                        headers = {"Referer": "https://return.gst.gov.in/returns/auth/gstr1"}).json()
         if "error" in data.keys()  :
             return []
         invs = data["data"]["processedInvoice"]
         return invs 
     
     def multi_downloader(self,periods,rtn_type="gstr1") :  
         """User function to download zips / jsons for multi period and different rtn_types"""
         rtn_type = rtn_type.lower()
         downloader_functions = {"zip":self.download_zip,"json":self.download_json}
         fname_ext = self.rtn_types_ext[rtn_type]
         downloader_function = downloader_functions[fname_ext]
         dir = self.dir + "/" + rtn_type
         downloads = []
         with ThreadPoolExecutor(max_workers=9) as executor:
              for period in periods :
                  if not os.path.exists(f"{dir}/{period}.{fname_ext}") : 
                         downloads.append(executor.submit( downloader_function,period,dir,rtn_type))
              for future in as_completed(downloads): pass 

     def download_zip(self,period,dir,rtn_type) :
         get_status = lambda flag : self.get(f"https://return.gst.gov.in/returns/auth/api/offline/download/generate?flag={flag}&rtn_prd={period}&rtn_typ={rtn_type.upper()}",
                                    headers={"Referer":"https://return.gst.gov.in/returns/auth/gstr/offlinedownload"}).json()     
         while True :  
             try : status = get_status(0)
             except : 
                time.sleep(60) 
                continue
             if "data" in  status and "token" not in status["data"] : #already download generated 
                 if datetime.now() - date_parse(status["data"]["timeStamp"])  >= datetime.timedelta(hours=24) : 
                    get_status(1)
                 else : 
                    os.makedirs(dir,exist_ok=True)
                    with open(f"{dir}/{period}.zip","wb+") as f : 
                        f.write( self.get( status["data"]["url"][0] ).content )
                        print(f"{period} donwloaded...")
                    break 
             time.sleep(60)

     def download_json(self,period,dir = None,rtn_type = None) :  
        if dir : 
            os.makedirs(dir,exist_ok=True)
        data = self.get(f"https://gstr2b.gst.gov.in/gstr2b/auth/api/gstr2b/getjson?rtnprd={period}",
                    headers = {"Referer": "https://gstr2b.gst.gov.in/gstr2b/auth/"}).json()
        if "error" in data : 
            if data["error"]["error_cd"] == "RET2B1016" : data = {}
            else : 
                print(data) 
                raise Exception("Error on Download Json")
        else  : 
            data = data["data"]["docdata"]
        if dir : 
            json.dump( data , open(f"{dir}/{period}.json","w+") )
        return data
          
     def read_json(self,period,rtn_type,dir=None) :
         fname_ext = self.rtn_types_ext[rtn_type]
         if dir is None : dir = self.dir 
         dir = dir + "/" + rtn_type
         fname = f"{dir}/{period}.{fname_ext}"
         json_file = fname
         if not os.path.exists(fname) : return None 

         if fname_ext == "zip" : 
            json_file = zipfile.ZipFile(fname).namelist()[0]
            os.system(f"unzip -o {fname}")

         data = defaultdict(list , json.load( open(json_file) ) )
         dfs = {}
         for (type,key) in [("b2b","inv"),("cdnr","nt")] : 
             if rtn_type in ["gstr1"] :  
                df  = pd.DataFrame( [  j | k["itm_det"] | {"ctin":i["ctin"]}  for i in data[type] for j in i[key] for k in j["itms"] ] )
                if len(df.index) : del df["itms"]
             if rtn_type in ["gstr2a","gstr2b"] :
                df  = pd.DataFrame( [  j | k | {"ctin":i["ctin"]}  for i in data[type] for j in i[key] for k in j["items"] ] )
                if len(df.index) : del df["items"]
             df["period"] = period 
             dfs[type] = df
         for type in ["b2cs"] :
             df = pd.DataFrame( data["b2cs"] ) 
             df["period"] = period 
             dfs["b2cs"] = df
         dfs["period"] = period
         return dfs 
     
     def make_report(self,periods,rtn_type,dir_report,filter_func=None,) :
         data = [ self.read_json(month,rtn_type) for month in periods  ]
         data = [ i for i in data if i is not None ]         
         agg = {"txval":sum,"camt":sum,"samt":sum}
         all = []
         for (k,inum_column) in [("b2b","inum"),("cdnr","nt_num"),("b2cs","rt")] :
             df = pd.concat([ i[k] for i in data ] ,axis=0)
             if len(df.index) == 0 : continue 
             if filter_func is not None : 
                if k not in filter_func : continue 
                df = filter_func[k](df)
             t = pd.to_datetime(df['period'],format="%m%Y").dt.to_period('Q-OCT').dt
             if rtn_type in ["gstr2b"] : 
                 df = df.rename(columns={"cgst":"camt","sgst":"samt","ntnum":"nt_num"})

             df["year"] = (t.qyear-1).astype(str) + "-" + t.qyear.astype(str)
             df["count"] = df[inum_column]
             if "nt_num" in df.columns : df = df.rename(columns = {"nt_num" : "inum"})

             writer = pd.ExcelWriter(f"{dir_report}/{rtn_type}_{k}.xlsx") 
             df.groupby("period").aggregate(agg | {"count":"nunique"}).to_excel( writer , sheet_name="Monthly")
             df.groupby("year").aggregate(agg | {"count":"nunique"}).to_excel( writer , sheet_name="Yearly")
             if "ctin" in df.columns : 
                 df_party_sum = df.pivot_table(index=["ctin","period"] , values = agg.keys() , aggfunc=agg, margins=True)
                 df_party_sum.to_excel( writer , sheet_name="Party-Wise")
             df.to_excel(writer,sheet_name="Detailed",index=False)
             writer.close()
             df["type"] = k 
             all.append( df[["period","year","txval","camt","samt","type"]] )
         all = pd.concat(all,axis=0)
         writer = pd.ExcelWriter(f"{dir_report}/{rtn_type}_all.xlsx") 
         all.groupby(["period","type"]).aggregate(agg).to_excel( writer , sheet_name="Monthly")
         all.groupby(["year","type"]).aggregate(agg).to_excel( writer , sheet_name="Yearly")
         all.to_excel(writer,sheet_name="Detailed",index=False)
         writer.close()   
     
     def get_einv_data(self,seller_gstin,period,doctype,inum) : 
         p = datetime.datetime.strptime( "01" + period , "%d%m%Y" )
         year = (p.year - 1) if p.month < 4 else p.year 
         fy = f"{year}-{(year+1)%100}"
         params = {'stin': seller_gstin ,'fy': fy ,'doctype': doctype ,'docnum': str(inum) ,'usertype': 'seller'}
         data = self.get('https://einvoice.gst.gov.in/auth/api/getIrnData',
             params=params, headers = { 'Referer': 'https://einvoice.gst.gov.in/jsonDownload' }
         ).json()
         if "error" in data : return None     
         data = json.loads(data["data"])["data"]
         signed_inv = data["SignedInvoice"]
         while len(signed_inv) % 4 != 0: signed_inv += "="
         payload = base64.b64decode(signed_inv.split(".")[1] + "==").decode("utf-8")
         inv = json.loads( json.loads(payload)["data"] )
         qrcode = data["SignedQRCode"]
         return inv | { "qrcode" : qrcode }
     
     def upload(self,period,fname) : 
           files = {'upfile': ( "gst.json" , open(fname) , 'application/json', { 'Content-Disposition': 'form-data' })}
           ret_ref = {"Referer": "https://return.gst.gov.in/returns/auth/gstr/offlineupload"}
           ref_id =  self.post(f"https://return.gst.gov.in/returndocs/offline/upload",
                  headers = ret_ref | {"sz" : "304230" }, 
                  data = {  "ty": "ROUZ" , "rtn_typ": "GSTR1" , "ret_period": period } ,files=files).json()
           ref_id = ref_id['data']['reference_id']
           res = self.post("https://return.gst.gov.in/returns/auth/api/gstr1/upload" , headers = ret_ref,
                           json = {"status":"1","data":{"reference_id":ref_id},"fp":period}) 
       
           for times in range(0,90) : 
              time.sleep(1)
              status_data = self.get(f"https://return.gst.gov.in/returns/auth/api/offline/upload/summary?rtn_prd={period}&rtn_typ=GSTR1",
                       headers = ret_ref).json()["data"]["upload"] 
              for status in status_data : 
                  if status["ref_id"] == ref_id : 
                     print( status )
                     if status["status"] == "PE" : 
                         self.get(f" https://return.gst.gov.in/returns/auth/api/offline/upload/error/generate?ref_id={ref_id}&rtn_prd={period}&rtn_typ=GSTR1",headers = ret_ref)
                     return status     

     def get_error(self,period,ref_id,fname) : 
         for times in range(0,40) : 
            time.sleep(1)
            res = self.get(f"https://return.gst.gov.in/returns/auth/api/offline/upload/summary?rtn_prd={period}&rtn_typ=GSTR1",
                     headers = {"Referer": "https://return.gst.gov.in/returns/auth/gstr/offlineupload"}).json()  
            status_data = res["data"]["upload"]
            for status in status_data : 
                if status["ref_id"] == ref_id :
                  if status["er_status"] == "P" : 
                    res = self.get(f"https://return.gst.gov.in/returns/auth/api/offline/upload/error/report/url?token={status['er_token']}&rtn_prd={period}&rtn_typ=GSTR1",
                              headers = {"Referer": "https://return.gst.gov.in/returns/auth/gstr/offlineupload"}) 
                    with open(fname,"wb") as f  : 
                          f.write(res.content) 
                    return None 
         raise Exception("GST Get error timed out")          
     
     def get_period_summary(self,period) : 
         #https://return.gst.gov.in/returns/auth/api/gstr1/summary?rtn_prd=012025
            data = self.get(f"https://return.gst.gov.in/returns/auth/api/gstr1/summary?rtn_prd={period}",
                        headers = {"Referer": "https://return.gst.gov.in/returns/auth/gstr1"}).json()
            if data is not None  : 
                res = {}
                for i in data["data"]["sec_sum"]:
                    sec_nm = i["sec_nm"]
                    if sec_nm == "TTL_LIAB":
                        sec_nm = "total"
                    res[sec_nm] = {
                        "txval": i.get("ttl_tax", None),
                        "cgst": i.get("ttl_cgst", None),
                        "sgst": i.get("ttl_sgst", None),
                        "igst": i.get("ttl_igst", None),
                        "cess": i.get("ttl_cess", None),
                        "val": i.get("ttl_val", None),
                        "ttl_rec": i.get("ttl_rec", None)
                    }
                    if "sub_sections" in i:
                        res[sec_nm]["sub_sections"] = [
                            {
                                "sec_nm": sub.get("sec_nm") or sub.get("typ"),
                                "txval": sub.get("ttl_tax", None),
                                "cgst": sub.get("ttl_cgst", None),
                                "sgst": sub.get("ttl_sgst", None),
                                "igst": sub.get("ttl_igst", None),
                                "cess": sub.get("ttl_cess", None),
                                "val": sub.get("ttl_val", None),
                                "ttl_rec": sub.get("ttl_rec", None)
                            }
                            for sub in i["sub_sections"]
                        ]
                return res
            else : 
                raise Exception("GST Get Summary Failed Json data is None")
    
     def gstin_details(self,gstin):
        res = self.post("https://publicservices.gst.gov.in/publicservices/auth/api/search/tp",
                                        headers={"Referer": "https://services.gst.gov.in/",
                                        "Host":"publicservices.gst.gov.in",
                                        "Origin":"https://services.gst.gov.in"}, json = {"gstin":gstin})
        data = res.json()
        is_active = (data["sts"] == "Active")
        return { "is_active" : is_active }
          
def myHash(str) : 
  hash_object = hashlib.md5(str.encode())
  md5_hash = hash_object.hexdigest()
  return hashlib.sha256(md5_hash.encode()).hexdigest()

def sha256_hash(input_str):
    return hashlib.sha256(input_str.encode()).hexdigest()

def extractForm(html,all_forms = False) :
    soup = BeautifulSoup(html, 'html.parser')
    if all_forms : 
      form = {  i["name"]  : i.get("value","") for form in soup.find_all("form") for i in form.find_all('input', {'name': True}) }
    else : 
      form = {  i["name"]  : i.get("value","") for i in soup.find("form").find_all('input', {'name': True}) }
    return form 

class EinvoiceWrongCredentials(WrongCredentials) :  
    pass

class Einvoice(Session) : 
      key = "einvoice"
      base_url = "https://einvoice1.gst.gov.in"
      home = "https://einvoice1.gst.gov.in"
      load_cookies = True
 
      def captcha(self) : 
          self.cookies.clear()
          self.cookies.set("ewb_ld_cookie",value = "292419338.20480.0000" , domain = "ewaybillgst.gov.in")             
          self.form = extractForm( self.get( self.base_url ).text )
          img = self.get("/get-captcha-image").content
          self.user.update_cookies( self.cookies )
          self.user.config["form"] = self.form 
          self.user.save()
          return img 
          
      def login(self,captcha) :
          r = get_curl("einvoice/login")
          salt = self.get("/Home/GetKey").json()["key"]
          md5pwd = hashlib.sha256((myHash(self.password) + salt).encode()).hexdigest()       
          sha_pwd =  sha256_hash(self.password)
          sha_salt_pwd =  sha256_hash(sha_pwd + salt)
          form:dict = self.config.get("form",{}) # type: ignore
          r.data =  form | {'UserLogin.UserName': self.username, 
                                 'UserLogin.Password': sha_salt_pwd , 
                                 "CaptchaCode" : captcha, 
                                 "UserLogin.HiddenPasswordSha":sha_pwd,
                                 "UserLogin.PasswordMD5":md5pwd}
          response  = r.send(self)
          is_success = (response.url == f"{self.base_url}/Home/MainMenu")
          error_div  = BeautifulSoup(response.text, 'html.parser').find("div",{"class":"divError"})
          error = error_div.text.strip() if (not is_success) and (error_div is not None) else ""
          if is_success : 
              self.user.update_cookies(self.cookies)
          else : 
              if "captcha" not in error.lower() : 
                  raise EinvoiceWrongCredentials(error)
          return is_success 

      def is_logged_in(self) : 
          try : 
            res = self.get("/Home/MainMenu")
            with open("einv_homepage.html","w+") as f :
                f.write(res.text)
          except Exception as e :
              print("Exception Occured on is_logged_in :",e) 
              return False
          return "/Home/MainMenu" in res.url

      def upload(self,json_data:str)  :  
           bulk_home = self.get("/Invoice/BulkUpload").text
           with open("einv_bulkupload.html","w+") as f: 
               f.write(bulk_home)
           files = { "JsonFile" : ("einvoice.json", StringIO(json_data) ,'application/json') }
           form = extractForm(bulk_home, all_forms=True)
           post_data = {
               '__RequestVerificationToken': form.get('__RequestVerificationToken'),
               'name': '',
               'submit': 'Upload'
           }
           upload_home = self.post("/Invoice/BulkUpload" ,  files = files , data = post_data ).text
           #Check if user is blocked due to two factor auth
           # if "This user is blocked" in upload_home : 
           #    raise Exception("Einvoice Portal : This user is blocked from generation of eInvoices. Either complete Two Factor Authentication or complete Deferment of Two Factor Authentication")
           success = pd.read_excel( self.get("/Invoice/ExcelUploadedInvoiceDetails").content )
           failed = pd.read_excel( self.get("/Invoice/FailedInvoiceDetails").content )
           print(failed)
           failed.to_excel("failed_einv.xlsx")
           return success , failed 
      
      def get_filed_einvs(self,date) -> pd.DataFrame : 
          """This functions works on today - 2 to today (Only 3 past days data available)"""
          form = extractForm( self.get("/MisRpt").text )
          form["submit"] = "Date"
          form["irp"] = "NIC1"
          form["ToDate"] = date.strftime("%d/%m/%Y")
          table_html = self.post("/MisRpt/MisRptAction",data=form).text
          if "<td>2154</td>" in table_html :
              return None
          irn_gen_by_me_excel_bytesio = self.get('/MisRpt/ExcelGenerratedIrnDetails?noofRec=1&Actn=GEN').content
          df = pd.read_excel(BytesIO(irn_gen_by_me_excel_bytesio))
          return df

          
      #Unverified
      def getinvs(self) : 
          form = extractForm( self.get("/MisRpt").text )
          form["submit"] = "Date"
          form["irp"] = "NIC1"
          fdate = datetime.datetime.strptime(form["FromDate"] ,"%d/%m/%Y")
          todate = datetime.datetime.strptime(form["ToDate"] ,"%d/%m/%Y")
          print(fdate,todate)
          df = []
          while todate >= fdate : 
             table_html = self.post("/MisRpt/MisRptAction",data=form | 
                                        {"ToDate":todate.strftime("%d/%m/%Y")}).text
             tables = pd.read_html( table_html )
             df = pd.read_excel( BytesIO(self.get('/MisRpt/ExcelGenerratedIrnDetails?noofRec=1&Actn=GEN').content) )
             print(df)
             print(tables)
             if len(tables) : 
                table = tables[0] 
                if "Ack No." in table.columns : 
                   df.append(table) 
             todate -= datetime.timedelta(days=1)
          return pd.concat(df) if len(df) > 0 else None
      
      ## Only works in Linux
      #Not working use gst module instead
      def getpdf(self,irn) : 
          form = extractForm( self.get("https://einvoice1.gst.gov.in/Invoice/EInvoicePrint/Print").text, all_forms=True )
          form = form | {"ModeofPrint": "IRN" , "PrintOption": "IRN","submit": "Print",
          "InvoiceView.InvoiceDetails.Irn": irn }
          html = self.post("https://einvoice1.gst.gov.in/Invoice/EInvoicePrintAction",data=form).text
          html = re.sub(r'src=".*/(.*?)"','src="\\1"',html)
          html = re.sub(r'href=".*/(.*?)"','href="\\1"',html)
          os.makedirs("print_includes", exist_ok=True)
          with open("print_includes/bill.html","w+") as f  : f.write(html)
      
      def upload_eway_bill(self,json_str:str) : 
        self.get("/SignleSignon/EwayBill").text
        res = self.get("https://ewaybillgst.gov.in/BillGeneration/BulkUploadEwayBill.aspx")
        
        buffer = StringIO(json_str)
        files = { "ctl00$ContentPlaceHolder1$FileUploadControl" : ("eway.json", buffer  ,'application/json') }

        form = extractForm(res.text)        
        res = self.post("https://ewaybillgst.gov.in/BillGeneration/BulkUploadEwayBill.aspx",files = files,data =form)

        buffer.seek(0)
        form = extractForm(res.text) | {"ctl00$ContentPlaceHolder1$hdnConfirm": "Y"}
        res = self.post("https://ewaybillgst.gov.in/BillGeneration/BulkUploadEwayBill.aspx",files = files,data =form)
        dfs = pd.read_html(StringIO(res.text))
        if len(dfs) == 0 : 
            raise Exception("Failed to upload eway bill, no table generated")
        df = dfs[0]
        if "EWB No" not in df.columns : 
            raise Exception("Failed to upload eway bill, no EWB No column found in response")
        return df
    
      def get_eway_bills(self) : 
          self.get("/SignleSignon/EwayBill").text
          url = "https://ewaybillgst.gov.in/Reports/CommomReport.aspx?id=3"
          res = self.get(url)
          form = extractForm(res.text)
          form["ctl00$ContentPlaceHolder1$txtDate"] = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%d/%m/%Y")
          form["ctl00$ContentPlaceHolder1$ddlUserId"] = 0
          res = self.post(url,data=form)
          form = extractForm(res.text)
          form["ctl00$ContentPlaceHolder1$ddlUserId"] = 0
          res = self.post(url,data=form)
          dfs = pd.read_html(StringIO(res.text))
          if len(dfs) == 0 : 
              raise Exception("Failed to get eway bills, no table generated")
          df = dfs[0]
          if "EWB No" not in df.columns : 
              raise Exception("Failed to get eway bills, no EWB No column found in response")
          return df

class UnileverWrongCredentials(WrongCredentials):
    pass

class Unilever(Session):
    key = "unilever"
    load_cookies = True

    def __init__(self, user: str):
        super().__init__(user)
        self.base_url = "https://web3.inpartner.unilever.com"
        # We start by bypassing SSL verification globally for this session as required by Unilever SAP
        self.verify = False 
        
        # Disable insecure request warnings caused by setting verify=False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        retry_count = 1
        while not self.is_logged_in():
            self.login()
            retry_count += 1

    def _get_cookies_from_redis(self):
        import redis
        import uuid
        import time
        import json
        
        r = redis.Redis(host='localhost', port=6379, db=0)
        req_id = str(uuid.uuid4())
        
        self.logger.info(f"Requesting SAP cookies from Redis worker (req_id: {req_id})...")
        
        # We send a payload so the worker knows WHICH queue to process
        payload = json.dumps({
            "type": "unilever_cookies",
            "req_id": req_id,
            "username": self.username,
            "password": self.password
        })
        
        r.rpush('unilever_requests', payload)
        
        start_time = time.time()
        while time.time() - start_time < 300: # Wait up to 5 minutes as browser GUI might be slow
            res = r.get(f'unilever_response:{req_id}')
            if res:
                r.delete(f'unilever_response:{req_id}')
                data = json.loads(res.decode('utf-8'))
                
                if "error" in data:
                    raise Exception(f"Worker Error: {data['error']}")
                    
                return data['cookies']
            time.sleep(1)
            
        raise Exception("Timeout waiting for SAP Cookies from Redis worker. Is the worker running?")

    def login(self) -> None:
        self.logger.info("SAP/Unilever Login Initiated (Via Desktop GUI Bot)")
        self.cookies.clear()
        
        new_cookies = self._get_cookies_from_redis()

        # new_cookies comes back as a list of dicts from the selenium driver
        for cookie in new_cookies:
            self.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])
            
        self.logger.info(f"Synced {len(new_cookies)} cookies! Verifying SAP Login...")
        
        if self.is_logged_in():
            self.logger.info("Logged in successfully to Unilever SAP")
            self.user.update_cookies(self.cookies)
        else:
            self.logger.error("Login Check failed immediately after cookie sync.")
            raise UnileverWrongCredentials("Failed to authenticate with Redis-provided cookies.")

    def _sap_odata_batch(self, service_url, requests_list):
        """
        Unified OData batch helper for Unilever SAP.
        Handles both GET and POST with automatic CSRF management.
        requests_list: list of dicts with {'method': 'GET'/'POST', 'url': '...', 'body': {...}}
        """
        
        batch_id = str(uuid.uuid4())[:8]
        batch_boundary = f"batch_{batch_id}"
        
        # 1. CSRF Logic (Only if POST is present)
        has_post = any(r.get('method', 'GET').upper() == 'POST' for r in requests_list)
        csrf_token = None
        if has_post:
            csrf_token = self._get_csrf_token(service_url)
            
        headers = {
            'Accept': 'multipart/mixed',
            'Accept-Language': 'en',
            'Connection': 'keep-alive',
            'Content-Type': f'multipart/mixed;boundary={batch_boundary}',
            'DataServiceVersion': '2.0',
            'MaxDataServiceVersion': '2.0',
            'Origin': 'https://web3.inpartner.unilever.com',
            'Referer': 'https://web3.inpartner.unilever.com/sap/bc/ui5_ui5/sap/zpmodel/index.html?sap-client=100&sap-language=EN',
            'sap-cancel-on-close': 'true',
            'sap-contextid-accept': 'header',
        }
        if csrf_token:
            headers['x-csrf-token'] = csrf_token

        # 2. Build Multipart Payload
        payload_lines = []
        for req in requests_list:
            method = req.get('method', 'GET').upper()
            inner_url = req.get('url')
            body = req.get('body')
            
            payload_lines.append(f"--{batch_boundary}")
            
            if method == 'POST':
                # POST requires a changeset boundary in SAP OData
                changeset_id = str(uuid.uuid4())[:8]
                changeset_boundary = f"changeset_{changeset_id}"
                
                payload_lines.extend([
                    f"Content-Type: multipart/mixed; boundary={changeset_boundary}",
                    "",
                    f"--{changeset_boundary}",
                    "Content-Type: application/http",
                    "Content-Transfer-Encoding: binary",
                    "",
                    f"POST {inner_url} HTTP/1.1",
                    "sap-contextid-accept: header",
                    "Content-Type: application/json",
                    "Accept: application/json",
                    "DataServiceVersion: 2.0",
                    "MaxDataServiceVersion: 2.0"
                ])
                if csrf_token:
                    payload_lines.append(f"x-csrf-token: {csrf_token}")
                
                if body:
                    body_str = json.dumps(body) if isinstance(body, dict) else body
                    payload_lines.append(f"Content-Length: {len(body_str)}")
                    payload_lines.append("")
                    payload_lines.append(body_str)
                else:
                    payload_lines.append("")
                
                payload_lines.append(f"--{changeset_boundary}--")
            else:
                # GET is simpler
                payload_lines.extend([
                    "Content-Type: application/http",
                    "Content-Transfer-Encoding: binary",
                    "",
                    f"GET {inner_url} HTTP/1.1",
                    "Accept: application/json",
                    "DataServiceVersion: 2.0",
                    "MaxDataServiceVersion: 2.0",
                    "",
                    ""
                ])
                
        payload_lines.append(f"--{batch_boundary}--")
        payload_lines.append("")
        
        data = "\r\n".join(payload_lines)
        
        # 3. Execution
        if not service_url.startswith('http') and not service_url.startswith('/'):
            service_url = f"/{service_url}"
        full_url = f"{service_url}?sap-client=100" if "$batch" in service_url else f"{service_url}/$batch?sap-client=100"
        
        res = self.post(full_url, headers=headers, data=data)
        return res

    def _parse_sap_batch_response(self, res):
        """
        Parses a multipart SAP OData $batch response.
        Identifies boundaries, handles changesets, and extracts JSON payloads.
        Returns a list of dictionaries (the parsed JSON content).
        """
        import re
        import json

        content_type = res.headers.get('Content-Type', '')
        boundary_match = re.search(r'boundary=([\w-]+)', content_type)
        if not boundary_match:
            self.logger.warning("No boundary found in batch response Content-Type.")
            return []

        boundary = f"--{boundary_match.group(1)}"
        # Split body by boundary
        parts = res.text.split(boundary)
        
        results = []

        for part in parts:
            part = part.strip()
            if not part or part == '--':
                continue

            # Check for inner multipart (changeset)
            if 'multipart/mixed; boundary=' in part:
                inner_boundary_match = re.search(r'boundary=([\w-]+)', part)
                if inner_boundary_match:
                    inner_boundary = f"--{inner_boundary_match.group(1)}"
                    inner_parts = part.split(inner_boundary)
                    for ip in inner_parts:
                        ip = ip.strip()
                        if not ip or ip == '--': continue
                        json_data = self._extract_json_from_part(ip)
                        if json_data: results.append(json_data)
                continue

            # Direct application/http part
            json_data = self._extract_json_from_part(part)
            if json_data: results.append(json_data)

        return results

    def _extract_json_from_part(self, part_text):
        """Helper to find and parse JSON within a multipart segment"""
        import json
        # SAP JSON usually starts after an empty line (end of HTTP headers)
        # and starts with {"
        json_start = part_text.find('{"')
        if json_start != -1:
            try:
                # Find the end - usually indicated by boundary (which we already split on)
                # but might have trailing whitespace
                return json.loads(part_text[json_start:].strip())
            except Exception as e:
                self.logger.debug(f"Failed to parse JSON from part: {e}")
        return None

    def is_logged_in(self) -> bool:
        try:
            # Simplified check using direct GET instead of batch POST
            url = "/sap/opu/odata/sap/YNGW_GET_ORDERS_PNTR_SRV/UserInfo?sap-client=100"
            res = self.get(url)
            
            self.logger.debug(f"SAP Login Check Response: {res.status_code}")
            if res.status_code == 200 and self.username.upper() in res.text.upper():
                self.logger.info("SAP Login Check: Passed")
                return True
            else:
                self.logger.error(f"SAP Login Check: Failed (Status: {res.status_code})")
                return False
                
        except Exception as e:
            self.logger.error(f"SAP Login Check: Failed with Exception ({e})")
            return False

    def _get_csrf_token(self, service_url):
        """
        Fetches a CSRF token from the specified SAP service.
        """
        headers = {
            "x-csrf-token": "fetch",
            "Referer": "https://web3.inpartner.unilever.com/sap/bc/ui5_ui5/sap/zpmodel/index.html?sap-client=100&sap-language=EN",
        }
        # Use GET to fetch the token
        full_url = f"{service_url}?sap-client=100" if service_url.startswith('http') else f"{service_url}?sap-client=100"
        res = self.get(full_url, headers=headers)
        token = res.headers.get("x-csrf-token")
        if not token:
            self.logger.error(f"Failed to fetch CSRF token for {service_url}")
        return token

    def ledger(self, from_date: datetime.date, to_date: datetime.date):
        """
        Fetches the customer ledger from SAP for a given date range.
        Args:
            from_date: datetime.date object
            to_date: datetime.date object
        """
        import urllib.parse
        import pandas as pd

        # Format dates as DD.MM.YYYY for SAP OData filter
        from_str = from_date.strftime("%d.%m.%Y")
        to_str = to_date.strftime("%d.%m.%Y")

        self.logger.info(f"Fetching SAP Ledger: {from_str} to {to_str}")
        
        filter_str = f"CompanyCode eq 'H' and Clerk eq '' and GLInd eq '' and (Date ge '{from_str}' and Date le '{to_str}') and Background eq ''"
        encoded_filter = urllib.parse.quote(filter_str)
        
        service = "/sap/opu/odata/sap/YNWG_CUSTOMER_LEDGER_SRV"
        inner_url = f"LedgerSet?sap-client=100&$filter={encoded_filter}"
        
        batch_res = self._sap_odata_batch(service, [{'method': 'GET', 'url': inner_url}])
        parsed_data = self._parse_sap_batch_response(batch_res)
        
        if not parsed_data:
            self.logger.error("Could not parse data from SAP Ledger response.")
            return pd.DataFrame()

        # Ledger usually has one response part
        data = parsed_data[0]
        results = data.get('d', {}).get('results', [])
        if not results:
            results = data.get('d', {})
            if isinstance(results, dict):
                results = [results] if results else []

        df = pd.DataFrame(results)
        if not df.empty and '__metadata' in df.columns:
            df = df.drop(columns=['__metadata'])
            
        self.logger.info(f"Retrieved {len(df)} ledger records.")
        return df

    def ilm_pdf(self, month: int, year: int):
        """
        Fetches ILM documents for a given month and year.
        Returns a list of dicts: {"doc_no": str, "date": datetime.date, "pdf": BytesIO}
        """
        from io import BytesIO

        last_day = calendar.monthrange(year, month)[1]
        from_date = f"{year}{month:02d}01"
        to_date = f"{year}{month:02d}{last_day:02d}"

        self.logger.info(f"Starting ILM PDF fetch for {month}/{year} ({from_date} to {to_date})")
        
        service = "/sap/opu/odata/sap/YNGW_NEW_ORDER_PAGE_SRV"
        
        payload = {
            "Fromdate": from_date,
            "ToDate": to_date,
            "Nav_ILMinput_to_display": [],
            "Nav_ILMinput_to_message": []
        }

        # Use unified batch helper
        batch_res = self._sap_odata_batch(service, [{
            'method': 'POST',
            'url': 'ILMInputSet?sap-client=100',
            'body': payload
        }])
        
        parsed_data = self._parse_sap_batch_response(batch_res)
        if not parsed_data:
            self.logger.error("No data parsed from ILM batch response.")
            return []

        # ILM usually has the display items in the first parsed part
        result_data = parsed_data[0]
        documents_metadata = result_data.get('d', {}).get('Nav_ILMinput_to_display', {}).get('results', [])
        self.logger.info(f"Found {len(documents_metadata)} ILM documents.")

        # 4. Download PDFs to Memory
        results = []
        for doc in documents_metadata:
            doc_id = doc.get('Document')
            doc_year = doc.get('Year')
            indicator = doc.get('indicator')
            doc_date_str = doc.get('Date') # Expected YYYYMMDD
            
            if not doc_id: continue
            
            # Parse date
            try:
                doc_date = datetime.date(int(doc_date_str[:4]), int(doc_date_str[4:6]), int(doc_date_str[6:8]))
            except:
                doc_date = None

            pdf_url = f"{service}/ILMPDFSet(year='{doc_year}',document='{doc_id}',indicator='{indicator}')/$value"
            self.logger.info(f"Downloading PDF for document {doc_id}...")
            
            try:
                pdf_res = self.get(pdf_url)
                if pdf_res.status_code == 200:
                    results.append({
                        "doc_no": doc_id,
                        "date": doc_date,
                        "pdf": BytesIO(pdf_res.content)
                    })
                else:
                    self.logger.error(f"Failed to download PDF for {doc_id}. Status: {pdf_res.status_code}")
            except Exception as e:
                self.logger.error(f"Exception downloading PDF for {doc_id}: {e}")

        self.logger.info(f"ILM PDF Fetch completed. Successfully downloaded {len(results)} PDFs to memory.")
        return results

    def post_orders(self, items, tonnage_volume=None):
        """
        Sends a batch POST request to OrderSet with the provided items.
        Returns the parsed JSON response parts.
        """
        service = "/sap/opu/odata/sap/YNGW_GET_ORDERS_PNTR_SRV"
        payload = {
            "imprestine": "",
            "ImPdp": "X",
            "ImSave": "X",
            "ImTonnage": "",
            "header_Item": items,
            "NpTonnageVolume": tonnage_volume if tonnage_volume is not None else [],
            "NpLog": []
        }
        
        self.logger.info(f"Posting {len(items)} orders to SAP...")
        res = self._sap_odata_batch(service, [{
            'method': 'POST',
            'url': 'OrderSet?sap-client=100',
            'body': payload
        }])
        
        return self._parse_sap_batch_response(res)
  