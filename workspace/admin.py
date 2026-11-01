from django.contrib import admin

from .models import Client, Invitation, Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "state", "gstin", "created_at"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "industry", "is_active"]
    list_filter = ["is_active"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "all_clients"]
    list_filter = ["role"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "organization", "role", "created_at", "accepted_at"]
