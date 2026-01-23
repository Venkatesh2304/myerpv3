from load.serializers import LoadDetailSerializer,LoadSummarySerializer
from load.models import TruckLoad
from rest_framework import viewsets

class LoadSummaryViewSet(viewsets.ModelViewSet):
    queryset = TruckLoad.objects.all()
    serializer_class = LoadSummarySerializer 

class LoadDetailViewSet(viewsets.ModelViewSet):
    queryset = TruckLoad.objects.all()
    serializer_class = LoadDetailSerializer
