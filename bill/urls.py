from django.urls.conf import include
from django.urls import path
from . import views
from bill.modelviews import *
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'billing', BillingViewSet)
router.register(r'bill', BillViewSet)

urlpatterns = [
    path("get_order/", views.get_order, name="get_order"),
    path("post_order/", views.post_order, name="post_order"),
    path("order/", views.manage_order, name="manage_order"),
    path("party_credit/", views.party_credit, name="party_credit"),
    path('', include(router.urls)),
]
