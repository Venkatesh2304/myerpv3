import pandas as pd
import io

def skiprows_excel(excel_file,col_name,col_number,sep) : 
    # Ensure file pointer is at start
    if hasattr(excel_file, 'seek'):
        excel_file.seek(0)
    elif hasattr(excel_file, 'file') and hasattr(excel_file.file, 'seek'):
        excel_file.file.seek(0)

    text_stream = io.TextIOWrapper(excel_file.file, encoding="utf-8", errors="replace")
    df = pd.read_csv(text_stream , skiprows=0 , sep=sep , names = list(range(0,100)) , header = None,engine="python")
    skiprows = -1 
    acc_no = None 
    for i in range(0,20) :   
        if df.iloc[i][col_number] == col_name : 
            skiprows = i 
            break
        x = df.iloc[i][0]
        if (type(x) == str) and ("account number" in x.lower()) :
            acc_no = df.iloc[i][1]
    
    if skiprows != -1:
        df.columns = df.iloc[skiprows]
        df = df.iloc[skiprows+1:]
    return df,acc_no 

class BankStatementParser:
    def parse(self, file_obj):
        raise NotImplementedError

class SBIParser(BankStatementParser):
    def parse(self, file_obj):
        df, acc_no = skiprows_excel(file_obj, "Txn Date", 0, "\t")
        if acc_no:
            acc_no = str(acc_no).strip("_").strip()
        
        # Rename columns
        df = df.rename(columns={"Txn Date":"date", "Credit":"amt", "Ref No./Cheque No.":"ref", "Description":"desc"})
        # Clean data
        df = df.iloc[:-1]
        df["date"] = pd.to_datetime(df["date"], format='%d %b %Y')
        return df, acc_no

class KVBParser(BankStatementParser):
    def parse(self, file_obj):
        df, acc_no = skiprows_excel(file_obj, "Transaction Date", 0, ",")
        if acc_no:
             # KVB specific cleaning
             acc_no = str(acc_no).replace('"', '').replace('=', '').strip()
        
        # Rename columns
        df = df.rename(columns={"Transaction Date":"date", "Credit":"amt", "Cheque No.":"ref", "Description":"desc"})
        # Clean data
        df["date"] = pd.to_datetime(df["date"], format='%d-%m-%Y %H:%M:%S')
        df = df.sort_values("date")
        df["ref"] = df["ref"].astype(str).str.split(".").str[0]
        return df, acc_no
