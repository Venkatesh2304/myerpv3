from django.urls.conf import include
from django.urls import path
from . import views
from bill.modelviews import *
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'billing_status', BillingProcessStatusViewSet)
router.register(r'billing', BillingViewSet)
router.register(r'order', OrderViewSet)
router.register(r'bill', BillViewSet)

urlpatterns = [
    path("start_billing/", views.start_billing, name="start_billing"),
    path('', include(router.urls)),
]
