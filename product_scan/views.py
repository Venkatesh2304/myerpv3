from rest_framework.decorators import api_view
from django.http import JsonResponse
from .models import SalesScan
from custom.classes import Ikea
from collections import defaultdict
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib import colors
from django.conf import settings
import os
import datetime
from core.utils import get_media_url
from .models import Barcode
from report.models import StockReport
import time

@api_view(['GET', 'POST'])
def barcode_view(request):
    if request.method == 'GET':
        code = request.query_params.get('code')
        if not code:
            return JsonResponse({'error': 'code is required'}, status=400)
        
        barcode_obj = Barcode.objects.filter(barcode=code).first()
        if not barcode_obj:
            return JsonResponse({'basepack': None}, status=404)
        
        basepack = barcode_obj.basepack
        products = StockReport.objects.filter(basepack=basepack).values('stock_id', 'mrp', 'name').distinct()
        
        result = []
        for p in products:
            result.append({
                'sku': p['stock_id'],
                'mrp': p['mrp'],
                'name': p['name']
            })
            
        return JsonResponse({'products': result, 'basepack': basepack})

    elif request.method == 'POST':
        code = request.data.get('code')
        sku = request.data.get('sku')
        # mrp = request.data.get('mrp') # Not needed as per user request
        
        if not all([code, sku]):
            return JsonResponse({'error': 'code and sku are required'}, status=400)
            
        # Find basepack from StockReport
        # We need to find a record with this sku to get the basepack
        stock_entry = StockReport.objects.filter(stock_id=sku).first()
        
        if not stock_entry:
             return JsonResponse({'error': 'Product not found in Stock Report to derive basepack'}, status=404)
        
        basepack = stock_entry.basepack
        
        Barcode.objects.update_or_create(barcode=code, defaults={'basepack': str(basepack), 'manual': True})
        
        return JsonResponse({'status': 'success'})

@api_view(['POST'])
def sales_scan_id(request):
    bill_no = request.data.get('bill_no').upper()
    company_id = request.data.get('company_id')
    if not bill_no or not company_id:
        return JsonResponse({'error': 'bill_no and company_id are required'}, status=400)
    if len(bill_no) <= 5 : 
        return JsonResponse({'error': 'Enter Full Bill Number'}, status=400)
    if not bill_no[-5:].isdigit():
        return JsonResponse({'error': 'Invalid Bill Number'}, status=400)

    sales_scan = SalesScan.objects.filter(bill_no=bill_no, company_id=company_id).first()
    
    if sales_scan and sales_scan.is_posted:
        return JsonResponse({'id': sales_scan.id})

    ikea = Ikea(company_id)
    bill_data = ikea.retrive_bill(bill_no)
    if not bill_data or 'billingProductMasterVOList' not in bill_data:
        return JsonResponse({'error': 'Bill not found in Ikea API, Check Company'}, status=404)

    if not sales_scan:
        #Validate bill number
        billDtStr = bill_data["billHdVO"]["billDtStr"]
        bill_date = datetime.datetime.strptime(billDtStr, '%d/%m/%Y')
        if bill_date < datetime.datetime.now() - datetime.timedelta(days=10):
            return JsonResponse({'error': 'Bill is older than 10 days'}, status=404)
        sales_scan = SalesScan.objects.create(bill_no=bill_no, company_id=company_id)
    
    sales_scan.update_from_bill_data(bill_data)
    return JsonResponse({'id': sales_scan.id})

