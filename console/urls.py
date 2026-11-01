from django.urls import path

from . import views

app_name = "console"

urlpatterns = [
    path("", views.overview, name="home"),
    path("agencies/", views.agencies, name="agencies"),
    path("agencies/<str:pk>/", views.agency_detail, name="agency_detail"),
    path("users/", views.users, name="users"),
    path("users/<str:pk>/status/", views.user_status, name="user_status"),
]
