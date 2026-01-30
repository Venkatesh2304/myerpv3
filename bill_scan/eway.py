from typing import Callable
import json
import numpy as np
import pandas as pd

class NpEncoder(json.JSONEncoder):
    """
    Custom JSON Encoder that converts non-serializable types like numpy int64, float64,
    pandas Timestamp, etc., to their Python native equivalents.
    """
    def default(self, obj):
        if isinstance(obj, (np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float32)):
            return round(float(obj),2)
        return super(NpEncoder, self).default(obj)
    
def eway_df_to_json(df,vehicle_no: Callable[[pd.Series],pd.Series],
                       distance: Callable[[pd.Series],pd.Series] ,default_pincode = 620008):
    df['Doc date'] = df['Doc date'].dt.strftime("%d/%m/%Y")
    df["CGST Rate"] = df["Tax Rate"].str.split("+").str[0].astype(float)
    df["SGST Rate"] = df["Tax Rate"].str.split("+").str[1].astype(float)
    df["To_Pin_code"] = df["To_Pin_code"].fillna(default_pincode)
    df["Distance level(Km)"] = distance(df["To_Pin_code"])
    df["Vehicle No"] = vehicle_no(df["Doc.No"])

    grouped = df.groupby('Doc.No')

    eway_json = {
        "version": "1.0.0621",
        "billLists": []
    }

    for doc_no, group in grouped:
        if doc_no is None:
            continue
        row = group.iloc[0]
        bill_json = {
            "userGstin": row['From_GSTIN'],
            "supplyType": "O",
            "subSupplyType": 1,
            "subSupplyDesc": "",
            "docType":  "INV", 
            "docNo": doc_no,
            "docDate": row['Doc date'],
            "transType": 1,
            
            "fromGstin": row['From_GSTIN'],
            "fromTrdName": row['From Otherparty Name'] ,
            "fromAddr1": row["From_Address1"],
            "fromAddr2": row["From_Address2"],
            "fromPlace": row["From_Place"] ,    
            "fromPincode": int(row['From_pin_code']),  
            "fromStateCode": 33 ,  
            "actualFromStateCode": 33 , 
            
            "toGstin": row['To_GSTIN'],
            "toTrdName": row['To Otherparty Name'] ,
            "toAddr1": row["To_Address1"],
            "toAddr2": row["To_Address2"],
            "toPincode": int(row['To_Pin_code']), 
            "toStateCode": 33 ,  
            "actualToStateCode": 33, 
            
            "totalValue": round(group['Assessable Value'].round(2).sum(),2),
            "cgstValue": round(group['CGST Amount'].sum(),2) ,
            "sgstValue": round(group['SGST Amount'].sum(),2),
            "OthValue": round(row['TCS Amount'],2),
            "totInvValue": round(row['Total Amount'],2),
            
            "transMode": 1,
            "transDistance": int(row['Distance level(Km)']),
            "transporterName": "",
            "transporterId": "",
            "transDocNo": doc_no,
            "transDocDate": row['Doc date'] ,
            "vehicleNo": row['Vehicle No'],
            "vehicleType": "R",
            "itemList": []
        }
        index = 1
        for _, item in group.iterrows():
            hsn = str(item['HSN']).split(".")[0]
            hsn = "0"*(8-len(hsn)) + hsn
            item_json = {
                "itemNo": index,
                "hsnCode": hsn ,
                "quantity": int(item['Qty']),
                "qtyUnit": "PCS",
                "taxableAmount": round(float(item['Assessable Value']),2),
                "cgstRate": round(item['CGST Rate'],1),
                "sgstRate": round(item['SGST Rate'],1),
                "igstRate": 0 ,
                "cessRate": 0 ,
            }
            bill_json['itemList'].append(item_json)
            index += 1 
        
        eway_json['billLists'].append(bill_json)

    return json.dumps(eway_json,cls=NpEncoder, indent=4)

