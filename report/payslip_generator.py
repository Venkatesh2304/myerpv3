import pandas as pd
import numpy as np
import calendar
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import zipfile
from fpdf import FPDF
import os

def count_sundays(year, month):
    cal = calendar.monthcalendar(year, month)
    return sum(1 for week in cal if week[calendar.SUNDAY] != 0)

def num_to_words(n):
    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
             "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    if n == 0:
        return "Zero"
    
    def convert_below_thousand(num):
        words = ""
        if num >= 100:
            words += units[num // 100] + " Hundred "
            num %= 100
        if num >= 20:
            words += tens[num // 10] + (" " + units[num % 10] if num % 10 != 0 else "")
        elif num > 0:
            words += units[num]
        return words.strip()
    
    parts = []
    if n >= 10000000:
        parts.append(convert_below_thousand(n // 10000000) + " Crore")
        n %= 10000000
    if n >= 100000:
        parts.append(convert_below_thousand(n // 100000) + " Lakh")
        n %= 100000
    if n >= 1000:
        parts.append(convert_below_thousand(n // 1000) + " Thousand")
        n %= 1000
    if n > 0:
        parts.append(convert_below_thousand(n))
        
    return "Indian Rupee " + " ".join(parts).strip() + " Only"

def get_weekly_periods(year, month, net_salary, base_salary=None, total_leaves=0, emp_name=None):
    num_days = calendar.monthrange(year, month)[1]
    
    # Collect all working days (Sunday = 6 strictly excluded)
    working_days = []
    for d in range(1, num_days + 1):
        cur_date = date(year, month, d)
        if cur_date.weekday() != 6:
            working_days.append(cur_date)
            
    total_calendar_working_days = len(working_days)
    
    # 1. Build weekly chunks (close on Saturday or month-end)
    raw_chunks = []
    current_chunk = []
    for cur_date in working_days:
        current_chunk.append(cur_date)
        if cur_date.weekday() == 5 or cur_date == working_days[-1]:
            raw_chunks.append({
                "start": current_chunk[0],
                "end": current_chunk[-1],
                "cal_days": len(current_chunk),
            })
            current_chunk = []
            
    # 2. Distribute leaves across chunks deterministically
    chunk_leaves = [0] * len(raw_chunks)
    leaves_to_distribute = min(max(0, int(total_leaves)), total_calendar_working_days)
    
    if leaves_to_distribute > 0 and raw_chunks:
        seed_val = sum(ord(c) for c in (emp_name or 'emp')) + year * 12 + month
        indices = list(range(len(raw_chunks)))
        # Sort indices: prioritize chunks with max working days (6 days)
        indices.sort(key=lambda idx: (-raw_chunks[idx]["cal_days"], (idx + seed_val) % len(raw_chunks)))
        
        assigned = 0
        while assigned < leaves_to_distribute:
            for idx in indices:
                if assigned >= leaves_to_distribute:
                    break
                if raw_chunks[idx]["cal_days"] - chunk_leaves[idx] > 1:
                    chunk_leaves[idx] += 1
                    assigned += 1
            if assigned < leaves_to_distribute:
                for idx in indices:
                    if assigned >= leaves_to_distribute:
                        break
                    if raw_chunks[idx]["cal_days"] - chunk_leaves[idx] > 0:
                        chunk_leaves[idx] += 1
                        assigned += 1
                break

    # 3. Calculate actual working days and pro-rated amount per chunk
    total_actual_working_days = sum(raw_chunks[i]["cal_days"] - chunk_leaves[i] for i in range(len(raw_chunks)))
    daily_rate = net_salary / total_actual_working_days if total_actual_working_days > 0 else 0
    
    periods = []
    for i, chk in enumerate(raw_chunks):
        c_leaves = chunk_leaves[i]
        c_working_days = chk["cal_days"] - c_leaves
        c_amount = round(daily_rate * c_working_days)
        start_d = chk["start"]
        end_d = chk["end"]
        periods.append({
            "start": start_d,
            "end": end_d,
            "period_str": f"{start_d.strftime('%d-%m-%Y')} to {end_d.strftime('%d-%m-%Y')}",
            "voucher_date": end_d.strftime('%d %b %y'),
            "working_days": c_working_days,
            "leaves": c_leaves,
            "amount": c_amount
        })
        
    # Reconcile rounding diff
    total_calc = sum(p["amount"] for p in periods)
    diff = round(net_salary - total_calc)
    if diff != 0 and periods:
        for p in reversed(periods):
            if p["working_days"] > 0:
                p["amount"] += diff
                break
                
    return periods

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
        
        if not emp_name: 
            continue
        
        current_date = start_date.replace(day=1)
        while current_date <= end_date:
            year = current_date.year
            month = current_date.month
            
            total_days = calendar.monthrange(year, month)[1]
            sundays = count_sundays(year, month)
            max_working_days = total_days - sundays
            
            # Random leaves (0, 1, or 2 days)
            leaves = int(np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1]))
            actual_worked_days = max(0, max_working_days - leaves)
            
            # Single pay: prorated net salary based on working days
            per_day_salary = base_salary / max_working_days if max_working_days > 0 else 0
            net_salary = round(per_day_salary * actual_worked_days)
            
            records.append({
                "Employee Name": emp_name,
                "Year": year,
                "Month": month,
                "Total Days": total_days,
                "Working Days": actual_worked_days,
                "Leaves": leaves,
                "Base Salary": base_salary,
                "Net Salary": net_salary
            })
            
            current_date += relativedelta(months=1)
            
    df = pd.DataFrame(records)
    
    if not df.empty:
        df.sort_values(by=["Employee Name", "Year", "Month"], inplace=True)
        with pd.ExcelWriter(output_filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            
    return output_filepath

class SalaryVoucherPDF(FPDF):
    def __init__(self, company_name=None, address_lines=None, gst_number=None):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.company_name = company_name or "DEVAKI ENTERPRISES,"
        self.address_lines = address_lines or [
            "F/4 INDUSTRIAL ESTATE,",
            "ARIYAMANGALAM, TRICHY - 620010"
        ]
        self.gst_number = gst_number or "33AAPFD1365C1ZR"
        self.set_auto_page_break(False)

    def draw_single_voucher(self, y_offset, voucher_date, emp_name, salary_period_str, working_days, leaves, amount):
        left = 18
        right = 192
        col_split = 145
        
        # 1. Company Header
        self.set_y(y_offset + 3)
        self.set_font('Helvetica', '', 10.5)
        self.cell(0, 4.2, self.company_name.upper(), 0, 1, 'C')
        
        self.set_font('Helvetica', '', 9)
        for line in self.address_lines:
            self.cell(0, 4.0, line.upper(), 0, 1, 'C')
            
        if self.gst_number:
            self.cell(0, 4.0, f"GSTIN : {self.gst_number}", 0, 1, 'C')
            
        # 2. Title: Salary Voucher
        self.ln(1.5)
        self.set_font('Helvetica', '', 10.5)
        self.cell(0, 5, "Salary Voucher", 0, 1, 'C')
        
        # 3. Dated (Last day of salary period)
        self.ln(1.5)
        y_meta = self.get_y()
        self.set_font('Helvetica', '', 9)
        self.set_xy(138, y_meta)
        self.cell(20, 4.5, "Dated :", 0, 0, 'L')
        self.set_xy(160, y_meta)
        self.cell(right - 160, 4.5, voucher_date, 0, 1, 'R')
        
        # 4. Table Header
        self.ln(1.5)
        tbl_top = self.get_y()
        self.set_line_width(0.2)
        self.line(left, tbl_top, right, tbl_top)
        
        header_h = 5.0
        self.set_xy(left + 2, tbl_top)
        self.set_font('Helvetica', '', 8.5)
        self.cell(col_split - left - 2, header_h, "Particulars", 0, 0, 'L')
        self.set_xy(col_split, tbl_top)
        self.cell(right - col_split - 2, header_h, "Amount", 0, 0, 'R')
        
        header_bottom = tbl_top + header_h
        self.line(left, header_bottom, right, header_bottom)
        
        # Table Body
        body_y = header_bottom + 3
        # Employee Name (Bold)
        self.set_xy(left + 2, body_y)
        self.set_font('Helvetica', 'B', 8.5)
        self.cell(col_split - left - 4, 4, emp_name.upper(), 0, 0, 'L')
        
        # Amount on right
        self.set_xy(col_split, body_y)
        self.set_font('Helvetica', '', 8.5)
        amt_str = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
        self.cell(right - col_split - 2, 4, amt_str, 0, 1, 'R')
        
        # Salary period
        self.set_xy(left + 4, self.get_y() + 0.5)
        self.set_font('Helvetica', 'B', 8.5)
        self.cell(col_split - left - 6, 4, f"Salary for {salary_period_str}", 0, 1, 'L')
        
        # Working days & Leaves
        self.set_xy(left + 4, self.get_y() + 0.5)
        self.set_font('Helvetica', '', 8.5)
        self.cell(col_split - left - 6, 4, f"Working days : {working_days}    Leaves : {leaves}", 0, 1, 'L')
        
        # Amount in words
        self.ln(10)
        self.set_x(left + 2)
        self.set_font('Helvetica', '', 8.5)
        self.cell(0, 4, "Amount (in words) :", 0, 1, 'L')
        self.set_x(left + 2)
        self.cell(0, 4, num_to_words(int(amount)), 0, 1, 'L')
        
        # Total Row & Bottom lines
        tbl_bottom_content_y = y_offset + 97
        self.line(left, tbl_bottom_content_y, right, tbl_bottom_content_y)
        
        total_h = 5.0
        self.set_xy(col_split, tbl_bottom_content_y)
        self.set_font('Helvetica', '', 8.5)
        self.cell(right - col_split - 2, total_h, amt_str, 0, 1, 'R')
        
        tbl_end_y = tbl_bottom_content_y + total_h
        self.line(left, tbl_end_y, right, tbl_end_y)
        
        # Vertical divider line
        self.line(col_split, tbl_top, col_split, tbl_end_y)
        
        # Signatures: Employee Signature left, Employer Signature right
        sig_y = tbl_end_y + 10
        self.set_font('Helvetica', '', 8.5)
        self.set_xy(left + 2, sig_y)
        self.cell(60, 4.5, "Employee Signature", 0, 0, 'L')
        
        self.set_xy(right - 60, sig_y)
        self.cell(60, 4.5, "Employer Signature", 0, 1, 'R')

    def add_two_vouchers_page(self, v1_data, v2_data=None):
        self.add_page()
        self.draw_single_voucher(
            y_offset=5,
            voucher_date=v1_data['voucher_date'],
            emp_name=v1_data['emp_name'],
            salary_period_str=v1_data['period_str'],
            working_days=v1_data['working_days'],
            leaves=v1_data['leaves'],
            amount=v1_data['amount']
        )
        
        if v2_data:
            self.draw_single_voucher(
                y_offset=150,
                voucher_date=v2_data['voucher_date'],
                emp_name=v2_data['emp_name'],
                salary_period_str=v2_data['period_str'],
                working_days=v2_data['working_days'],
                leaves=v2_data['leaves'],
                amount=v2_data['amount']
            )

def generate_pdf_zip(queryset, output_filepath, company_name=None, company_address=None):
    df = pd.DataFrame(list(queryset.values(
        'employee_name', 'year', 'month', 'total_days', 'working_days', 
        'leaves', 'base_salary', 'net_salary'
    )))
    
    if df.empty:
        with zipfile.ZipFile(output_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("empty.txt", "No records found.")
        return output_filepath

    c_name = "DEVAKI ENTERPRISES,"
    address_lines = [
        "F/4 INDUSTRIAL ESTATE,",
        "ARIYAMANGALAM, TRICHY - 620010"
    ]
    gst_num = "33AAPFD1365C1ZR"
    
    with zipfile.ZipFile(output_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, row in df.iterrows():
            year = int(row['year'])
            month = int(row['month'])
            emp_name = str(row['employee_name'])
            net_salary = float(row['net_salary'])
            base_salary = float(row.get('base_salary', net_salary))
            working_days = int(row.get('working_days', 0))
            leaves = int(row.get('leaves', 0))
            
            total_days = int(row.get('total_days', calendar.monthrange(year, month)[1]))
            sundays = count_sundays(year, month)
            max_working_days = total_days - sundays
            
            if leaves == 0 and working_days > 0 and working_days < max_working_days:
                leaves = max_working_days - working_days
            if working_days == 0:
                working_days = max_working_days - leaves
            
            periods = get_weekly_periods(
                year=year,
                month=month,
                net_salary=net_salary,
                base_salary=base_salary,
                total_leaves=leaves,
                emp_name=emp_name
            )
            
            pdf = SalaryVoucherPDF(
                company_name=c_name,
                address_lines=address_lines,
                gst_number=gst_num
            )
            
            voucher_items = []
            for p in periods:
                voucher_items.append({
                    "emp_name": emp_name,
                    "voucher_date": p["voucher_date"],
                    "period_str": p["period_str"],
                    "working_days": p["working_days"],
                    "leaves": p["leaves"],
                    "amount": p["amount"]
                })
                
            for i in range(0, len(voucher_items), 2):
                v1 = voucher_items[i]
                v2 = voucher_items[i+1] if i+1 < len(voucher_items) else None
                pdf.add_two_vouchers_page(v1, v2)
                
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            
            month_str = calendar.month_abbr[month]
            emp_safe = "".join([c if c.isalnum() else "_" for c in emp_name])
            filename = f"{year}_{month:02d}_{month_str}_{emp_safe}_weekly_salary_vouchers.pdf"
            zf.writestr(filename, pdf_bytes)

    return output_filepath
