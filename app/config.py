import os
from dataclasses import dataclass
from urllib.parse import urlparse
from cryptography.fernet import Fernet


def flag(name):
    return os.getenv(name, "false").lower() == "true"


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/claritybs.db")
    key: str = os.getenv("DATA_ENCRYPTION_KEY", "")
    origin: str = os.getenv("APP_ORIGIN", "http://localhost:8000").rstrip("/")
    intake_enabled: bool = flag("PUBLIC_INTAKE_ENABLED")
    business: str = os.getenv("BUSINESS_NAME", "")
    support: str = os.getenv("SUPPORT_EMAIL", "")
    retention: int = int(os.getenv("RETENTION_DAYS", "90"))
    payment_mode: str = os.getenv("PAYMENT_MODE", "disabled")
    pay_key: str = os.getenv("RAZORPAY_KEY_ID", "")
    pay_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    pay_webhook: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    notification_mode: str = os.getenv("NOTIFICATION_MODE", "manual")
    wa_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    wa_phone: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_secret: str = os.getenv("META_APP_SECRET", "")
    wa_verify: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    wa_version: str = os.getenv("WHATSAPP_API_VERSION", "")
    wa_template: str = os.getenv("WHATSAPP_TEMPLATE_NAME", "")
    wa_language: str = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    consent_version: str = "2026-09-30-v1"

    @property
    def production(self):
        return self.environment == "production"

    def validate(self):
        Fernet(self.key.encode())
        url = urlparse(self.origin)
        if (
            self.environment not in {"development", "test", "production"}
            or not url.hostname
            or url.path
            or url.query
        ):
            raise RuntimeError("Invalid environment or APP_ORIGIN")
        if self.production and (
            url.scheme != "https" or not self.database_url.startswith("postgresql")
        ):
            raise RuntimeError("Production requires HTTPS and PostgreSQL")
        if not 1 <= self.retention <= 365:
            raise RuntimeError("Retention must be 1–365 days")
        if self.intake_enabled and (not self.business or "@" not in self.support):
            raise RuntimeError(
                "Enabled intake requires business name and support email"
            )
        if self.payment_mode not in {
            "disabled",
            "razorpay",
        } or self.notification_mode not in {"manual", "whatsapp"}:
            raise RuntimeError("Invalid provider mode")
        if self.payment_mode == "razorpay" and not all(
            [self.pay_key, self.pay_secret, self.pay_webhook]
        ):
            raise RuntimeError("Incomplete Razorpay configuration")
        if self.notification_mode == "whatsapp" and not all(
            [
                self.wa_token,
                self.wa_phone,
                self.wa_secret,
                self.wa_verify,
                self.wa_version,
                self.wa_template,
            ]
        ):
            raise RuntimeError("Incomplete WhatsApp configuration")


settings = Settings()
settings.validate()
