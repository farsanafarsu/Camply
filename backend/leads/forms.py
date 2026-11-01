from django import forms

from billing.forms import RupeeField

from .models import Lead


class LeadForm(forms.ModelForm):
    value = RupeeField(label="Deal value (₹)", required=False)

    class Meta:
        model = Lead
        fields = ["client", "campaign", "full_name", "email", "phone", "city", "message", "consent",
                  "utm_source", "utm_medium", "utm_campaign"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, clients, campaigns, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = clients
        self.fields["campaign"].queryset = campaigns
        self.fields["campaign"].required = False

    def clean(self):
        data = super().clean()
        if not (data.get("email") or data.get("phone")):
            raise forms.ValidationError("Add an email address or a phone number.")
        return data


class LeadUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=Lead.Status.choices)
    assigned_to = forms.ChoiceField(required=False, label="Assigned to")
    value = RupeeField(label="Deal value (₹)", required=False)
    remind_at = forms.DateTimeField(required=False, label="Remind me on",
                                    widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))

    def __init__(self, *args, people, **kwargs):
        super().__init__(*args, **kwargs)
        self.people = {str(u.pk): u for u in people}
        self.fields["assigned_to"].choices = [("", "Nobody")] + [(pk, u.display_name) for pk, u in self.people.items()]

    def clean_assigned_to(self):
        return self.people.get(self.cleaned_data.get("assigned_to") or "")