@api_view(['GET', 'POST'])
def scan_sales_box(request):
    if request.method == 'POST':
        scan_id = request.data.get('scan_id')
    else:
        scan_id = request.query_params.get('scan_id')
    
    if not scan_id:
        return JsonResponse({'error': 'scan_id is required'}, status=400)
    
    try:
        # Use simple get, avoid 500 if id invalid format (though int expected usually)
        sales_scan = SalesScan.objects.get(id=scan_id)
    except (SalesScan.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Scan not found'}, status=404)

    if request.method == 'POST':
        box_no = int(request.data.get('box_no')) - 1
        scanned = request.data.get('scanned', {})
        logs = request.data.get('logs', [])
        
        if not sales_scan.scanned_products:
             sales_scan.scanned_products = []
        
        if not sales_scan.logs:
             sales_scan.logs = []
             
        # Initialize up to current box
        while len(sales_scan.scanned_products) <= box_no:
            sales_scan.scanned_products.append({})
        
        while len(sales_scan.logs) <= box_no:
            sales_scan.logs.append([])

        sales_scan.scanned_products[box_no] = scanned
        sales_scan.logs[box_no] = logs

        # Add empty box if last box has content
        if len(sales_scan.scanned_products) > 0 and len(sales_scan.scanned_products[-1]) > 0:
            sales_scan.scanned_products.append({})
            sales_scan.logs.append([])
        
        from django.utils import timezone
        sales_scan.scanned_time = timezone.now()
        sales_scan.save()
        return JsonResponse({'box_no': len(sales_scan.scanned_products)})

    elif request.method == 'GET':
        box_no = int(request.query_params.get('box_no', 1)) - 1
        
        current_scanned = defaultdict(lambda: defaultdict(int))
        others_scanned = defaultdict(lambda: defaultdict(int))
        
        for idx, box_data in enumerate(sales_scan.scanned_products):
            # Iterate through contents
            # Structure matches load: {sku: {mrp: qty}} ? 
            # Load uses QtyMap which is defaultdict(lambda : defaultdict(int))
            # sales_scan structure is {sku: {mrp: qty}} based on previous context
            
             for sku, sku_data in box_data.items():
                for mrp, qty in sku_data.items():
                    if idx == box_no:
                        current_scanned[sku][mrp] += qty
                    else:
                        others_scanned[sku][mrp] += qty
        
        return JsonResponse({
            'current_scanned': current_scanned,
            'others_scanned': others_scanned
        })

def generate_sales_scan_pdf(sales_scan, output_path):
    # Reduced margins (20 points = ~0.7cm)
    doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=20, bottomMargin=20, leftMargin=20, rightMargin=20)
    elements = []
    
    sku_name_map = sales_scan.sku_name_map
    
    # 0. Header (Bill No & Time)
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    styles = getSampleStyleSheet()
    
    current_time = datetime.datetime.now().strftime("%d-%b-%Y %H:%M")
    header_data = [[f"Bill No: {sales_scan.bill_no}", f"Time: {current_time}"]]
    header_table = Table(header_data, colWidths=[250, 250])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4)) # Reduced gap
    
    # 1. Box Summary Table (Total pieces per box)
    summary_data = [["Box Number", "Cases", "Pcs"]]
    box_totals = []
    
    # Detailed data for the second table
    detailed_data = [["Box", "Product Name", "MRP", "Cases", "Pcs"]]
    
    bill_products = sales_scan.bill_products

    for box_idx, box_data in enumerate(sales_scan.scanned_products):
        box_num = box_idx + 1
        box_total_cases = 0
        box_total_pcs = 0
        box_has_content = False
        
        for sku, mrp_data in box_data.items():
            for mrp, qty in mrp_data.items():
                if qty > 0:
                    # Get unitsCase from bill_products
                    mrp_str = str(mrp)
                    mrp_entry = bill_products.get(sku, {}).get(mrp_str, {})
                    units_per_case = mrp_entry.get('unitsCase', 1)
                    if not units_per_case or units_per_case == 0:
                        units_per_case = 1
                    
                    cases = qty // units_per_case
                    pcs = qty % units_per_case

                    box_total_cases += cases
                    box_total_pcs += pcs

                    product_name = sku_name_map.get(sku, sku)
                    detailed_data.append([str(box_num), str(product_name), str(mrp), str(cases), str(pcs)])
                    box_has_content = True
        
        if box_has_content:
            summary_data.append([str(box_num), str(box_total_cases), str(box_total_pcs)])
            box_totals.append(box_total_cases + box_total_pcs)

    # Styling for B&W Printer (No backgrounds, simple borders, minimal padding)
    bw_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

    # Add Box Summary Table
    if len(box_totals) > 0:
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        styles = getSampleStyleSheet()
        
        summary_table = Table(summary_data, colWidths=[100, 100, 100])
        summary_table.setStyle(bw_style)
        elements.append(summary_table)
        elements.append(Spacer(1, 8)) # Reduced gap

        # Add Detailed Break-up Table
        detailed_table = Table(detailed_data, repeatRows=1)
        detailed_table.setStyle(bw_style)
        elements.append(detailed_table)
    else:
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No Scanned Data Found", styles['Normal']))

    doc.build(elements)

@api_view(['POST'])
def sales_scan_summary(request):
    scan_id = request.data.get('scan_id')
    if not scan_id:
        return JsonResponse({'error': 'scan_id is required'}, status=400)
        
    try:
        sales_scan = SalesScan.objects.get(id=scan_id)
    except SalesScan.DoesNotExist:
        return JsonResponse({'error': 'Scan not found'}, status=404)
        
    # Create directory
    company_id = str(sales_scan.company.pk)
    output_dir = os.path.join(settings.MEDIA_ROOT, 'product_scan', company_id)
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"scan_summary_{sales_scan.id}.pdf"
    file_path = os.path.join(output_dir, file_name)
    
    try:
        generate_sales_scan_pdf(sales_scan, file_path)
    except Exception as e:
         return JsonResponse({'error': f"PDF Generation failed: {str(e)}"}, status=500)

    return JsonResponse({'filepath': get_media_url(file_path)})

@api_view(['POST'])
def sales_scan_mismatch(request):
    scan_id = request.data.get('scan_id')
    if not scan_id:
        return JsonResponse({'error': 'scan_id is required'}, status=400)
    
    try:
        sales_scan = SalesScan.objects.get(id=scan_id)
    except SalesScan.DoesNotExist:
        return JsonResponse({'error': 'Scan not found'}, status=404)

    return JsonResponse({'mismatches': sales_scan.mismatches})
