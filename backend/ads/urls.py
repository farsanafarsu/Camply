from django.urls import path

from . import views

app_name = "ads"

urlpatterns = [
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/<str:pk>/sync/", views.sync_now, name="sync_now"),
    path("accounts/<str:pk>/client/", views.assign_client, name="assign_client"),
    path("integrations/", views.integrations, name="integrations"),
]
