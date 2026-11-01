from django import forms

from .models import Rule


class RuleForm(forms.Form):
    name = forms.CharField(max_length=150)
    kind = forms.ChoiceField(label="When", choices=Rule.Kind.choices)
    client = forms.ChoiceField(required=False, label="Client")
    percent = forms.IntegerField(required=False, min_value=1, max_value=500, label="Percentage",
                                 help_text="For budget rules, e.g. 80")
    cpl_rupees = forms.DecimalField(required=False, min_value=1, max_digits=10, decimal_places=2,
                                    label="Cost per lead limit (₹)")
    days = forms.IntegerField(required=False, min_value=1, max_value=90, label="Days to look back", initial=7)
    frequency = forms.ChoiceField(required=False, choices=[("weekly", "Weekly (Mondays)"), ("monthly", "Monthly (1st)")])
    recipients = forms.CharField(required=False, label="Email these people",
                                 help_text="Comma-separated email addresses. Alerts always show in Camply too.")

    def __init__(self, *args, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = {str(c.pk): c for c in clients}
        self.fields["client"].choices = [("", "All clients")] + [(pk, c.name) for pk, c in self.clients.items()]

    def clean_client(self):
        return self.clients.get(self.cleaned_data.get("client") or "")

    def clean_recipients(self):
        from django.core.validators import validate_email

        emails = [e.strip().lower() for e in self.cleaned_data.get("recipients", "").split(",") if e.strip()]
        for email in emails:
            try:
                validate_email(email)
            except forms.ValidationError:
                raise forms.ValidationError(f"“{email}” isn't a valid email address.") from None
        return emails[:20]

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        params = {}
        for name in Rule.PARAMS.get(kind, []):
            value = data.get(name)
            if value in (None, ""):
                defaults = {"percent": 80, "days": 7, "frequency": "weekly"}
                if name not in defaults:
                    self.add_error(name, "This rule needs this value.")
                    continue
                value = defaults[name]
            params[name] = float(value) if name == "cpl_rupees" else value
        if kind == Rule.Kind.SCHEDULED_REPORT and not data.get("recipients"):
            self.add_error("recipients", "Add at least one email address for the summary.")
        data["params"] = params
        return data
