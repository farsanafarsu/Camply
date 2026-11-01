from django.contrib import admin

from .models import ActionRequest, Alert, Rule

admin.site.register(Rule)
admin.site.register(Alert)
admin.site.register(ActionRequest)
