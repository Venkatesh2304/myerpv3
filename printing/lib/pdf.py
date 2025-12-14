from custom.pdf.base import BaseTablePDF
import pandas as pd
from typing import Tuple, Dict, Any, List
from enum import Enum
import datetime
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from io import BytesIO
import pymupdf

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

class PendingSheetPDF:
    def generate(self, df: pd.DataFrame, sheet_no: str, salesman: str, beat: str, date: datetime.date) -> BytesIO:
        bytesio = BytesIO()
        # Define the PDF document with specified margins
        pdf = SimpleDocTemplate(bytesio, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=10, bottomMargin=10)
        
        # Calculate the width of the page and the columns
        width, height = A4
        total_width = width - 60  # Subtract margins

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
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%d/%m/%Y")
            
        for col in ["Coll", "Outstanding", "Bill"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.split(".").str[0]
                
        data = []
        for _, row in df.iterrows():
            days = str(row.get("Days", "")).split(".")[0]
            party_name = row.get("Party Name", "")
            salesperson = row.get("Salesperson Name", "")
            
            data.append([party_name.split("-")[0][:27], row.get("Date", ""), salesperson[:12], days, " ", " "])
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

        elements = [header_table, table, Spacer(1, 20), combined_table]
        pdf.build(elements)
        bytesio.seek(0)
        return bytesio 

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
