from datetime import timedelta

from django import forms
from django.utils import timezone

from camply.money import rupees_to_paise

from .models import LedgerEntry


class RupeeField(forms.DecimalField):
    """Accepts rupees (e.g. 25000.50) and cleans to integer paise."""

    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 0.01)
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        return rupees_to_paise(value) if value is not None else None


class LedgerEntryForm(forms.Form):
    client = forms.ChoiceField()
    kind = forms.ChoiceField(choices=LedgerEntry.Kind.choices)
    amount = RupeeField(label="Amount (₹)")
    is_credit_adjustment = forms.TypedChoiceField(
        label="Adjustment direction", choices=[("1", "Credit (add)"), ("0", "Debit (subtract)")],
        coerce=lambda v: v == "1", required=False, initial="1",
    )
    entry_date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))
    reference = forms.CharField(max_length=120, required=False, help_text="UTR, Razorpay payment ID or invoice no.")
    note = forms.CharField(max_length=300, required=False)

    def __init__(self, *args, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = {str(c.pk): c for c in clients}
        self.fields["client"].choices = [(pk, c.name) for pk, c in self.clients.items()]

    def clean_client(self):
        return self.clients[self.cleaned_data["client"]]


class InvoiceForm(forms.Form):
    client = forms.ChoiceField()
    description = forms.CharField(max_length=200, initial="Digital advertising management services")
    amount = RupeeField(label="Service fee before GST (₹)")
    issue_date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))
    due_in_days = forms.IntegerField(min_value=0, max_value=90, initial=15, label="Due in (days)")

    def __init__(self, *args, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = {str(c.pk): c for c in clients}
        self.fields["client"].choices = [(pk, c.name) for pk, c in self.clients.items()]

    def clean_client(self):
        return self.clients[self.cleaned_data["client"]]

    @property
    def due_date(self):
        return self.cleaned_data["issue_date"] + timedelta(days=self.cleaned_data["due_in_days"])
