from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle , Spacer
from reportlab.lib import colors

def pending_sheet_pdf(df, sheet_no ,salesman,beat,date):
    bytesio = BytesIO()
    pdf = SimpleDocTemplate(bytesio, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=10, bottomMargin=10)
    width, height = letter
    total_width = width - 60

    header_data = [[sheet_no, salesman],[beat,date.strftime("%d-%b-%Y")]]
    header_table = Table(header_data, colWidths=[total_width * 0.5, total_width * 0.5])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 1), (-1, 1), 1, colors.black) , 
        ('BOTTOMPADDING', (0,1), (-1,1), 10),
    ]))

    df["coll_amt"] = (df["bill_amt"] - df["balance"]).round()
    df["bill_date"] = df["bill_date"].dt.strftime("%d/%m/%Y")
    for col in ["coll_amt","balance","bill_amt","days"] :  #Integer to string
        df[col] = df[col].astype(str).str.split(".").str[0]
    data = []
    for _,row in df.iterrows() : 
        data.append([ row["party_name"].split("-")[0][:27] , row["bill_date"] , row["salesman"][:12] , row["days"] , " " , " " ])
        data.append([ row["inum"] + " "*9 + row["days"] + " days" , row["bill_amt"] , row["coll_amt"] , row["balance"] , " " , " " ])


    # Create the table and specify column widths
    table = Table(data, colWidths= [total_width*0.3] + [total_width*0.12,total_width*0.15,total_width*0.1,total_width*0.13]  + [total_width*0.20])
    
    # Initialize the table style with basic configurations
    table_style = TableStyle([
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('FONT', (0,0), (-1,-1), 'Helvetica', 10),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBEFORE', (4, 0), (5, -1), 1, colors.black) ,
    ])

    # Apply a bottom border only to even rows (2, 4, 6, ...)
    for row_index in range(1, len(data), 2):  # Start at 1 and step by 2
        table_style.add('LINEBELOW', (0, row_index), (-1, row_index), 1, colors.black)

    table.setStyle(table_style)
    total_outstanding = round(df["balance"].astype(float).sum())
    count_table = [("Bills",len(df.index)),("Return"," "),
                   ("Out Amt",total_outstanding),("Coll Amt"," ")]
    denomination_data1 = [(500,"","") , (200,"","") , (100,"","") , (50,"","") ] 
    denomination_data2 = [(20,"","") , (10,"","") ,("Coins","",""),("Total","","")] 
    common_style = TableStyle([ ('GRID', (0, 0), (-1, -1), 1, colors.black) , ('TOPPADDING',(0,0),(-1,-1),20) ])
    widths1 = [total_width/15,total_width/10,total_width/4]
    widths2 = [total_width/15,total_width/10,total_width/6]
    c = Table(count_table, colWidths=[total_width/10,total_width/10],style=common_style)
    d1 = Table(denomination_data1, colWidths=widths1,style=common_style)
    d2 = Table(denomination_data2, colWidths=widths2,style=common_style)
    combined_table = [[c , d1 , d2]]
    combined_table = Table(combined_table)

    elements = [header_table,table,Spacer(1, 20),combined_table] #Paragraph(sheet_no), Paragraph() , 
    pdf.build(elements)
    return bytesio 
