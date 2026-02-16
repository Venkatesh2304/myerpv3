from django.urls import path
from .views import import_ledger_view

urlpatterns = [
    path('import/', import_ledger_view, name='import_ledger'),
]
