import pandas as pd
import numpy as np
import calendar
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io
import zipfile
from fpdf import FPDF
import os

def count_sundays(year, month):
    cal = calendar.monthcalendar(year, month)
    return sum(1 for week in cal if week[calendar.SUNDAY] != 0)

def generate_rough_excel(employees_data, start_period, end_period, output_filepath):
    """
    employees_data: List of dicts [{'name': 'John', 'salary': 25000}]
    start_period: str 'YYYY-MM'
    end_period: str 'YYYY-MM'
    """
    start_date = datetime.strptime(start_period, "%Y-%m")
    end_date = datetime.strptime(end_period, "%Y-%m")
    
    end_date = end_date.replace(day=calendar.monthrange(end_date.year, end_date.month)[1])
    
    records = []
    
    for emp in employees_data:
        emp_name = emp.get('name', '').strip()
        base_salary = float(emp.get('salary', 0))
        
        if not emp_name: continue
        
        current_date = start_date.replace(day=1)
        while current_date <= end_date:
            year = current_date.year
            month = current_date.month
            
            total_days = calendar.monthrange(year, month)[1]
            sundays = count_sundays(year, month)
            max_working_days = total_days - sundays
            
            # Random leaves (0 to 2 days)
            leaves = np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])
            actual_worked_days = max_working_days - leaves
            
            monthly_base = base_salary
            
            # Prorate based on max_working_days
            per_day_salary = monthly_base / max_working_days if max_working_days > 0 else 0
            actual_base_pay = int(per_day_salary * actual_worked_days)
            
            # Small bonus
            bonus = np.random.choice([0, 500, 1000], p=[0.5, 0.3, 0.2])
            total_pay = actual_base_pay + bonus
            
            records.append({
                "Employee Name": emp_name,
                "Year": year,
                "Month": month,
                "Total Days": total_days,
                "Working Days": actual_worked_days,
                "Base Salary": monthly_base,
                "Calculated Pay": actual_base_pay,
                "Bonus": bonus,
                "Net Salary": total_pay
            })
            
            current_date += relativedelta(months=1)
            
    df = pd.DataFrame(records)
    
    if not df.empty:
        df.sort_values(by=["Employee Name", "Year", "Month"], inplace=True)
        with pd.ExcelWriter(output_filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            
    return output_filepath

class PayslipPDF(FPDF):
    def __init__(self, company_name, company_address):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.company_name = company_name or "DEVAKI ENTERPRISES"
        self.company_address = company_address or "ARIYAMANGALAM, TIRUCHIRAPPALLI, TAMIL NADU - 620010."

    def add_payslip(self, emp_name, period_str, total_days, days_worked, base_salary, bonus, net_salary, wage_per_day, earned_salary):
        self.add_page()
        # Border
        self.rect(10, 10, 190, 130)
        
        self.set_font('Arial', 'B', 14)
        self.cell(0, 8, 'PAYMENT OF WAGES ACT, 1936', 0, 1, 'C')
        
        self.set_font('Arial', '', 10)
        self.cell(0, 6, 'FORM VI', 0, 1, 'C')
        self.cell(0, 6, '(Prescribed under The Tamil Nadu Payment of Wages Rules, 1937)', 0, 1, 'C')
        self.ln(2)
        
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, 'WAGE SLIP', 0, 1, 'C')
        
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, f'{self.company_name}', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 6, f'{self.company_address}', 0, 1, 'C')
        self.ln(5)
        
        # Details
        self.set_font('Arial', 'B', 10)
        self.cell(40, 8, 'Employee Name:', 0, 0, 'L')
        self.set_font('Arial', '', 10)
        self.cell(60, 8, emp_name, 0, 0, 'L')
        
        self.set_font('Arial', 'B', 10)
        self.cell(40, 8, 'Wage Period:', 0, 0, 'L')
        self.set_font('Arial', '', 10)
        self.cell(50, 8, period_str, 0, 1, 'L')
        
        self.set_font('Arial', 'B', 10)
        self.cell(40, 8, 'Total Days/Month:', 0, 0, 'L')
        self.set_font('Arial', '', 10)
        self.cell(60, 8, str(total_days), 0, 0, 'L')
        
        self.set_font('Arial', 'B', 10)
        self.cell(40, 8, 'Days Worked:', 0, 0, 'L')
        self.set_font('Arial', '', 10)
        self.cell(50, 8, str(days_worked), 0, 1, 'L')
        
        self.ln(5)
        
        # Table
        self.set_font('Arial', 'B', 10)
        self.cell(95, 8, 'EARNINGS', 1, 0, 'C')
        self.cell(95, 8, 'DEDUCTIONS', 1, 1, 'C')
        
        self.set_font('Arial', '', 10)
        
        # Row 1
        self.cell(65, 8, 'Basic Rate per day', 'L', 0, 'L')
        self.cell(30, 8, f'Rs. {wage_per_day:.2f}', 'R', 0, 'R')
        self.cell(65, 8, 'Advances', 'L', 0, 'L')
        self.cell(30, 8, 'Rs. 0.00', 'R', 1, 'R')
        
        # Row 2
        self.cell(65, 8, 'Earned Basic Salary', 'L', 0, 'L')
        self.cell(30, 8, f'Rs. {earned_salary:.2f}', 'R', 0, 'R')
        self.cell(65, 8, 'Loss / Damage', 'L', 0, 'L')
        self.cell(30, 8, 'Rs. 0.00', 'R', 1, 'R')
        
        # Row 3
        self.cell(65, 8, 'Bonus / Allowances', 'L', 0, 'L')
        self.cell(30, 8, f'Rs. {bonus:.2f}', 'R', 0, 'R')
        self.cell(65, 8, 'Other Deductions', 'L', 0, 'L')
        self.cell(30, 8, 'Rs. 0.00', 'R', 1, 'R')
        
        # Totals
        self.set_font('Arial', 'B', 10)
        self.cell(65, 8, 'Gross Earnings', 'L,T,B', 0, 'L')
        self.cell(30, 8, f'Rs. {net_salary:.2f}', 'R,T,B', 0, 'R')
        self.cell(65, 8, 'Total Deductions', 'L,T,B', 0, 'L')
        self.cell(30, 8, 'Rs. 0.00', 'R,T,B', 1, 'R')
        
        self.ln(5)
        self.set_font('Arial', 'B', 11)
        self.cell(100, 8, f'Net Amount Payable: Rs. {net_salary:.2f}', 0, 1, 'L')
        
        self.ln(20)
        self.set_font('Arial', 'B', 10)
        self.cell(95, 8, 'Signature of Employer', 0, 0, 'L')
        self.cell(95, 8, 'Signature of Employee', 0, 1, 'R')

