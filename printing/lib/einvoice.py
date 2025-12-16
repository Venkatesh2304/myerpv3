import datetime
from custom.classes import Ikea
from custom.classes import Einvoice
from django.db.models.aggregates import Max
from django.db.models.aggregates import Min
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
    is_einvoice_logged_in: bool = True

class EinvoiceHandler:
    def __init__(self, company):
        self.company = company

    def handle_upload(self, einv_qs) -> EinvoiceResult:

        ikea = Ikea(self.company.pk)
        einvoice_service = Einvoice(self.company.user.pk)
        if not einvoice_service.is_logged_in() : 
            return EinvoiceResult(success=False, error="E-Invoice service not logged in", is_einvoice_logged_in=False)
        
        # Django aggregate returns dict
        from_date = einv_qs.aggregate(d=Min("bill_date"))["d"]
        to_date = einv_qs.aggregate(d=Max("bill_date"))["d"]
        
        # Generate e-invoice JSON from IkeaDownloader
        inums = list(einv_qs.values_list("bill_id", flat=True))
        try:
            bytesio = ikea.einvoice_json(fromd=from_date, tod=to_date, bills=inums)
        except Exception as e:
            pass
            #TODO: Log error
            # return EinvoiceResult(success=False, error=f"Failed to generate e-invoice JSON from ikea: {e}", failed_inums=inums)

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
            err = "No data generated for e-invoice upload from ikea."

        try:
            today_einvs_bytesio = einvoice_service.get_filed_einvs(datetime.date.today())
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
