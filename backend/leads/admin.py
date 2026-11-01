from django.contrib import admin

from .models import Lead, LeadNote, LeadWebhook

admin.site.register(Lead)
admin.site.register(LeadNote)
admin.site.register(LeadWebhook)
