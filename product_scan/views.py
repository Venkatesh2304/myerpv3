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

@api_view(['POST'])
def sales_scan_id(request):
    bill_no = request.data.get('bill_no').upper()
    company_id = request.data.get('company_id')
    if not bill_no or not company_id:
        return JsonResponse({'error': 'bill_no and company_id are required'}, status=400)

    sales_scan, created = SalesScan.objects.get_or_create(
        bill_no=bill_no,
        company_id=company_id,
    )
    
    # If new or empty, fetch data from Ikea API
    #TODO: remove True
    if created or not sales_scan.bill_products or True:
        ikea = Ikea(company_id)
        bill_data = ikea.retrive_bill(bill_no)
        
        if not bill_data or 'billingProductMasterVOList' not in bill_data:
            sales_scan.delete()
            return JsonResponse({'error': 'Bill not found in Ikea API'}, status=404)
        products_list = bill_data['billingProductMasterVOList']
        bill_products = defaultdict(lambda: defaultdict(dict))
        
        for item in products_list:
            sku = item.get('prodCode')
            mrp = int(item.get('mrp', 0))
            if not sku: continue
            existing_sku_mrp_data =  bill_products[sku][mrp]
            bill_products[sku][mrp] = {
                'qUnits': int(item.get('qUnits', 0)) + int(existing_sku_mrp_data.get('qUnits', 0)),
                'qCases': int(item.get('qCase', 0)) + int(existing_sku_mrp_data.get('qCases', 0)),
                'unitsCase': int(item.get('unitsCase', 1)),
                'basepack': str(item.get('itemVarCode')),
                'name': item.get('prodName', '')
            }
        
        sales_scan.bill_products = bill_products
        sales_scan.save()
        
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
        if not sales_scan.scanned_products:
             sales_scan.scanned_products.append({})
             
        if box_no < len(sales_scan.scanned_products):
             sales_scan.scanned_products[box_no] = scanned
        else:
             raise ValueError("Box number out of bounds")

        if len(sales_scan.scanned_products[-1]) > 0:
            sales_scan.scanned_products.append({})
        
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
    
    sku_name_map = sales_scan.get_sku_name_map()
    
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
    summary_data = [["Box Number", "Total Pieces"]]
    box_totals = []
    
    # Detailed data for the second table
    detailed_data = [["Box", "Product Name", "MRP", "Qty"]]
    
    for box_idx, box_data in enumerate(sales_scan.scanned_products):
        box_num = box_idx + 1
        box_total_qty = 0
        box_has_content = False
        
        for sku, mrp_data in box_data.items():
            for mrp, qty in mrp_data.items():
                if qty > 0:
                    box_total_qty += qty
                    product_name = sku_name_map.get(sku, sku)
                    detailed_data.append([str(box_num), str(product_name), str(mrp), str(qty)])
                    box_has_content = True
        
        if box_has_content:
            summary_data.append([str(box_num), str(box_total_qty)])
            box_totals.append(box_total_qty)

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
        
        summary_table = Table(summary_data, colWidths=[100, 100])
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

    # 1. Calculate Scanned Totals
    scanned_totals = defaultdict(lambda: defaultdict(int))
    for box_data in sales_scan.scanned_products:
        for sku, mrp_data in box_data.items():
            for mrp, qty in mrp_data.items():
                scanned_totals[sku][mrp] += qty

    # 2. Calculate Billed Totals & Compare
    mismatches = []
    
    # Get SKU Name Map
    sku_name_map = sales_scan.get_sku_name_map()
    
    # We need to iterate over both billed and scanned to catch all differences
    # Set of all (sku, mrp) pairs
    all_pairs = set()
    
    # Add from bill_products
    for sku, mrp_data in sales_scan.bill_products.items():
        for mrp in mrp_data.keys():
            all_pairs.add((sku, mrp))
            
    # Add from scanned_totals (in case of extra items scanned)
    for sku, mrp_data in scanned_totals.items():
        for mrp in mrp_data.keys():
            all_pairs.add((sku, mrp))
            
    for sku, mrp in all_pairs:
        # Get Billed Qty
        billed_qty = 0
        if sku in sales_scan.bill_products and mrp in sales_scan.bill_products[sku]:
            item = sales_scan.bill_products[sku][mrp]
            billed_qty = (item.get('qCases', 0) * item.get('unitsCase', 1)) + item.get('qUnits', 0)
            
        # Get Scanned Qty
        scanned_qty = scanned_totals[sku][mrp]
        
        if billed_qty != scanned_qty:
            mismatches.append({
                'sku': sku,
                'name': sku_name_map.get(sku, sku),
                'mrp': mrp,
                'billed': billed_qty,
                'scanned': scanned_qty
            })
            
    return JsonResponse({'mismatches': mismatches})
