"""Django settings for Camply.

Configuration comes from environment variables (see .env.example).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is off.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # Django contrib apps re-configured to use MongoDB ObjectId primary keys.
    "camply.apps.MongoAdminConfig",
    "camply.apps.MongoAuthConfig",
    "camply.apps.MongoContentTypesConfig",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Authentication: email + password, Google, Microsoft, two-step verification.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "allauth.mfa",
    # Camply
    "accounts",
    "workspace",
    "ads",
    "billing",
    "audit",
    "dashboard",
    "console",
    "leads",
    "creatives",
    "automation",
]

MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
    "account": "mongo_migrations.account",
    "socialaccount": "mongo_migrations.socialaccount",
    "mfa": "mongo_migrations.mfa",
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "workspace.middleware.CurrentMembershipMiddleware",
]

ROOT_URLCONF = "camply.urls"
# Friendly handling of stale forms (e.g. a sign-in page left open in another tab).
CSRF_FAILURE_VIEW = "dashboard.views.csrf_failure"
WSGI_APPLICATION = "camply.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "workspace.context_processors.workspace",
                "automation.context_processors.notifications",
            ],
            "builtins": ["camply.templatetags.camply_tags"],
        },
    },
]

# --- Database: MongoDB -------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": env("MONGODB_URI", "mongodb://localhost:27017"),
        "NAME": env("MONGODB_DB", "camply"),
    }
}
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
ALLAUTH_DEFAULT_AUTO_FIELD = DEFAULT_AUTO_FIELD

# --- Auth ----------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "dashboard:home"
ACCOUNT_LOGOUT_REDIRECT_URL = "account_login"

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", "mandatory")
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,5/5m/key"}
ACCOUNT_EMAIL_SUBJECT_PREFIX = "Camply: "

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Camply"

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {}
if env("GOOGLE_CLIENT_ID"):
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": env("GOOGLE_CLIENT_ID"), "secret": env("GOOGLE_CLIENT_SECRET", "")}],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
if env("MICROSOFT_CLIENT_ID"):
    SOCIALACCOUNT_PROVIDERS["microsoft"] = {
        "APPS": [
            {
                "client_id": env("MICROSOFT_CLIENT_ID"),
                "secret": env("MICROSOFT_CLIENT_SECRET", ""),
                "settings": {"tenant": env("MICROSOFT_TENANT", "common")},
            }
        ],
    }

# --- Locale: India -------------------------------------------------------------
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static files ----------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# --- Email (Resend in production, console in development) -----------------------
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Camply <no-reply@camply.app>")
RESEND_API_KEY = env("RESEND_API_KEY")
EMAIL_BACKEND = (
    "camply.email.ResendEmailBackend" if RESEND_API_KEY else "django.core.mail.backends.console.EmailBackend"
)

# --- Background jobs: Celery + Redis ------------------------------------------
REDIS_URL = env("REDIS_URL")
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = TIME_ZONE
# Without Redis (local development) tasks run inline instead of on a worker.
CELERY_TASK_ALWAYS_EAGER = not REDIS_URL
CELERY_BEAT_SCHEDULE = {
    "sync-all-ad-accounts": {"task": "ads.tasks.sync_all_accounts", "schedule": 60 * 60},
    "evaluate-automation-rules": {"task": "automation.tasks.evaluate_all_rules", "schedule": 60 * 60},
}

# --- Integrations ----------------------------------------------------------------
# Fernet key used to encrypt ad platform tokens at rest.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")
# When true, ad accounts without a live connection use the sandbox adapter (demo data).
CAMPLY_SANDBOX_ADAPTERS = env_bool("CAMPLY_SANDBOX_ADAPTERS", DEBUG)
META_GRAPH_API_VERSION = env("META_GRAPH_API_VERSION", "v23.0")
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
S3_BUCKET = env("S3_BUCKET")
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")

# Creative uploads: an S3-compatible bucket when configured (needed on hosts with temporary
# disks, like Render), otherwise the local media folder. Files are always served through
# Camply's own permission-checked view, never by public URL.
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
CREATIVE_MAX_UPLOAD_MB = int(env("CREATIVE_MAX_UPLOAD_MB", "50"))
if S3_BUCKET:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": S3_BUCKET,
            "endpoint_url": S3_ENDPOINT_URL or None,
            "access_key": env("S3_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_ACCESS_KEY"),
            "region_name": env("S3_REGION") or None,
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }

# Billing defaults
GST_RATE_PERCENT = 18
CAMPLY_SUPPLIER_STATE = env("CAMPLY_SUPPLIER_STATE", "Kerala")

# --- Security (production) -------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
