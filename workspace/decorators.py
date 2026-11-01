from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .permissions import has_perm


def require_perm(*perms):
    """Require a signed-in member of an organization holding every listed permission."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            membership = getattr(request, "membership", None)
            if membership is None or not all(has_perm(membership, p) for p in perms):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
