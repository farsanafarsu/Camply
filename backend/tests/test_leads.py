"""Leads: inbox scoping, pipeline updates, notes, webhook intake, duplicates and export."""

import json

import pytest
from django.urls import reverse

from accounts.models import User
from leads.models import Lead, LeadWebhook
from workspace.models import Client, Membership, Organization, Role

pytestmark = pytest.mark.django_db


def make_user(email):
    from allauth.account.models import EmailAddress

    user = User.objects.create_user(email=email, password="leads-pass-123")
    EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
    return user


@pytest.fixture
def setup():
    org = Organization.objects.create(name="Agency", state="Kerala")
    alpha = Client.objects.create(organization=org, name="Alpha")
    beta = Client.objects.create(organization=org, name="Beta")
    manager = make_user("manager@agency.test")
    m = Membership.objects.create(organization=org, user=manager, role=Role.CAMPAIGN_MANAGER)
    m.clients.set([alpha])
    viewer = make_user("viewer@agency.test")
    Membership.objects.create(organization=org, user=viewer, role=Role.VIEWER, all_clients=True)
    Lead.objects.create(organization=org, client=alpha, full_name="Asha", email="asha@x.test")
    Lead.objects.create(organization=org, client=beta, full_name="Bilal", email="bilal@x.test")
    return {"org": org, "alpha": alpha, "beta": beta, "manager": manager, "viewer": viewer}


def test_inbox_only_shows_assigned_clients(client, setup):
    client.force_login(setup["manager"])
    html = client.get(reverse("leads:inbox")).content.decode()
    assert "Asha" in html and "Bilal" not in html


def test_viewer_has_no_leads_access(client, setup):
    client.force_login(setup["viewer"])
    assert client.get(reverse("leads:inbox")).status_code == 403


def test_add_lead_flags_duplicate_by_phone(client, setup):
    client.force_login(setup["manager"])
    Lead.objects.create(organization=setup["org"], client=setup["alpha"], phone="9876543210")
    client.post(reverse("leads:add"), {"client": str(setup["alpha"].pk), "full_name": "Again",
                                       "phone": "+91 98765 43210"})
    lead = Lead.objects.get(full_name="Again")
    assert lead.phone == "9876543210" and lead.duplicate_of is not None


def test_update_status_assign_and_note(client, setup):
    client.force_login(setup["manager"])
    lead = Lead.objects.get(full_name="Asha")
    client.post(reverse("leads:detail", args=[lead.pk]),
                {"status": Lead.Status.QUALIFIED, "assigned_to": str(setup["manager"].pk)})
    client.post(reverse("leads:detail", args=[lead.pk]), {"note": "Called, visiting Saturday"})
    lead.refresh_from_db()
    assert lead.status == Lead.Status.QUALIFIED and lead.assigned_to == setup["manager"]
    assert lead.notes.get().body == "Called, visiting Saturday"


def test_cannot_open_lead_of_unassigned_client(client, setup):
    client.force_login(setup["manager"])
    other = Lead.objects.get(full_name="Bilal")
    assert client.get(reverse("leads:detail", args=[other.pk])).status_code == 404


def test_webhook_accepts_form_and_json(client, setup):
    hook = LeadWebhook.objects.create(organization=setup["org"], client=setup["alpha"])
    url = reverse("leads:webhook", args=[hook.token])
    assert client.post(url, {"name": "Form Lead", "phone": "98470 11111", "utm_source": "facebook"}).status_code == 200
    assert client.post(url, json.dumps({"name": "Json Lead", "email": "j@x.test", "consent": True}),
                       content_type="application/json").status_code == 200
    form_lead = Lead.objects.get(full_name="Form Lead")
    assert form_lead.client == setup["alpha"] and form_lead.source == Lead.Source.WEBHOOK
    assert form_lead.utm_source == "facebook"
    assert Lead.objects.get(full_name="Json Lead").consent is True
    assert client.post(url, {"name": "No contact"}).status_code == 400
    assert client.post(reverse("leads:webhook", args=["wrong-token"]), {"email": "a@b.test"}).status_code == 404


def test_export_csv_is_scoped(client, setup):
    client.force_login(setup["manager"])
    body = client.get(reverse("leads:export")).content.decode("utf-8-sig")
    assert "Asha" in body and "Bilal" not in body


def test_utm_and_tracking_pages_load(client, setup):
    client.force_login(setup["manager"])
    assert client.get(reverse("leads:utm")).status_code == 200
    assert client.get(reverse("leads:tracking")).status_code == 200
    assert client.get(reverse("leads:sources")).status_code == 200
