from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("workspace/", include("workspace.urls")),
    path("ads/", include("ads.urls")),
    path("billing/", include("billing.urls")),
    path("", include("dashboard.urls")),
]

handler403 = "dashboard.views.permission_denied"
