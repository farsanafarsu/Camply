from django.urls import path

from . import views

app_name = "leads"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("new/", views.add, name="add"),
    path("export.csv", views.export_csv, name="export"),
    path("sources/", views.sources, name="sources"),
    path("utm/", views.utm_builder, name="utm"),
    path("tracking/", views.tracking, name="tracking"),
    path("in/<str:token>/", views.webhook, name="webhook"),
    path("<str:pk>/", views.detail, name="detail"),
]
