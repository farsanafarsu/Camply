from django import forms

from billing.forms import RupeeField

from .models import STATE_CHOICES, Client, Organization, Role


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "legal_name", "gstin", "state", "city", "billing_email"]

    def clean_gstin(self):
        return validate_gstin(self.cleaned_data.get("gstin", ""))


class ClientForm(forms.ModelForm):
    monthly_budget = RupeeField(label="Monthly ad budget (₹)", required=False)

    class Meta:
        model = Client
        fields = ["name", "industry", "contact_name", "contact_email", "gstin", "state"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = [("", "—")] + STATE_CHOICES
        if self.instance.pk and self.instance.monthly_budget_paise:
            self.initial["monthly_budget"] = self.instance.monthly_budget_paise / 100

    def clean_gstin(self):
        return validate_gstin(self.cleaned_data.get("gstin", ""))

    def save(self, commit=True):
        self.instance.monthly_budget_paise = self.cleaned_data.get("monthly_budget")
        return super().save(commit)


def validate_gstin(value):
    value = (value or "").strip().upper()
    if value and (len(value) != 15 or not value[:2].isdigit()):
        raise forms.ValidationError("A GSTIN has 15 characters and starts with a 2-digit state code.")
    return value


class MemberAccessForm(forms.Form):
    role = forms.ChoiceField()
    all_clients = forms.BooleanField(required=False, label="Access to all clients")
    clients = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, assignable_roles, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [(r.value, r.label) for r in assignable_roles]
        self.client_map = {str(c.pk): c for c in clients}
        self.fields["clients"].choices = [(pk, c.name) for pk, c in self.client_map.items()]

    def clean_clients(self):
        return [self.client_map[pk] for pk in self.cleaned_data["clients"]]

    def clean(self):
        data = super().clean()
        if data.get("role") == Role.OWNER:
            data["all_clients"] = True
        return data


class InviteForm(MemberAccessForm):
    email = forms.EmailField()

    field_order = ["email", "role", "all_clients", "clients"]
