from custom.pdf.base import BaseTablePDF
import pandas as pd
from typing import Tuple, Dict, Any, List
from enum import Enum
import datetime
import os
from io import BytesIO
import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

class LoadingSheetType(Enum):
    Salesman = "Salesman"
    Plain = "Plain"

class LoadingSheetPDF(BaseTablePDF):
    def generate(self, tables: Tuple[pd.DataFrame, pd.DataFrame], sheet_type: LoadingSheetType, context: Dict[str, Any] = None, output_dir: str = ".") -> str:
        if context is None:
            context = {}
            
        df, party_sales = tables 
        df = df.dropna(subset=["Sr No"]) # Assuming Sr No is the column name
        
        # Safe string manipulation
        df["MRP"] = df["MRP"].astype(str).str.split(".").str[0]
        df["LC"] = df["Total LC.Units"].astype(str).str.split(".").str[0]
        df["Units"] = df["Total LC.Units"].astype(str).str.split(".").str[1]
        df = df.rename(columns={"Total FC": "FC", "Total Gross Sales": "Gross Value"})

        total_fc = df["FC"].iloc[-1]
        total_lc = df["LC"].iloc[-1]
        df = df.fillna("")
        df["No"] = df.reset_index(drop=True).index + 1    
        df[["FC","LC"]] = df[["FC","LC"]].replace({"0" : ""})
        df = df.iloc[:-1] # Remove total row
        
        # Ensure columns exist
        cols_to_keep = ["No","Product Name", "MRP", "FC", "Units", "LC","UPC", "Gross Value","Division Name"]
        df = df[[c for c in cols_to_keep if c in df.columns]]

        party_sales = party_sales.dropna(subset=["Party"])
        party_sales = party_sales.sort_values("Bill No")
        party_sales = party_sales.fillna("")
        party_sales["No"] = party_sales.reset_index(drop=True).index + 1    
        party_sales = party_sales[["No","Bill No","Party","Gross Amount","Sch.Disc","Net Amt"]]
        
        no_of_bills = len(party_sales.index) - 1 
        outlet_count = party_sales["Party"].nunique() - 1
        lines_count = len(df.index)
        time_str = datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p") 
        try:
            net_total_value = round(float(party_sales.iloc[-1]["Net Amt"]))
        except (ValueError, IndexError):
            net_total_value = 0
        
        try:
            gross_total_value = round(float(party_sales.iloc[-1]["Gross Amount"]))
        except (ValueError, IndexError):
            gross_total_value = 0

        net_total_value_str = f"Rs. {net_total_value}"
        gross_total_value_str = f"Rs. {gross_total_value}"

        # Setup PDF
        self.set_top_margin(15)
        self.set_auto_page_break(auto=True, margin=5)
        self.set_font('Arial', '', 10)
        self.add_page()
        header_table_data = []

        dfs = []

        if sheet_type == LoadingSheetType.Salesman:
            self.cell(0, 10, "DEVAKI ENTERPRISES", 0, 0, 'L')
            self.ln()        
            header_table_data.append(["TIME", time_str, "", "", "VALUE", net_total_value_str])
            header_table_data.append(["SALESMAN", context.get("salesman", ""), "", "", "BEAT", context.get("beat", "")])
            party_val = (context.get("party") or "SALESMAN").ljust(34).upper()
            
            try:
                total_case = str(int(total_fc or "0") + int(total_lc or "0"))
            except ValueError:
                total_case = "0"
                
            header_table_data.append(["PARTY", party_val, "", "", "TOTAL CASE", total_case])
            header_table_data.append(["BILL", context.get("inum", ""), "", "", "PHONE", "9944833444"])
            
            def calculate_case(row):
                fc = int(row["FC"]) if row["FC"] else 0
                lc = int(row["LC"]) if row["LC"] else 0
                return str(fc + lc) if (fc + lc) > 0 else ""

            df["Case"] = df.apply(calculate_case, axis=1)
            
            dfs = df[["No", "Product Name", "MRP", "Case", "Units", "UPC", "Gross Value"]]
            # Add total row manually
            dfs.loc[len(dfs.index)] = ["", "Total"] + [""] * 4 + [gross_total_value_str]
            
        elif sheet_type == LoadingSheetType.Plain:
            header_table_data.append(["TIME", time_str, "", "", "BILLS", no_of_bills])
            header_table_data.append(["LINES", lines_count, "", "", "OUTLETS", outlet_count])
            header_table_data.append(["TOTAL LC", total_lc, "", "", "TOTAL FC", total_fc])
            
            df[["LC.", "Units.", "FC."]] = df[["LC", "Units", "FC"]].copy()
            if "Division Name" in df.columns:
                df['group'] = (df['Division Name'] != "").cumsum()
                split_dfs = [group for _, group in df.groupby('group') if (group['Division Name'] != "").any()]
                dfs = [group[["No", "Product Name", "MRP", "LC", "Units", "FC", "UPC", "LC.", "Units.", "FC."]] for group in split_dfs]
            else:
                dfs = [df[["No", "Product Name", "MRP", "LC", "Units", "FC", "UPC", "LC.", "Units.", "FC."]]]

        header_table = pd.DataFrame(header_table_data, dtype="str", columns=["a", "b", "c", "d", "e", "f"])
        self.print_table(header_table, border=0, print_header=False)
        self.ln(5)
        
        if isinstance(dfs, pd.DataFrame):
            dfs_list = [dfs]
        else:
            dfs_list = dfs

        for index, d in enumerate(dfs_list):
            self.print_table(d, border=1)
            if index < len(dfs_list) - 1: 
                self.ln(25)

        if sheet_type == LoadingSheetType.Plain: 
            self.add_page()
        if sheet_type == LoadingSheetType.Salesman: 
            self.ln(5)

        self.print_table(party_sales, border=1)
        
        output_path = os.path.join(output_dir, "loading.pdf")
        self.output(output_path)
        return output_path

