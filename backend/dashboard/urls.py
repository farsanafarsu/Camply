from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("campaigns/", views.campaigns, name="campaigns"),
    path("campaigns/<str:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<str:pk>/status/", views.campaign_status, name="campaign_status"),
    path("reports/", views.reports, name="reports"),
    path("reports/export.csv", views.reports_csv, name="reports_csv"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("copilot/", views.planned, {"section": "copilot"}, name="copilot"),
]
