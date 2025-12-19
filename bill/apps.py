from django.apps import AppConfig
from django.db.models.signals import post_migrate

def run_my_startup_logic(sender, **kwargs):
    from .models import Billing
    Billing.objects.update(ongoing=False)

class BillConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bill"
    def ready(self):
        post_migrate.connect(run_my_startup_logic, sender=self)
