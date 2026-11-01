from django import template
from django.urls import NoReverseMatch, reverse

from camply import money
from workspace.permissions import has_perm

register = template.Library()


@register.filter
def inr(paise):
    return money.format_inr(paise)


@register.filter
def inr_paise(paise):
    return money.format_inr(paise, decimals=True)


@register.filter
def inr_compact(paise):
    return money.format_inr_compact(paise)


@register.filter
def num(value):
    return money.format_number(value)


@register.filter
def pct(value, digits=1):
    if value is None:
        return "–"
    return f"{value:.{int(digits)}f}%"


@register.filter
def ratio(value, digits=1):
    if value is None:
        return "–"
    return f"{value:.{int(digits)}f}x"


@register.filter
def signed_pct(value):
    if value is None:
        return "–"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


@register.simple_tag(takes_context=True)
def can(context, perm):
    request = context.get("request")
    membership = getattr(request, "membership", None) if request else None
    return has_perm(membership, perm)


@register.simple_tag(takes_context=True)
def nav_active(context, url_name):
    """Return 'is-active' when the current URL belongs to the named nav section."""
    request = context.get("request")
    if not request or not request.resolver_match:
        return ""
    try:
        target = reverse(url_name)
    except NoReverseMatch:
        return ""
    path = request.path
    if target == "/":
        return "is-active" if path == "/" else ""
    return "is-active" if path.startswith(target) else ""


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs):
    """Rebuild the current query string with some parameters replaced."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
