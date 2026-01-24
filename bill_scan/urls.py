from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import vehicle_bills
from .modelviews import VehicleViewSet

router = DefaultRouter()
router.register(r'vehicle', VehicleViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('vehicle_bills/', vehicle_bills, name='vehicle_bills'),
]
