from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
from core.models import Company
from ledger.logic import import_ledger_data

@api_view(['POST'])
@parser_classes([MultiPartParser])
def import_ledger_view(request):
    company_id = request.data.get('company')
    file = request.FILES.get('file')

    if not company_id or not file:
        return Response({'error': 'Company and file are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return Response({'error': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    # Save file temporarily
    file_path = default_storage.save(f'tmp/{file.name}', ContentFile(file.read()))
    full_path = default_storage.path(file_path)

    try:
        success, message = import_ledger_data(company, full_path)
        if success:
            return Response({'message': message}, status=status.HTTP_200_OK)
        else:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        # Clean up
        if os.path.exists(full_path):
            os.remove(full_path)
