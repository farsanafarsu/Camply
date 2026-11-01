from django.contrib import admin

from .models import Invoice, LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["entry_date", "client", "kind", "amount_paise", "reference"]
    list_filter = ["kind"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "client", "issue_date", "total_paise", "status"]
    list_filter = ["status"]
