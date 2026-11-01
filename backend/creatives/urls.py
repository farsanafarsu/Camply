from django.urls import path

from . import views

app_name = "creatives"

urlpatterns = [
    path("", views.library, name="library"),
    path("new/", views.create, name="create"),
    path("<str:pk>/", views.detail, name="detail"),
    path("<str:pk>/edit/", views.edit, name="edit"),
    path("<str:pk>/file/", views.file, name="file"),
    path("<str:pk>/review/", views.transition, name="transition"),
]
