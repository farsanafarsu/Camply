from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ads.models import MetricSnapshot
from audit import log as audit
from camply.money import calculate_gst
from workspace.decorators import require_perm
from workspace.scoping import allowed_clients, get_scoped_or_404, scope

from .forms import InvoiceForm, LedgerEntryForm
from .models import Invoice, LedgerEntry, ledger_balances_by_client


@login_required
@require_perm("budget.view")
def wallet(request):
    membership = request.membership
    clients = list(allowed_clients(membership))
    entries = scope(LedgerEntry.objects.select_related("client", "created_by"), membership)
    month_start = timezone.localdate().replace(day=1)
    spend_by_client = {
        r["client_id"]: r["spend"]
        for r in scope(MetricSnapshot.objects.filter(date__gte=month_start), membership)
        .values("client_id").annotate(spend=Sum("spend_paise"))
    }
    balance_by_client = ledger_balances_by_client(entries)
    balances = []
    for client in clients:
        balances.append({
            "client": client,
            "balance_paise": balance_by_client.get(client.pk, 0),
            "platform_spend_mtd": spend_by_client.get(client.pk, 0),
            "budget_paise": client.monthly_budget_paise,
            "utilisation": (spend_by_client.get(client.pk, 0) * 100 / client.monthly_budget_paise)
            if client.monthly_budget_paise else None,
        })
    selected = request.GET.get("client", "")
    shown = entries.filter(client_id=selected) if selected in {str(c.pk) for c in clients} else entries
    return render(request, "billing/wallet.html", {
        "balances": balances,
        "entries": shown[:100],
        "selected": selected,
        "clients": clients,
        "form": LedgerEntryForm(clients=clients),
        "razorpay_ready": bool(settings.RAZORPAY_KEY_ID),
    })


@login_required
@require_POST
@require_perm("budget.manage")
def add_entry(request):
    clients = list(allowed_clients(request.membership))
    form = LedgerEntryForm(request.POST, clients=clients)
    if not form.is_valid():
        for field, errors in form.errors.items():
            messages.error(request, f"{form.fields[field].label or field}: {' '.join(errors)}" if field in form.fields
                           else " ".join(errors))
        return redirect("billing:wallet")
    data = form.cleaned_data
    entry = LedgerEntry.objects.create(
        organization=request.organization,
        client=data["client"],
        kind=data["kind"],
        amount_paise=data["amount"],
        is_credit_adjustment=data["is_credit_adjustment"] if data["kind"] == LedgerEntry.Kind.ADJUSTMENT else True,
        entry_date=data["entry_date"],
        reference=data["reference"],
        note=data["note"],
        created_by=request.user,
    )
    audit.record(organization=request.organization, action="ledger.add", entity=entry, request=request,
                 after={"kind": entry.kind, "amount_paise": entry.amount_paise, "reference": entry.reference})
    messages.success(request, f"Recorded {entry.get_kind_display().lower()} for {entry.client}.")
    return redirect("billing:wallet")


@login_required
@require_perm("budget.view")
def invoices(request):
    clients = list(allowed_clients(request.membership))
    form = InvoiceForm(clients=clients)
    return render(request, "billing/invoices.html", {
        "invoices": scope(Invoice.objects.select_related("client"), request.membership)[:100],
        "form": form,
        "gst_rate": settings.GST_RATE_PERCENT,
    })


def next_invoice_number(organization, issue_date):
    # Indian financial year runs April–March: FY 2026-27 → "2627".
    fy_start = issue_date.year if issue_date.month >= 4 else issue_date.year - 1
    prefix = f"CMP/{str(fy_start)[2:]}{str(fy_start + 1)[2:]}/"
    count = Invoice.objects.filter(organization=organization, number__startswith=prefix).count()
    return f"{prefix}{count + 1:04d}"


@login_required
@require_POST
@require_perm("budget.manage")
def create_invoice(request):
    clients = list(allowed_clients(request.membership))
    form = InvoiceForm(request.POST, clients=clients)
    if not form.is_valid():
        messages.error(request, "Please check the invoice details: " + "; ".join(
            f"{k}: {' '.join(v)}" for k, v in form.errors.items()))
        return redirect("billing:invoices")
    org = request.organization
    client = form.cleaned_data["client"]
    issue_date = form.cleaned_data["issue_date"]
    gst = calculate_gst(form.cleaned_data["amount"], supplier_state=org.state, customer_state=client.state,
                        rate_percent=settings.GST_RATE_PERCENT)
    invoice = Invoice.objects.create(
        organization=org,
        client=client,
        number=next_invoice_number(org, issue_date),
        issue_date=issue_date,
        due_date=form.due_date,
        description=form.cleaned_data["description"],
        place_of_supply=client.state or "",
        subtotal_paise=gst["subtotal"],
        cgst_paise=gst["cgst"],
        sgst_paise=gst["sgst"],
        igst_paise=gst["igst"],
        total_paise=gst["total"],
        status=Invoice.Status.ISSUED,
        created_by=request.user,
    )
    audit.record(organization=org, action="invoice.create", entity=invoice, request=request,
                 after={"number": invoice.number, "total_paise": invoice.total_paise})
    messages.success(request, f"Invoice {invoice.number} created.")
    return redirect("billing:invoice_detail", pk=invoice.pk)


@login_required
@require_perm("budget.view")
def invoice_detail(request, pk):
    invoice = get_scoped_or_404(Invoice.objects.select_related("client", "organization"), request.membership, pk=pk)
    return render(request, "billing/invoice_detail.html", {"invoice": invoice, "gst_rate": settings.GST_RATE_PERCENT})
