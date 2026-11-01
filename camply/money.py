"""Money helpers. All amounts are stored as integer paise to avoid float rounding."""

from decimal import ROUND_HALF_UP, Decimal

PAISE_PER_RUPEE = 100


def rupees_to_paise(rupees) -> int:
    return int((Decimal(str(rupees)) * PAISE_PER_RUPEE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def group_indian(whole: int) -> str:
    """Group an integer the Indian way: 487320 -> '4,87,320', 12345678 -> '1,23,45,678'."""
    digits = str(abs(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        digits = ",".join(pairs + [tail])
    return f"-{digits}" if whole < 0 else digits


def format_number(value) -> str:
    """Format a count with Indian grouping (impressions, clicks, leads)."""
    if value is None:
        return "–"
    return group_indian(int(value))


def format_inr(paise, *, decimals: bool = False) -> str:
    """Format paise as rupees: 48732000 -> '₹4,87,320' (or '₹4,87,320.00' with decimals)."""
    if paise is None:
        return "–"
    paise = int(paise)
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    if decimals:
        rupees, fraction = divmod(paise, PAISE_PER_RUPEE)
        return f"{sign}₹{group_indian(rupees)}.{fraction:02d}"
    rupees = int((Decimal(paise) / PAISE_PER_RUPEE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{sign}₹{group_indian(rupees)}"


def format_inr_compact(paise) -> str:
    """Short form for chart axes and tight spaces: ₹950, ₹45.2K, ₹4.87L, ₹1.2Cr."""
    if paise is None:
        return "–"
    rupees = Decimal(int(paise)) / PAISE_PER_RUPEE
    sign = "-" if rupees < 0 else ""
    rupees = abs(rupees)
    for threshold, suffix in ((Decimal(10_000_000), "Cr"), (Decimal(100_000), "L"), (Decimal(1_000), "K")):
        if rupees >= threshold:
            value = (rupees / threshold).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
            return f"{sign}₹{value:f}{suffix}"
    return f"{sign}₹{rupees.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}"


def percent_of(part: int, rate_percent) -> int:
    """Return rate_percent of an amount in paise, rounded half up to the nearest paisa."""
    return int((Decimal(part) * Decimal(str(rate_percent)) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_gst(subtotal_paise: int, *, supplier_state: str, customer_state: str | None, rate_percent=18) -> dict:
    """Split GST into CGST + SGST (same state) or IGST (inter-state).

    When the customer's state is unknown, IGST is applied.
    """
    same_state = bool(customer_state) and supplier_state.strip().lower() == customer_state.strip().lower()
    if same_state:
        half_rate = Decimal(str(rate_percent)) / 2
        cgst = percent_of(subtotal_paise, half_rate)
        sgst = percent_of(subtotal_paise, half_rate)
        igst = 0
    else:
        cgst = sgst = 0
        igst = percent_of(subtotal_paise, rate_percent)
    tax = cgst + sgst + igst
    return {
        "subtotal": subtotal_paise,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "tax": tax,
        "total": subtotal_paise + tax,
        "rate_percent": rate_percent,
        "intra_state": same_state,
    }


def safe_ratio(numerator, denominator):
    """Divide, returning None when the denominator is zero or missing."""
    if not denominator:
        return None
    return numerator / denominator