def generate_pdf_zip(queryset, output_filepath, company_name=None, company_address=None):
    """
    Generates PDFs based on a Django QuerySet of PayslipRecord objects.
    Writes a zipfile to output_filepath containing one PDF per employee per month.
    """
    df = pd.DataFrame(list(queryset.values(
        'employee_name', 'year', 'month', 'total_days', 'working_days', 
        'base_salary', 'calculated_pay', 'bonus', 'net_salary'
    )))
    
    if df.empty:
        with zipfile.ZipFile(output_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("empty.txt", "No records found.")
        return output_filepath
        
    with zipfile.ZipFile(output_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            year = int(row['year'])
            month = int(row['month'])
            emp_name = str(row['employee_name'])
            
            last_day = calendar.monthrange(year, month)[1]
            period_str = f"01/{month:02d}/{year} to {last_day}/{month:02d}/{year}"
            
            days_in_month = int(row['total_days'])
            sundays = count_sundays(year, month)
            max_working_days = days_in_month - sundays
            
            days_worked = int(row['working_days'])
            base_salary = float(row['base_salary'])
            
            wage_per_day = round(base_salary / max_working_days, 2) if max_working_days > 0 else 0
            
            calculated_pay = float(row['calculated_pay'])
            bonus = float(row['bonus'])
            net = float(row['net_salary'])
            
            pdf = PayslipPDF(company_name, company_address)
            pdf.add_payslip(emp_name, period_str, days_in_month, days_worked, base_salary, bonus, net, wage_per_day, calculated_pay)
            
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            
            month_str = calendar.month_abbr[month]
            emp_safe = "".join([c if c.isalnum() else "_" for c in emp_name])
            filename = f"{year}_{month:02d}_{month_str}_{emp_safe}.pdf"
            zf.writestr(filename, pdf_bytes)

    return output_filepath
