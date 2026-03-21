from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from rest_framework.decorators import api_view
from django.http import JsonResponse, FileResponse
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
from datetime import timedelta
from report.models import StockReport
import time
import subprocess
import tempfile
from django.core.files import File
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

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
        
        sales_scan.scanned_time = datetime.datetime.now()
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

@api_view(['GET'])
def anomaly_analysis(request):
    date_str = request.query_params.get('date')
    
    if not date_str:
        return JsonResponse({'error': 'date is required (YYYY-MM-DD)'}, status=400)
    
    try:
        target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    user_companies = request.user.companies.all()
    scans = SalesScan.objects.filter(scanned_time__date=target_date, company__in=user_companies)

    fake_scans = []
    manual_entries = []
    mismatches = []

    for scan in scans:
        all_logs = []
        for box_logs in scan.logs:
            if isinstance(box_logs, list):
                for log in box_logs:
                    if isinstance(log, dict):
                        all_logs.append(log)
        
        bill_products = scan.bill_products
        sku_name_map = scan.sku_name_map

        def get_mrp_display(sku):
            mrps = list(bill_products.get(sku, {}).keys())
            if not mrps:
                return ""
            return " / ".join(sorted([str(m) for m in mrps]))

        # Simple grouping and anomaly detection
        sku_data = defaultdict(lambda: {'first_time': float('inf'), 'fake_count': 0, 'manual_count': 0, 'logs': []})
        
        for log in all_logs:
            sku = log.get('sku')
            if not sku:
                continue
            d = sku_data[sku]
            ts = log.get('timestamp', float('inf'))
            if ts < d['first_time']:
                d['first_time'] = ts
            d['logs'].append(log)
            if log.get('type', '').startswith('manual_'):
                d['manual_count'] += 1

        for sku, d in sku_data.items():
            # Sort logs for fake scan detection
            d['logs'].sort(key=lambda x: x.get('timestamp', 0))
            total_fake_diff = 0
            for i in range(1, len(d['logs'])):
                t1 = d['logs'][i-1].get('timestamp')
                t2 = d['logs'][i].get('timestamp')
                if t1 and t2:
                    diff = t2 - t1
                    if diff < 1000:
                        d['fake_count'] += 1
                        total_fake_diff += diff

            total_items = len(d['logs'])
            if total_items > 0 and (d['fake_count'] / total_items) >= 0.5:
                avg_time = (total_fake_diff / d['fake_count']) / 1000.0 if d['fake_count'] > 0 else 0
                fake_scans.append({
                    'product': sku_name_map.get(sku, sku),
                    'mrp': get_mrp_display(sku),
                    'time': d['first_time'] if d['first_time'] != float('inf') else None,
                    'party': scan.party_name,
                    'bill_no': scan.bill_no,
                    'desc': f"{total_items} items / {avg_time:.1f} sec"
                })

            if d['manual_count'] > 0:
                manual_entries.append({
                    'product': sku_name_map.get(sku, sku),
                    'mrp': get_mrp_display(sku),
                    'time': d['first_time'] if d['first_time'] != float('inf') else None,
                    'party': scan.party_name,
                    'bill_no': scan.bill_no,
                    'desc': f"{d['manual_count']} Manual Entries"
                })

        # 3. Mismatches
        for m in scan.mismatches:
            sku = m['sku']
            diff = m['scanned'] - m['billed']
            desc = f"{diff} Excess" if diff > 0 else f"{abs(diff)} Shortage"
            
            mismatches.append({
                'product': m['name'],
                'mrp': get_mrp_display(sku),
                'time': sku_data[sku]['first_time'] if sku in sku_data and sku_data[sku]['first_time'] != float('inf') else None,
                'party': scan.party_name,
                'bill_no': scan.bill_no,
                'desc': desc
            })

    return JsonResponse({
        'fake_scans': fake_scans,
        'manual_entries': manual_entries,
        'mismatches': mismatches
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def get_video_tasks(request):
    
    company_id = request.query_params.get('company_id')
    if not company_id:
        return JsonResponse({'error': 'company_id is required'}, status=400)
    
    # Filter for scans with no video, have logs, no activity for 30 minutes, and within last 5 days
    days_ago = datetime.datetime.now() - timedelta(days=1)
    threshold = datetime.datetime.now() - timedelta(minutes=30)
    
    # We use updated_at to check for inactivity
    tasks = SalesScan.objects.filter(
        company_id=company_id,
        video_status__in=['none', 'failed','pending'],
        scanned_time__isnull=False,
        scanned_time__lt=threshold,
        scanned_time__gte=days_ago
    ).exclude(logs=[])
    result = []
    for task in tasks:
        start_dt, end_dt = task.video_range
        if not start_dt or not end_dt:
            continue
            
        result.append({
            'id': task.id,
            'bill_no': task.bill_no,
            'start': start_dt.strftime('%Y-%m-%d %H:%M:%SZ'), # Hikvision format
            'end': end_dt.strftime('%Y-%m-%d %H:%M:%SZ'),
        })
    
    return JsonResponse({'tasks': result})

def _get_video_filters(scan, rel_start_offset=0):
    """
    Returns the FFmpeg vf chain for product name overlays.
    rel_start_offset: used for clips to adjust text timing (log_ts - min_ts - offset).
    """
    all_logs = []
    for box_logs in scan.logs:
        if isinstance(box_logs, list):
            for log in box_logs:
                if isinstance(log, dict) and 'timestamp' in log:
                    all_logs.append(log)
    
    if not all_logs:
        return "null"
        
    all_logs.sort(key=lambda x: x['timestamp'])
    min_ts = min(log['timestamp'] for log in all_logs)
    sku_name_map = scan.sku_name_map
    filters = []
    
    for i, log in enumerate(all_logs):
        sku = log.get('sku')
        if not sku: continue
        name = sku_name_map.get(sku, sku) or sku
        safe_name = str(name).replace("'", "").replace(":", "-")
        # Timing relative to the start of the video/clip
        rel_ts = (log['timestamp'] - min_ts) / 1000.0 - rel_start_offset
        
        # Calculate duration: 4 seconds, but capped by next log to avoid overlap
        duration = 4.0
        rel_end = rel_ts + duration
        if i < len(all_logs) - 1:
            next_rel_ts = (all_logs[i+1]['timestamp'] - min_ts) / 1000.0 - rel_start_offset
            if next_rel_ts > rel_ts:
                rel_end = min(rel_end, next_rel_ts)
        
        # Only include if it falls within the clip (or just let FFmpeg handle it,
        # but enable='between(t, ...)' handles it anyway)
        filters.append(f"drawtext=text='{safe_name}':x=w-tw-10:y=10:fontcolor=red:fontsize=64:enable='between(t,{rel_ts:.2f},{rel_end:.2f})'")
    
    return ",".join(filters)

@api_view(['POST'])
@permission_classes([AllowAny])
def upload_scan_video(request):
    scan_id = request.data.get('scan_id')
    video_file = request.FILES.get('video')
    
    if not scan_id or not video_file:
        return JsonResponse({'error': 'scan_id and video file are required'}, status=400)
        
    try:
        sales_scan = SalesScan.objects.get(id=scan_id)
    except SalesScan.DoesNotExist:
        return JsonResponse({'error': 'Scan not found'}, status=404)
        
    # Compression disabled temporarily as per user request
    """
    # Save uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_in:
        for chunk in video_file.chunks():
            temp_in.write(chunk)
        temp_in_path = temp_in.name

    # Create temporary path for compressed output
    temp_out_path = temp_in_path + "_compressed.mp4"

    cmd = [
        "ffmpeg", "-i", temp_in_path,
        "-vcodec", "libx265",
        "-crf", "35",
        "-vf", "scale=1280:-2,fps=8",
        "-preset", "ultrafast",
        "-an",
        "-y",
        temp_out_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
             print(f"Compression failed: {result.stderr}")
             return JsonResponse({'error': 'Video compression failed', 'details': result.stderr, 'code': result.returncode}, status=500)
             
        with open(temp_out_path, 'rb') as f:
            sales_scan.video_file.save(f"{sales_scan.bill_no}_compressed.mp4", File(f), save=False)
        sales_scan.video_status = 'completed'
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        if os.path.exists(temp_in_path): os.remove(temp_in_path)
        if os.path.exists(temp_out_path): os.remove(temp_out_path)
    """
    
    sales_scan.video_file = video_file
    sales_scan.video_status = 'completed'
    
    # Record the calculated times used
    start_dt, end_dt = sales_scan.video_range
    sales_scan.video_start_time = start_dt
    sales_scan.video_end_time = end_dt
    
    sales_scan.save()
    return JsonResponse({'status': 'success'})

@api_view(['POST'])
@permission_classes([AllowAny])
def fail_video_task(request):
    scan_id = request.data.get('scan_id')
    if not scan_id:
        return JsonResponse({'error': 'scan_id is required'}, status=400)
        
    try:
        sales_scan = SalesScan.objects.get(id=scan_id)
    except SalesScan.DoesNotExist:
        return JsonResponse({'error': 'Scan not found'}, status=404)
        
    sales_scan.video_status = 'failed'
    sales_scan.save()
    return JsonResponse({'status': 'success'})

@api_view(['POST'])
@permission_classes([AllowAny])
def get_processed_video(request):
    scan_id = request.data.get('scan_id')
    target_ts = request.data.get('timestamp')
    
    if not scan_id:
        return JsonResponse({'error': 'scan_id is required'}, status=400)
        
    try:
        scan = SalesScan.objects.get(id=scan_id)
    except SalesScan.DoesNotExist:
        return JsonResponse({'error': 'Scan not found'}, status=404)
        
    if not scan.video_file:
        return JsonResponse({'error': 'Raw video file not found'}, status=404)
    
    input_path = scan.video_file.path
    if not os.path.exists(input_path):
        return JsonResponse({'error': f'Video file not found on disk at {input_path}'}, status=404)

    if target_ts:
        # Clipping with Overlay logic
        try:
            target_ts = int(target_ts)
        except ValueError:
            return JsonResponse({'error': 'Invalid timestamp format'}, status=400)
            
        # Get min_ts to calculate relative start for clipping and offset for overlays
        all_logs_ts = [log['timestamp'] for box in scan.logs for log in box if isinstance(log, dict) and 'timestamp' in log]
        if not all_logs_ts:
            return JsonResponse({'error': 'No logs found to calculate relative time'}, status=400)
        
        min_ts = min(all_logs_ts)
        rel_start = (target_ts - min_ts) / 1000.0 - 2.0
        if rel_start < 0: rel_start = 0
        
        output_name = f"{scan.bill_no}_{target_ts}.mp4"
        output_path = os.path.join(os.path.dirname(input_path), output_name)
        if os.path.exists(output_path):
            os.remove(output_path)
                    
        # For clipping with text, we MUST re-encode.
        vf_chain = _get_video_filters(scan, rel_start_offset=rel_start)
        cmd = [
            "ffmpeg", "-ss", str(rel_start), "-i", input_path,
            "-t", "30",
            # "-vf", vf_chain,
            # "-vcodec", "libx264",
            "-c:v", "copy",
            "-preset", "ultrafast",
            "-an", "-y",
            output_path
        ]
    else:
        # Full Video with Text Overlay logic
        output_path = os.path.join(os.path.dirname(input_path), f"{scan.bill_no}.mp4")
        if os.path.exists(output_path):
            os.remove(output_path)

        vf_chain = _get_video_filters(scan)
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", vf_chain,
            "-vcodec", "libx264",
            "-an", "-y",
            output_path
        ]
    
    try:
        subprocess.run(cmd, check=True)
        return JsonResponse({'filepath': get_media_url(output_path)})
    except subprocess.CalledProcessError as e:
        return JsonResponse({'error': 'Video processing failed', 'details': str(e)}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
