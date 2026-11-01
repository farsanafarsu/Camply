from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("wallet/", views.wallet, name="wallet"),
    path("wallet/entries/", views.add_entry, name="add_entry"),
    path("invoices/", views.invoices, name="invoices"),
    path("invoices/new/", views.create_invoice, name="create_invoice"),
    path("invoices/<str:pk>/", views.invoice_detail, name="invoice_detail"),
]
