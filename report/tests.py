from django.test import TransactionTestCase
from report.models import ReportSyncLog, SalesRegisterReport
from core.models import Company, User
from django.utils import timezone
from datetime import timedelta
import pandas as pd
from unittest.mock import MagicMock

class ReportSyncLogTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.company = Company.objects.create(name="testcompany", user=self.user)

    def test_log_creation_and_update(self):
        # 1. Initial State: No log
        oldness = ReportSyncLog.get_oldness(SalesRegisterReport, identifier=self.company.pk)
        self.assertIsNone(oldness)

        # 2. Update Log
        ReportSyncLog.update_log(SalesRegisterReport, identifier=self.company.pk)
        
        # 3. Verify Log Exists
        log = ReportSyncLog.objects.get(report_name="SalesRegisterReport", identifier=self.company.pk)
        self.assertIsNotNone(log.last_updated)
        
        # 4. Verify Oldness
        oldness = ReportSyncLog.get_oldness(SalesRegisterReport, identifier=self.company.pk)
        self.assertIsNotNone(oldness)
        self.assertLess(oldness, timedelta(seconds=1))

    def test_integration_with_update_db(self):
        # Mock fetcher and dataframe
        mock_fetcher = MagicMock()
        mock_df = pd.DataFrame({
            "BillRefNo": ["B1"],
            "BillDate/Sales Return Date": ["2023-01-01"],
            "Party Code": ["P1"],
            "Party Name": ["Party1"],
            "Beat": ["Beat1"],
            "BillValue": [100.0],
            "CR Adj": [0.0],
            "GSTIN Number": ["GST1"],
            "TCS Amt": [0.0],
            "TDS-194R Per": [0.0],
            "Tax Amt": [10.0],
            "SRT Tax": [0.0],
            "SchDisc": [0.0],
            "CashDisc": [0.0],
            "BTPR SchDisc": [0.0],
            "OutPyt Adj": [0.0],
            "Ushop Redemption": [0.0],
            "Adjustments": [0.0],
            "DisFin Adj": [0.0],
            "Reversed Payouts": [0.0],
            "RoundOff": [0.0],
            "type": ["sales"],
            "amt": [100.0],
            "tax": [10.0],
            "other_discount": [0.0],
            "inum": ["B1"],
            "date": ["2023-01-01"],
            "party_id": ["P1"],
            "party_name": ["Party1"],
            "beat": ["Beat1"],
            "ctin": ["GST1"],
            "tcs": [0.0],
            "tds": [0.0],
            "schdisc": [0.0],
            "cashdisc": [0.0],
            "btpr": [0.0],
            "outpyt": [0.0],
            "ushop": [0.0],
            "pecom": [0.0],
            "roundoff": [0.0]
        })
        
        # Mock get_dataframe to return processed df directly to avoid complex mocking of fetcher
        original_get_dataframe = SalesRegisterReport.Report.get_dataframe
        SalesRegisterReport.Report.get_dataframe = MagicMock(return_value=SalesRegisterReport.Report.custom_preprocessing(mock_df))

        # Call update_db
        from report.models import DateRangeArgs
        import datetime
        args = DateRangeArgs(fromd=datetime.date(2023, 1, 1), tod=datetime.date(2023, 1, 1))
        SalesRegisterReport.update_db(mock_fetcher, self.company, args)

        # Verify Log Updated
        oldness = ReportSyncLog.get_oldness(SalesRegisterReport, identifier=self.company.pk)
        self.assertIsNotNone(oldness)
        
        # Restore original method
        SalesRegisterReport.Report.get_dataframe = original_get_dataframe

    def test_convenience_get_oldness(self):
        # 1. Initial State: No log
        self.assertIsNone(SalesRegisterReport.get_oldness(self.company))

        # 2. Update Log via update_log (simulating update_db)
        ReportSyncLog.update_log(SalesRegisterReport, identifier=self.company.pk)

        # 3. Verify Oldness via convenience method
        oldness = SalesRegisterReport.get_oldness(self.company)
        self.assertIsNotNone(oldness)
        self.assertLess(oldness, timedelta(seconds=1))

    def test_user_report_convenience_get_oldness(self):
        from report.models import GSTR1Portal
        # 1. Initial State: No log
        self.assertIsNone(GSTR1Portal.get_oldness(self.user))

        # 2. Update Log
        ReportSyncLog.update_log(GSTR1Portal, identifier=self.user.pk)

        # 3. Verify Oldness
        oldness = GSTR1Portal.get_oldness(self.user)
        self.assertIsNotNone(oldness)
        self.assertLess(oldness, timedelta(seconds=1))
