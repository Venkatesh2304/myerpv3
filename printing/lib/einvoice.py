from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
from custom.classes import IkeaDownloader
import pandas as pd
from io import BytesIO
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from bill.models import Bill
from custom.classes import Billing

@dataclass
class EinvoiceResult:
    success: bool
    error: Optional[str] = None
    failed_inums: List[str] = field(default_factory=list)

class EinvoiceHandler:
    def __init__(self, company):
        self.company = company

    def handle_upload(self, einvoice_service, einv_qs) -> EinvoiceResult:
        ikea = IkeaDownloader(self.company.user.pk)
        
        # Django aggregate returns dict
        from_date = einv_qs.aggregate(d=Min("bill_date"))["d"]
        to_date = einv_qs.aggregate(d=Max("bill_date"))["d"]
        
        if not from_date or not to_date:
             return EinvoiceResult(success=False, error="No dates found for bills")

        # Generate e-invoice JSON from IkeaDownloader
        inums = list(einv_qs.values_list("bill_id", flat=True))
        try:
            bytesio = ikea.einvoice_json(fromd=from_date, tod=to_date, bills=inums)
        except Exception as e:
            return EinvoiceResult(success=False, error=f"Failed to generate e-invoice JSON: {e}", failed_inums=inums)

        err = ""
        failed_inums = []
        
        if bytesio:
            try:
                json_str = bytesio.getvalue().decode('utf-8')
                success, failures = einvoice_service.upload(json_str)
                if failures is not None and not failures.empty:
                     failed_inums = failures["Invoice No"].tolist()
                     err = f"E-Invoice upload failed for {failed_inums}"
            except Exception as e:
                return EinvoiceResult(success=False, error=f"Upload service failed: {e}", failed_inums=inums)
        else:
            failed_inums = inums
            err = "No data generated for e-invoice upload."

        try:
            today_einvs_bytesio = BytesIO(einvoice_service.get_today_einvs())
            response = ikea.upload_irn(today_einvs_bytesio)
            
            if not response.get("valid"):
               pass 

            einvoice_df = pd.read_excel(today_einvs_bytesio)
            for _, row in einvoice_df.iterrows():
                # Update IRN in DB
                Bill.objects.filter(company=self.company, bill_id=str(row["Doc No"]).strip()).update(irn=str(row["IRN"]).strip())
            
            processed_bills = einvoice_df["Doc No"].values
            failed_inums = list(set(failed_inums) - set(processed_bills))
            
        except Exception as e:
             if not err:
                 err = f"Error syncing IRN: {e}"

        return EinvoiceResult(success=(err == ""), error=err, failed_inums=failed_inums)
