from django.conf import settings
from django.db import models
from django.db.models import Sum


class LedgerEntry(models.Model):
    """A line in a client's internal wallet ledger.

    This is Camply's own record of money received from and allocated for a client. It is
    NOT the balance held by Meta, Google, TikTok or OpenAI. Platform spend, agency fees and
    GST are recorded as separate entries so they are never mixed together.
    """

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Client deposit"
        AD_SPEND = "ad_spend", "Ad spend allocation"
        SERVICE_FEE = "service_fee", "Agency service fee"
        GST = "gst", "GST on fee"
        REFUND = "refund", "Refund to client"
        ADJUSTMENT = "adjustment", "Adjustment"

    # Kinds that reduce the client's balance; amounts are stored positive and signed on read.
    DEBIT_KINDS = {Kind.AD_SPEND, Kind.SERVICE_FEE, Kind.GST, Kind.REFUND}

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.CASCADE, related_name="ledger_entries")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    amount_paise = models.BigIntegerField(help_text="Positive amount; direction comes from the kind.")
    is_credit_adjustment = models.BooleanField(default=True, help_text="For adjustments: credit (true) or debit.")
    entry_date = models.DateField()
    reference = models.CharField(max_length=120, blank=True, help_text="UTR, Razorpay payment ID, invoice no.")
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name_plural = "ledger entries"

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount_paise}"

    @property
    def is_debit(self):
        if self.kind == self.Kind.ADJUSTMENT:
            return not self.is_credit_adjustment
        return self.kind in self.DEBIT_KINDS

    @property
    def signed_paise(self):
        return -self.amount_paise if self.is_debit else self.amount_paise


def ledger_balance(entries) -> int:
    """Balance in paise for a queryset of ledger entries."""
    credits = entries.filter(kind=LedgerEntry.Kind.DEPOSIT).aggregate(t=Sum("amount_paise"))["t"] or 0
    debits = entries.filter(kind__in=list(LedgerEntry.DEBIT_KINDS)).aggregate(t=Sum("amount_paise"))["t"] or 0
    adjustments = entries.filter(kind=LedgerEntry.Kind.ADJUSTMENT)
    adj_credit = adjustments.filter(is_credit_adjustment=True).aggregate(t=Sum("amount_paise"))["t"] or 0
    adj_debit = adjustments.filter(is_credit_adjustment=False).aggregate(t=Sum("amount_paise"))["t"] or 0
    return credits + adj_credit - debits - adj_debit


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    organization = models.ForeignKey("workspace.Organization", on_delete=models.CASCADE)
    client = models.ForeignKey("workspace.Client", on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField(max_length=30)
    issue_date = models.DateField()
    due_date = models.DateField()
    description = models.CharField(max_length=200, default="Digital advertising management services")
    place_of_supply = models.CharField(max_length=60, blank=True)
    subtotal_paise = models.BigIntegerField()
    cgst_paise = models.BigIntegerField(default=0)
    sgst_paise = models.BigIntegerField(default=0)
    igst_paise = models.BigIntegerField(default=0)
    total_paise = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date", "-number"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="unique_invoice_number")]

    def __str__(self):
        return self.number

    @property
    def tax_paise(self):
        return self.cgst_paise + self.sgst_paise + self.igst_paise
