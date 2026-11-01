from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        patch_allauth_user_ids()


def patch_allauth_user_ids():
    """Make allauth encode MongoDB ObjectId user IDs in links (password reset, passkeys).

    allauth treats any IntegerField subclass as an integer primary key, and MongoDB's
    ObjectIdAutoField subclasses AutoField, so `int(user.pk)` crashes. Encode ObjectIds as
    their 24-character hex string instead. Modules that imported the helpers by name get
    the patched versions too.
    """
    from allauth.account import forms as account_forms
    from allauth.account import utils as account_utils
    from bson import ObjectId
    from django.contrib.auth import get_user_model
    from django_mongodb_backend.fields import ObjectIdAutoField

    original_to_str = account_utils.user_pk_to_url_str
    original_to_pk = account_utils.url_str_to_user_pk

    def uses_object_id():
        return isinstance(get_user_model()._meta.pk, ObjectIdAutoField)

    def user_pk_to_url_str(user):
        if uses_object_id():
            return str(user.pk)
        return original_to_str(user)

    def url_str_to_user_pk(pk_str):
        if uses_object_id():
            # An invalid ID raises ValueError, which allauth treats as a bad link.
            if not ObjectId.is_valid(pk_str):
                raise ValueError("Invalid user id in link.")
            return ObjectId(pk_str)
        return original_to_pk(pk_str)

    account_utils.user_pk_to_url_str = user_pk_to_url_str
    account_utils.url_str_to_user_pk = url_str_to_user_pk
    account_forms.url_str_to_user_pk = url_str_to_user_pk
    try:
        from allauth.mfa import adapter as mfa_adapter

        mfa_adapter.user_pk_to_url_str = user_pk_to_url_str
    except ImportError:
        pass
