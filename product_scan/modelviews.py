from rest_framework import viewsets
from .models import SalesScan
from .serializers import SalesScanSerializer

class SalesScanViewSet(viewsets.ModelViewSet):
    queryset = SalesScan.objects.all()
    serializer_class = SalesScanSerializer
