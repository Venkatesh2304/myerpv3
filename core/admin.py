from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from core import models

@admin.register(models.User)
class UserAdmin(DjangoUserAdmin):
    pass

@admin.register(models.Company)
class CompanyAdmin(admin.ModelAdmin):
    pass
