from typing import TypedDict


class AnymailConfig(TypedDict, total=False):
    MAILGUN_API_KEY: str
    MAILGUN_SENDER_DOMAIN: str
    # ... other expected keys


class AllAuthSettings(TypedDict):
    ACCOUNT_ALLOW_REGISTRATION: bool
