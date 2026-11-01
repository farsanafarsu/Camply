"""Creative Studio: uploads, platform checks, approval workflow by role, versions, file access."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import User
from creatives.models import Creative
from workspace.models import Client, Membership, Organization, Role

pytestmark = pytest.mark.django_db


def make_user(email):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(email=email, password="creative-pass-123")
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


def png(width=1080, height=1080):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "#FF6B35").save(buffer, "PNG")
    return SimpleUploadedFile("ad.png", buffer.getvalue(), content_type="image/png")


@pytest.fixture
def team(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    org = Organization.objects.create(name="Agency", state="Kerala")
    alpha = Client.objects.create(organization=org, name="Alpha")
    beta = Client.objects.create(organization=org, name="Beta")
    people = {}
    for key, role, clients in (("manager", Role.CAMPAIGN_MANAGER, [alpha]), ("client", Role.CLIENT, [alpha]),
                               ("viewer", Role.VIEWER, [alpha]), ("beta_manager", Role.CAMPAIGN_MANAGER, [beta])):
        user = make_user(f"{key}@agency.test")
        m = Membership.objects.create(organization=org, user=user, role=role)
        m.clients.set(clients)
        people[key] = user
    return {"org": org, "alpha": alpha, "beta": beta, **people}


def upload(client, team, **extra):
    data = {"client": str(team["alpha"].pk), "name": "Onam offer", "kind": "image", "file": png(),
            "headline": "Onam special: 30% off", "platforms": ["meta"], "tags_text": "Onam, offer, onam", "language": "en"}
    data.update(extra)
    return client.post(reverse("creatives:create"), data)


def test_upload_reads_image_size_and_tags(client, team):
    client.force_login(team["manager"])
    upload(client, team)
    creative = Creative.objects.get()
    assert (creative.width, creative.height) == (1080, 1080)
    assert creative.tags == ["onam", "offer"] and creative.status == Creative.Status.DRAFT
    html = client.get(reverse("creatives:detail", args=[creative.pk])).content.decode()
    assert "fits 1080×1080" in html


def test_wrong_file_type_is_rejected(client, team):
    client.force_login(team["manager"])
    bad = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
    upload(client, team, file=bad)
    assert not Creative.objects.exists()


def test_full_approval_flow_by_role(client, team):
    client.force_login(team["manager"])
    upload(client, team)
    creative = Creative.objects.get()
    url = reverse("creatives:transition", args=[creative.pk])
    client.post(url, {"action": "submit"})
    client.post(url, {"action": "approve_internal"})
    creative.refresh_from_db()
    assert creative.status == Creative.Status.CLIENT_APPROVAL

    # The manager can't sign off on the client's behalf.
    assert client.post(url, {"action": "approve_client"}).status_code == 403

    client.force_login(team["client"])
    client.post(url, {"action": "approve_client"})
    creative.refresh_from_db()
    assert creative.status == Creative.Status.READY
    assert creative.reviews.count() == 3


def test_requesting_changes_needs_a_comment(client, team):
    client.force_login(team["manager"])
    upload(client, team)
    creative = Creative.objects.get()
    url = reverse("creatives:transition", args=[creative.pk])
    client.post(url, {"action": "submit"})
    client.post(url, {"action": "request_changes"})
    creative.refresh_from_db()
    assert creative.status == Creative.Status.INTERNAL_REVIEW
    client.post(url, {"action": "request_changes", "comment": "Logo too small"})
    creative.refresh_from_db()
    assert creative.status == Creative.Status.DRAFT


def test_viewer_cannot_create_or_move_creatives(client, team):
    client.force_login(team["viewer"])
    assert client.get(reverse("creatives:create")).status_code == 403
    client.force_login(team["manager"])
    upload(client, team)
    creative = Creative.objects.get()
    client.force_login(team["viewer"])
    assert client.post(reverse("creatives:transition", args=[creative.pk]), {"action": "submit"}).status_code == 403


def test_new_version_keeps_history(client, team):
    client.force_login(team["manager"])
    upload(client, team)
    first = Creative.objects.get()
    client.post(reverse("creatives:edit", args=[first.pk]), {
        "client": str(team["alpha"].pk), "name": "Onam offer", "kind": "image", "headline": "Onam: 40% off",
        "platforms": ["meta"], "language": "en", "save_as_new_version": "on",
    })
    second = Creative.objects.exclude(pk=first.pk).get()
    first.refresh_from_db()
    assert second.version == 2 and second.root == first and first.headline == "Onam special: 30% off"
    assert second.file.name == first.file.name


def test_files_are_not_served_across_clients(client, team):
    client.force_login(team["manager"])
    upload(client, team)
    creative = Creative.objects.get()
    assert client.get(reverse("creatives:file", args=[creative.pk])).status_code == 200
    client.force_login(team["beta_manager"])
    assert client.get(reverse("creatives:file", args=[creative.pk])).status_code == 404
    client.logout()
    assert client.get(reverse("creatives:file", args=[creative.pk])).status_code == 302
