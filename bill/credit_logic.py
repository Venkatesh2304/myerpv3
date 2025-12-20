from .models import PartyCredit

class PartyCreditLogic:
    def __init__(self, company_id, party_ids):
        self.company_id = company_id
        # Pre-fetch only relevant credits
        self.credits = {
            pc.party_id: pc 
            for pc in PartyCredit.objects.filter(company_id=company_id, party_id__in=party_ids)
        }

    def _get_limits(self, party_id):
        credit = self.credits.get(party_id)
        if credit:
            return credit.bills, credit.days, credit.value
        return 1, 0, 0 # Defaults

    def check_bills(self, allocated_value, os_list, coll_list , limit_bills):
        if len(os_list) < limit_bills:
            return True
        elif len(os_list) == limit_bills : 
            max_collection_days = max([days for _,days in coll_list], default=0)
            max_outstanding_days = max([days for _,days in os_list], default=0)
            total_outstanding = sum([bal for bal,_ in os_list]) or 0
            if max(max_collection_days,max_outstanding_days) > 21 : 
                return False
            elif total_outstanding > 500 and allocated_value > 500 :
                return False
            else : 
                return True
        else : 
            return False
            
    def check_days(self, os_list, limit_days):
        max_outstanding_days = max([days for _,days in os_list], default=0)
        return (max_outstanding_days <= limit_days)

    def check_value(self, allocated_value, limit_value):
        return (allocated_value <= limit_value)

    def allow_order(self, party_id, os_list, coll_list, allocated_value):
        limit_bills, limit_days, limit_value = self._get_limits(party_id)
        
        is_bills_ok = self.check_bills(allocated_value, os_list, coll_list, limit_bills) if limit_bills > 0 else True
        is_days_ok = self.check_days(os_list, limit_days) if limit_days > 0 else True
        is_value_ok = self.check_value(allocated_value, limit_value) if limit_value > 0 else True
        warning = []
        if not is_days_ok : 
            warning.append(f"Days Exceeded : {limit_days}")
        if not is_value_ok : 
            warning.append(f"Value Exceeded : {limit_value}")
            
        return is_bills_ok and is_days_ok and is_value_ok, warning