class PickingLoadingSheetPDF:
    def generate(self, data_list: List[Dict[str, Any]]) -> BytesIO:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
        elements: List[Any] = []
        styles = getSampleStyleSheet()
        
        # 1. Prepare and filter data
        processed_data = []
        for record in data_list:
            df_source = record.get("df")
            if df_source is None: continue
            df = df_source.copy()
            # 1. Clean and Prepare Data
            # Sort by MRP
            df["mrp_num"] = pd.to_numeric(df["MRP"], errors='coerce').fillna(0)
            df = df.sort_values("mrp_num")
            df["MRP"] = df["mrp_num"].astype(int).astype(str)
            
            # Ensure Case and Units are clean strings (remove .0 if present)
            def clean_qty(val):
                s = str(val).split(".")[0]
                return s if s not in ["nan", "0"] else ""

            df["Case"] = df["Case"].apply(clean_qty)
            df["Units"] = df["Units"].astype(str).str.split(".").str[0].replace("0", "")
            
            df["S.No"] = range(1, len(df) + 1)
            
            processed_data.append({
                "bill_no": record.get("bill_no", ""),
                "party_name": record.get("party_name", ""),
                "df": df,
                "rows": len(df)
            })

        # 2. Page Packing Optimization (Max 2 bills per page, total rows < 30)
        # We sort by row count to pack efficiently
        processed_data.sort(key=lambda x: x["rows"], reverse=True)
        pages = []
        while processed_data:
            current_bill = processed_data.pop(0)
            page_bills = [current_bill]
            
            # Find a partner bill
            for i in range(len(processed_data)-1, -1, -1):
                if current_bill["rows"] + processed_data[i]["rows"] < 28: # Using 28 as safe limit for headers/spacers
                    page_bills.append(processed_data.pop(i))
                    break # Max 2 bills
            
            pages.append(page_bills)

        # 3. Build Elements
        for i, page_bills in enumerate(pages):
            for j, bill in enumerate(page_bills):
                bill_no = bill["bill_no"]
                party_name = bill["party_name"]
                df = bill["df"]
                
                cols_to_print = ["S.No", "Product Name", "MRP", "Case", "Units"]
                
                # New Row: Bill Info + Row 1: Headers
                bill_header_row = [f"Bill No: {bill_no}    |    Party: {party_name}", "", "", "", ""]
                data = [bill_header_row] + [cols_to_print] + df[cols_to_print].values.tolist()
                
                # Add Totals Row
                total_cases = pd.to_numeric(df["Case"], errors='coerce').sum()
                total_units = pd.to_numeric(df["Units"], errors='coerce').sum()
                data.append(["", "Total", "", str(int(total_cases)) if total_cases > 0 else "0", str(int(total_units)) if total_units > 0 else "0"])

                table = Table(data, repeatRows=2, colWidths=[30, 250, 60, 50, 50])
                table.setStyle(TableStyle([
                    ('SPAN', (0, 0), (-1, 0)), # Merge first row (bill info)
                    ('BACKGROUND', (0, 1), (-1, 1), colors.white),
                    ('TEXTCOLOR', (0, 0), (-1, 1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('FONTNAME', (0, 0), (-1, 1), 'Helvetica-Bold'), # Bold header rows
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), # Bold last row
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('TOPPADDING', (0, 0), (-1, 0), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ]))
                elements.append(table)
                
                if j < len(page_bills) - 1:
                    elements.append(Spacer(1, 40)) # Space between bills on same page
            
            if i < len(pages) - 1:
                elements.append(PageBreak())
        
        doc.build(elements)
        buffer.seek(0)
        return buffer

class PendingSheetPDF:
    def generate(self, df: pd.DataFrame, sheet_no: str, salesman: str, beat: str, date: datetime.date) -> BytesIO:
        buffer = BytesIO()
        # Define the PDF document with specified margins
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=10, bottomMargin=10)
        
        # Calculate the width of the page and the columns
        width, height = A4
        total_width = width - 60  # Subtract margins

        elements: List[Any] = []
        header_data = [[sheet_no, salesman], [beat, date.strftime("%d-%b-%Y")]]
        header_table = Table(header_data, colWidths=[total_width * 0.5, total_width * 0.5])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 1), (-1, 1), 1, colors.black), 
            ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
        ]))

        first_column_width = total_width * 0.3
        
        df = df.rename(columns={"Bill Net Amt": "Bill", "Collected Amount": "Coll", "OutstANDing Amount": "Outstanding", "Bill Ageing (In Days)": "Days", "Sr No": " "})
        if "Date" in df.columns:
            df["Date_fmt"] = pd.to_datetime(df["Date"], errors='coerce').dt.strftime("%d/%m/%Y").fillna("")
            
        for col in ["Coll", "Outstanding", "Bill"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int).astype(str)
                
        data = []
        for _, row in df.iterrows():
            days = str(row.get("Days", "")).split(".")[0]
            party_name = str(row.get("Party Name", ""))
            salesperson = str(row.get("Salesperson Name", ""))
            date_val = str(row.get("Date_fmt", "")) if "Date_fmt" in df.columns else ""
            
            data.append([party_name.split("-")[0][:27], date_val, salesperson[:12], days, " ", " "])
            data.append([str(row.get("Bill No", "")) + " " * 9 + days + " days", row.get("Bill", ""), row.get("Coll", ""), row.get("Outstanding", ""), " ", " "])

        # Create the table and specify column widths
        table = Table(data, colWidths=[total_width * 0.3] + [total_width * 0.12, total_width * 0.15, total_width * 0.1, total_width * 0.13] + [total_width * 0.20])
        
        # Initialize the table style with basic configurations
        table_style = TableStyle([
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBEFORE', (4, 0), (5, -1), 1, colors.black),
        ])

        # Apply a bottom border only to even rows (2, 4, 6, ...)
        for row_index in range(1, len(data), 2):  # Start at 1 and step by 2
            table_style.add('LINEBELOW', (0, row_index), (-1, row_index), 1, colors.black)

        table.setStyle(table_style)
        
        try:
            total_outstanding = round(df["Outstanding"].astype(float).sum())
        except (ValueError, KeyError):
            total_outstanding = 0
            
        count_table = [("Bills", len(df.index)), ("Return", " "),
                       ("Out Amt", total_outstanding), ("Coll Amt", " ")]
        denomination_data1 = [(500, "", ""), (200, "", ""), (100, "", ""), (50, "", "")] 
        denomination_data2 = [(20, "", ""), (10, "", ""), ("Coins", "", ""), ("Total", "", "")] 
        
        common_style = TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.black), ('TOPPADDING', (0, 0), (-1, -1), 20)])
        widths = [total_width / 15, total_width / 10, total_width / 4]
        
        c = Table(count_table, colWidths=[total_width / 10, total_width / 10], style=common_style)
        d1 = Table(denomination_data1, colWidths=widths, style=common_style)
        d2 = Table(denomination_data2, colWidths=widths, style=common_style)
        
        combined_table = [[c, d1, d2]]
        combined_table = Table(combined_table)

        elements += [header_table, table, Spacer(1, 20), combined_table]
        doc.build(elements)
        buffer.seek(0)
        return buffer 

class PDFEditor:
    @staticmethod
    def remove_blank_pages_from_first_copy(pdf_path: str, blank_threshold: int = 640):
        doc = pymupdf.open(pdf_path)
        output_pdf = pymupdf.open()  # Create a new PDF document

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_height = page.rect.height  # Total height of the page
            text_instances = page.get_text("dict")["blocks"]

            max_y = 0  # Track the maximum Y-coordinate of text

            for block in text_instances:
                if "bbox" in block:  # Each block has a bounding box
                    y1 = block["bbox"][3]  # Bottom Y-coordinate
                    if y1 > max_y:
                        max_y = y1

            # Calculate blank height
            blank_height = page_height - max_y

            # Check if the blank height exceeds the threshold
            if blank_height < blank_threshold:
                output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)

        output_pdf.save(pdf_path)
        output_pdf.close()
        doc.close()
