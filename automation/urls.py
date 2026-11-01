from django.urls import path

from . import views

app_name = "automation"

urlpatterns = [
    path("", views.rules, name="rules"),
    path("run/", views.run_now, name="run"),
    path("rules/<str:pk>/", views.rule_action, name="rule_action"),
    path("alerts/", views.alerts, name="alerts"),
    path("alerts/update/", views.alert_action, name="alert_action"),
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<str:pk>/", views.approval_decide, name="approval_decide"),
]
