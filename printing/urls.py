from django.urls import path
from . import views

urlpatterns = [
    path("print_bills/", views.print_bills, name="print_bills"),
]
