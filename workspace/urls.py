from django.urls import path

from . import views

app_name = "workspace"

urlpatterns = [
    path("onboarding/", views.onboarding, name="onboarding"),
    path("switch/", views.switch_organization, name="switch"),
    path("clients/", views.clients, name="clients"),
    path("clients/<str:pk>/", views.client_edit, name="client_edit"),
    path("team/", views.team, name="team"),
    path("team/invite/", views.invite, name="invite"),
    path("team/<str:pk>/", views.member_edit, name="member_edit"),
    path("invite/<str:token>/", views.accept_invite, name="accept_invite"),
    path("settings/", views.settings_view, name="settings"),
    path("profile/", views.profile, name="profile"),
]
