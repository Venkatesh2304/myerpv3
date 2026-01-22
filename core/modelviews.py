from core.models import Company
from core.serializers import CompanySerializer
from rest_framework import viewsets

class CompanyModelViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
