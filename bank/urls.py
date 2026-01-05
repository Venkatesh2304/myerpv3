
from bank import views
from django.urls.conf import include
from django.urls.conf import path
from bank.modelviews import ChequeViewSet,BankStatementViewSet,BankViewSet
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r'cheque', ChequeViewSet)
router.register(r'bankstatement', BankStatementViewSet)
router.register(r'bank', BankViewSet)

urlpatterns = [
    path('refresh_bank/', views.refresh_bank),
    path('bank_collection/', views.bank_collection),
    path('deposit_slip/', views.generate_deposit_slip),
    path('bank_statement_upload/', views.bank_statement_upload),
    path('match_upi/', views.auto_match_upi),
    path('match_neft/', views.auto_match_neft),
    path('cheque_match/', views.cheque_match),
    path('push_collection/', views.push_collection),
    path('smart_match/',views.smart_match),
    path('', include(router.urls)),
]
