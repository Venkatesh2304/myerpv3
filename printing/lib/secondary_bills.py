from docx import Document
from docx.shared import Pt, Cm
from prettytable import PrettyTable, ALL
from typing import Callable, Dict, Optional

class SecondaryBillGenerator:
    def generate(self, txt_file_path: str, output_docx_path: str, barcode_generator: Callable, config: Optional[Dict]):
        document = Document()
        self._process_file(txt_file_path, document, barcode_generator, config)
        document.save(output_docx_path)

    def _process_file(self, file_path: str, document: Document, barcode_generator: Callable, config: Dict):
        with open(file_path, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        values = ['Region', 'Invoice No', 'Invoice Date', 'Retailer PAN']
        first, last, billval = [], [], []
        invoice = []
        name = []

        for i in range(len(lines)):
            line = lines[i]
            if 'Invoice No ' in line and config['secname'] in line:
                first.append(i)
                invoice.append(line)
            if 'Time of Billing ' in line:
                last.append(i)
            if 'Bill Amount' in line:
                billval.append(line)
            if 'Retailer ' in line and 'Name' in line and config['secadd'] in line:
                name.append(line)

        self._setup_document_styles(document)

        for i in range(len(first)):
            # Add blank rows for spacing (from original code)
            # table = PrettyTable(['Date', 'Amount', 'Balance']) # Was defined but not really used effectively in loop in original? 
            # Original code created table outside loop but added rows inside? 
            # Actually original code:
            # table=PrettyTable(['Date','Amount','Balance'])
            # ...
            # for i in range(0,3) : table.add_row([' '*20]*3)
            # But table is never added to document in the original code? 
            # Wait, looking at original code:
            # table=PrettyTable...
            # ...
            # for i in range(0,3) : table.add_row...
            # It seems table is NOT used. I will omit it.

            y1 = lines[first[i]:last[i]+1]
            bill_text = ""
            for j in y1:
                bill_text += j + '\n'
                l = 0
                j1 = j
                for t in values:
                    if t in j:
                        l = 1
                        if 'Time' in j:
                            j1 = j
                        else:
                            j1 = j.split(t)[0]
                
                if l == 0:
                    document.add_paragraph(j)
                else:
                    document.add_paragraph(j1)

            billvalue = billval[i]
            billvalue1 = billvalue.split('Bill')[0]
            billvalue2 = 'Bill' + billvalue.split('Bill')[1]
            document.add_paragraph(billvalue1)
            
            paragraph1 = document.add_paragraph()
            # imp=invoice[i].split('Invoice')[1].split(':')[1]+'*'+name[i].split(':')[1]+'*'+'Amt :'+billvalue2.split(':')[1]
            # imp=' '.join(imp.split())
            # paragraph1=paragraph1.add_run('  '+'   '.join(imp.split('*')))
            
            # Safer parsing
            try:
                inv_part = invoice[i].split('Invoice')[1].split(':')[1]
                name_part = name[i].split(':')[1]
                amt_part = billvalue2.split(':')[1]
                imp = f"{inv_part}*{name_part}*Amt :{amt_part}"
                imp = ' '.join(imp.split())
                run = paragraph1.add_run('  ' + '   '.join(imp.split('*')))
            except IndexError:
                run = paragraph1.add_run("Error parsing invoice details")

            run.font.size = Pt(12)
            run.bold = True
            
            paragraph3 = document.add_paragraph().add_run(' ' * 60 + 'Signature')
            # paragraph3.alignment = 2 # WD_ALIGN_PARAGRAPH.RIGHT is 2
            # But run doesn't have alignment, paragraph does.
            document.paragraphs[-1].alignment = 2 # Right align
            paragraph3.font.size = Pt(12)
            paragraph3.bold = True

            # Barcode
            try:
                inum = invoice[i].split('Invoice')[1].split(':')[1].strip()
                barcode_img = barcode_generator(inum)
                barcode = document.add_picture(barcode_img)
                barcode.width = Cm(2.5)
                barcode.height = Cm(2.5)
            except Exception as e:
                print(f"Error adding barcode: {e}")

            lines_per_page = config.get('lines', 18)
            if i % 2 == 0:
                document.add_paragraph('\n' * lines_per_page)
            else:
                document.add_page_break()

    def _setup_document_styles(self, document: Document):
        style = document.styles['Normal']
        font = style.font
        font.name = 'Courier New'
        font.size = Pt(9)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)

        for section in document.sections:
            section.top_margin = Cm(0.5)
            section.bottom_margin = Cm(0.5)
            section.left_margin = Cm(0.5)
            section.right_margin = Cm(0.5)
