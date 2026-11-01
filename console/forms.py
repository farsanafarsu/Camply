from django import forms

from workspace.models import Organization, Role


class UserForm(forms.Form):
    """Create a login (or update an existing one with the same email) and give it an agency role."""

    email = forms.EmailField()
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    password = forms.CharField(
        min_length=8, widget=forms.PasswordInput(render_value=False),
        help_text="At least 8 characters. They can change it after signing in.",
    )
    organization = forms.ChoiceField(label="Agency", required=False)
    role = forms.ChoiceField(choices=Role.choices, initial=Role.OWNER)
    platform_admin = forms.BooleanField(
        required=False, label="Platform admin",
        help_text="Can open this console and see every agency. Leave off for normal users.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orgs = {str(o.pk): o for o in Organization.objects.order_by("name")}
        self.fields["organization"].choices = [("", "No agency")] + [(pk, o.name) for pk, o in self.orgs.items()]

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_organization(self):
        value = self.cleaned_data.get("organization")
        return self.orgs.get(value) if value else None

    def clean(self):
        data = super().clean()
        if not data.get("organization") and not data.get("platform_admin"):
            raise forms.ValidationError("Choose an agency, or make them a platform admin.")
        return data
