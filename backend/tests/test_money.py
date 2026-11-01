import pytest

from camply.money import calculate_gst, format_inr, format_inr_compact, format_number, group_indian, rupees_to_paise


@pytest.mark.parametrize("value,expected", [
    (0, "0"), (999, "999"), (1000, "1,000"), (487320, "4,87,320"), (1248920, "12,48,920"),
    (12345678, "1,23,45,678"), (-487320, "-4,87,320"),
])
def test_indian_grouping(value, expected):
    assert group_indian(value) == expected


def test_format_inr_rounds_to_rupees():
    assert format_inr(48732000) == "₹4,87,320"
    assert format_inr(17150) == "₹172"  # ₹171.50 rounds half up
    assert format_inr(48732050, decimals=True) == "₹4,87,320.50"
    assert format_inr(-150000) == "-₹1,500"
    assert format_inr(None) == "–"


def test_compact():
    assert format_inr_compact(48732000) == "₹4.87L"
    assert format_inr_compact(4520000) == "₹45.2K"
    assert format_inr_compact(1_20_00_000_00) == "₹1.2Cr"
    assert format_inr_compact(95000) == "₹950"


def test_number_and_paise():
    assert format_number(1248920) == "12,48,920"
    assert rupees_to_paise("25000.505") == 2500051
    assert rupees_to_paise(171) == 17100


def test_gst_same_state_splits_cgst_sgst():
    gst = calculate_gst(2500000, supplier_state="Kerala", customer_state="kerala")
    assert gst["intra_state"] is True
    assert gst["cgst"] == gst["sgst"] == 225000
    assert gst["igst"] == 0
    assert gst["total"] == 2950000


def test_gst_inter_state_uses_igst():
    gst = calculate_gst(2100000, supplier_state="Kerala", customer_state="Tamil Nadu")
    assert gst["igst"] == 378000
    assert gst["cgst"] == gst["sgst"] == 0
    assert gst["total"] == 2478000


def test_gst_unknown_state_defaults_to_igst():
    assert calculate_gst(10001, supplier_state="Kerala", customer_state="")["igst"] == 1800
