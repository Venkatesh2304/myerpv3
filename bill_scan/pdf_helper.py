from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

def generate_bill_list_pdf(bill_numbers, columns=6):
    bytesio = BytesIO()
    pdf = SimpleDocTemplate(bytesio, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    width, height = letter
    total_width = width - 60
    
    # Chunk the bill numbers into rows
    data = []
    for i in range(0, len(bill_numbers), columns):
        row = bill_numbers[i:i + columns]
        # Pad the last row if necessary
        if len(row) < columns:
            row += [''] * (columns - len(row))
        data.append(row)
        
    if not data:
        data = [['No bills']]
        columns = 1

    # Calculate column width
    col_width = total_width / columns
    
    table = Table(data, colWidths=[col_width] * columns)
    
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    elements = [table]
    pdf.build(elements)
    bytesio.seek(0)
    return bytesio
