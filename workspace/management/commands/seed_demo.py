"""Create the PRception Media demo workspace with sandbox ad data.

    python manage.py seed_demo

Demo users sign in with the password in CAMPLY_DEMO_PASSWORD (.env).
"""

import os
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from ads.models import Ad, AdAccount, AdSet, Campaign, Platform
from ads.services import sync_account
from billing.models import Invoice, LedgerEntry
from camply.money import calculate_gst, rupees_to_paise
from workspace.models import Client, Membership, Organization, Role

# Fictional clients and campaigns for demos.
CLIENTS = [
    {
        "name": "Kovalam Bay Resorts", "industry": "Hospitality", "state": "Kerala", "budget": 180000,
        "accounts": {
            Platform.META: ["Monsoon Getaway Packages", "Weekend Staycation Leads", "Wedding Venue Enquiries"],
            Platform.GOOGLE: ["Search · Kovalam Resorts", "Performance Max · Bookings"],
        },
    },
    {
        "name": "Techno Skills Academy", "industry": "Education", "state": "Kerala", "budget": 150000,
        "accounts": {
            Platform.META: ["TVM Admissions 2026", "Data Science Batch – Lead Form"],
            Platform.GOOGLE: ["Search · Coding Courses Trivandrum"],
            Platform.TIKTOK: ["Student Stories – Reach"],
        },
    },
    {
        "name": "Lumen Dental Care", "industry": "Healthcare", "state": "Tamil Nadu", "budget": 90000,
        "accounts": {
            Platform.GOOGLE: ["Search · Dental Implants", "Search · Braces & Aligners"],
            Platform.META: ["Smile Makeover Offer"],
        },
    },
    {
        "name": "Malabar Spice Co.", "industry": "D2C / Food", "state": "Karnataka", "budget": 80000,
        "accounts": {
            Platform.META: ["Onam Gift Boxes – Sales"],
            Platform.TIKTOK: ["Kitchen Hacks – Creators"],
            Platform.OPENAI: ["Recipe Discovery – ChatGPT"],
        },
    },
]

USERS = [
    ("farsana@prception.test", "Farsana", "N", Role.OWNER, None),
    ("arjun@prception.test", "Arjun", "Menon", Role.CAMPAIGN_MANAGER, ["Kovalam Bay Resorts", "Techno Skills Academy"]),
    ("diya@prception.test", "Diya", "Thomas", Role.ANALYST, ["Lumen Dental Care", "Malabar Spice Co."]),
    ("accounts@prception.test", "Rahul", "Nair", Role.FINANCE, None),
    ("marketing@kovalambay.test", "Anita", "Varghese", Role.CLIENT, ["Kovalam Bay Resorts"]),
]


