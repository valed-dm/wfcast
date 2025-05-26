from django.conf import settings
from django.http import HttpRequest

from wfcast.types import AllAuthSettings


def allauth_settings(request: HttpRequest) -> AllAuthSettings:
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
    }
