from fpdf import FPDF
import pandas as pd
from typing import List
import datetime

class BaseTablePDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.S = 10  # Font size
        self.H = 6   # Cell height

    def header(self):
        # Move to the top right corner
        self.set_y(10)  # Adjust vertical position as needed
        
        # Print the page number on the right
        self.cell(0, 10, f'{datetime.date.today().strftime("%d-%m-%Y")}', 0, 0, 'L')
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'R')
        self.ln(10)

    def _calculate_col_widths(self, df: pd.DataFrame) -> List[float]:
        col_widths = []
        for col in df.columns:
            max_width = self.get_string_width(str(col)) + 4  # Start with the header width
            for value in df[col]:
                value_width = self.get_string_width(str(value).replace(' ','X')) + 4
                max_width = max(max_width, value_width)
            col_widths.append(max_width)
        
        total_width = sum(col_widths)
        if total_width > 0:
            scale = 190 / total_width
            col_widths = [i * scale for i in col_widths]
        else:
            col_widths = [190 / len(df.columns)] * len(df.columns)
            
        return col_widths

    def _print_table_header(self, col_widths: List[float], header: List[str], border: int):
        self.set_font('Arial', '', self.S)
        for i, col_name in enumerate(header):
            self.cell(col_widths[i], self.H, str(col_name), border=border, align='L')
        self.ln()

    def print_table(self, df: pd.DataFrame, border: int = 0, print_header: bool = True):
        self.set_font('Arial', '', self.S)
        col_widths = self._calculate_col_widths(df)
        header = df.columns.tolist()
        if print_header:
            self._print_table_header(col_widths, header, border)

        # Print DataFrame rows and repeat header on each new page if needed
        for index, row in df.iterrows():
            # Check if a new page is needed
            if self.get_y() > 280:  # Adjust this value if you need more/less space before the footer
                self.add_page()      # Add a new page
                self._print_table_header(col_widths, header, border)  # Reprint the header on the new page

            for i, item in enumerate(row): 
                self.cell(col_widths[i], self.H, str(item), border=border, align='L')
            self.ln()