class Command(BaseCommand):
    help = "Create the PRception Media demo organization with clients, ad accounts and sandbox results."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=120, help="Days of sandbox history to generate.")

    def handle(self, *args, days, **options):
        password = os.environ.get("CAMPLY_DEMO_PASSWORD")
        if not password:
            raise CommandError("Set CAMPLY_DEMO_PASSWORD in .env before seeding demo users.")
        if Organization.objects.filter(slug="prception-media").exists():
            raise CommandError("The demo organization already exists. Drop the database to re-seed.")

        org = Organization.objects.create(
            name="PRception Media", slug="prception-media", legal_name="PRception Media",
            state="Kerala", city="Thiruvananthapuram", billing_email="accounts@prception.test",
        )
        clients = {}
        for spec in CLIENTS:
            clients[spec["name"]] = Client.objects.create(
                organization=org, name=spec["name"], industry=spec["industry"], state=spec["state"],
                monthly_budget_paise=rupees_to_paise(spec["budget"]),
            )

        owner = None
        for email, first, last, role, client_names in USERS:
            user = User.objects.create_user(email=email, password=password, first_name=first, last_name=last)
            self._verify_email(user)
            membership = Membership.objects.create(
                organization=org, user=user, role=role, all_clients=client_names is None,
            )
            if client_names:
                membership.clients.set([clients[n] for n in client_names])
            if role == Role.OWNER:
                owner = user

        n = 0
        for spec in CLIENTS:
            client = clients[spec["name"]]
            for platform, names in spec["accounts"].items():
                n += 1
                account = AdAccount.objects.create(
                    organization=org, client=client, platform=platform,
                    external_id=f"{platform}-{1000 + n}", name=f"{client.name} · {Platform(platform).label}",
                )
                for i, name in enumerate(names):
                    campaign = Campaign.objects.create(
                        organization=org, client=client, ad_account=account, platform=platform,
                        external_id=f"{account.external_id}-c{i + 1}", name=name, owner=owner,
                    )
                    self._ad_tree(campaign)
                summary = sync_account(account, days=days)
                self.stdout.write(f"  {account.name}: {summary['campaigns']} campaigns, {summary['rows']} rows")

        self._ledger(org, clients, owner)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {org.name}: {len(clients)} clients, {len(USERS)} users. Sign in as {USERS[0][0]}."
        ))

    def _verify_email(self, user):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)

    def _ad_tree(self, campaign):
        for s in range(2):
            ad_set = AdSet.objects.create(
                organization_id=campaign.organization_id, client_id=campaign.client_id, campaign=campaign,
                external_id=f"{campaign.external_id}-s{s + 1}",
                name=["Kerala · 25–45", "Lookalike 1% · India"][s] if campaign.platform == Platform.META
                else ["Exact match", "Broad match"][s],
                status=campaign.status, daily_budget_paise=rupees_to_paise(1500 + 500 * s),
            )
            for a in range(2):
                Ad.objects.create(
                    organization_id=campaign.organization_id, client_id=campaign.client_id, campaign=campaign,
                    ad_set=ad_set, external_id=f"{ad_set.external_id}-a{a + 1}",
                    name=f"Variant {'AB'[a]} · {['Carousel', 'Video 15s'][a]}",
                    review_status=Ad.ReviewStatus.APPROVED if (s + a) % 3 else Ad.ReviewStatus.PENDING,
                )

    def _ledger(self, org, clients, owner):
        today = timezone.localdate()
        for i, client in enumerate(clients.values()):
            deposit = rupees_to_paise(200000 - 30000 * i)
            fee = rupees_to_paise(25000 - 4000 * i)
            gst = calculate_gst(fee, supplier_state=org.state, customer_state=client.state)
            entries = [
                (LedgerEntry.Kind.DEPOSIT, deposit, f"UTR{4821930 + i}", "Advance for ad spend", 20),
                (LedgerEntry.Kind.AD_SPEND, int(deposit * 0.62), "", "Allocated to Meta and Google", 12),
                (LedgerEntry.Kind.SERVICE_FEE, fee, f"CMP/2627/{i + 1:04d}", "Monthly management fee", 5),
                (LedgerEntry.Kind.GST, gst["tax"], f"CMP/2627/{i + 1:04d}", "GST @ 18% on fee", 5),
            ]
            for kind, amount, reference, note, days_ago in entries:
                LedgerEntry.objects.create(
                    organization=org, client=client, kind=kind, amount_paise=amount, reference=reference,
                    note=note, entry_date=today - timedelta(days=days_ago), created_by=owner,
                )
            Invoice.objects.create(
                organization=org, client=client, number=f"CMP/2627/{i + 1:04d}",
                issue_date=today - timedelta(days=5), due_date=today + timedelta(days=10),
                place_of_supply=client.state, subtotal_paise=gst["subtotal"], cgst_paise=gst["cgst"],
                sgst_paise=gst["sgst"], igst_paise=gst["igst"], total_paise=gst["total"],
                status=Invoice.Status.PAID if i % 2 else Invoice.Status.ISSUED, created_by=owner,
            )
