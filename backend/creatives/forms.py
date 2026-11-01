from django import forms
from django.conf import settings

from ads.models import Platform

from .models import Creative

ALLOWED_TYPES = {
    Creative.Kind.IMAGE: ("image/jpeg", "image/png", "image/webp", "image/gif"),
    Creative.Kind.VIDEO: ("video/mp4", "video/quicktime", "video/webm"),
}


class CreativeForm(forms.ModelForm):
    platforms = forms.MultipleChoiceField(choices=Platform.choices, required=False,
                                          widget=forms.CheckboxSelectMultiple)
    tags_text = forms.CharField(label="Tags", required=False, help_text="Comma separated, e.g. onam, offer, carousel")
    save_as_new_version = forms.BooleanField(
        required=False, label="Save as a new version",
        help_text="Keeps the current version in the history. Approval starts again from Draft.",
    )

    class Meta:
        model = Creative
        fields = ["client", "campaign", "name", "kind", "file", "landing_url", "headline", "primary_text",
                  "description", "cta", "language"]
        widgets = {"primary_text": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, clients, campaigns, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = clients
        self.fields["campaign"].queryset = campaigns
        self.fields["campaign"].required = False
        if self.instance.pk:
            self.initial["platforms"] = self.instance.platforms
            self.initial["tags_text"] = ", ".join(self.instance.tags)
        else:
            del self.fields["save_as_new_version"]

    def clean_tags_text(self):
        raw = self.cleaned_data.get("tags_text", "")
        tags = []
        for tag in raw.split(","):
            tag = tag.strip().lower()[:40]
            if tag and tag not in tags:
                tags.append(tag)
        return tags[:20]

    def clean(self):
        data = super().clean()
        kind, upload = data.get("kind"), data.get("file")
        if kind in ALLOWED_TYPES and not upload and not (self.instance.pk and self.instance.file):
            self.add_error("file", f"Upload the {Creative.Kind(kind).label.lower()} file.")
        if upload and hasattr(upload, "content_type"):
            allowed = ALLOWED_TYPES.get(kind)
            if allowed and upload.content_type not in allowed:
                self.add_error("file", f"That file type isn't allowed for {Creative.Kind(kind).label.lower()}s.")
            if upload.size > settings.CREATIVE_MAX_UPLOAD_MB * 1024 * 1024:
                self.add_error("file", f"Files must be under {settings.CREATIVE_MAX_UPLOAD_MB} MB.")
        if kind == Creative.Kind.COPY and not (data.get("headline") or data.get("primary_text")):
            self.add_error("headline", "Ad copy needs a headline or primary text.")
        if kind == Creative.Kind.LANDING and not data.get("landing_url"):
            self.add_error("landing_url", "Add the landing page URL.")
        return data
