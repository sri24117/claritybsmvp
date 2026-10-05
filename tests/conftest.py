import os, tempfile, dataclasses
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url

temporary = tempfile.TemporaryDirectory(prefix="claritybs-test-")
url = os.getenv("TEST_POSTGRES_URL", "sqlite:///" + temporary.name + "/test.db")
if url.startswith("postgresql") and not str(make_url(url).database).endswith("_test"):
    raise RuntimeError("PostgreSQL tests require an isolated database ending in _test")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": url,
        "DATA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "APP_ORIGIN": "http://testserver",
        "PUBLIC_INTAKE_ENABLED": "true",
        "BUSINESS_NAME": "Synthetic Test Practice",
        "SUPPORT_EMAIL": "support@example.test",
        "PAYMENT_MODE": "disabled",
        "NOTIFICATION_MODE": "manual",
    }
)
from fastapi.testclient import TestClient
from app.db import Base, engine, init_db, SessionLocal, User
from app.main import app
from app.security import password_hash
from app.config import settings


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as db:
        for email, role, credential in [
            ("admin@example.test", "admin", "Synthetic credential — testing only"),
            ("dt@example.test", "practitioner", "Synthetic credential — testing only"),
            (
                "other@example.test",
                "practitioner",
                "Synthetic credential — testing only",
            ),
            ("ops@example.test", "admin", ""),
        ]:
            db.add(
                User(
                    email=email,
                    name=email.split("@")[0],
                    role=role,
                    credential=credential,
                    password_hash=password_hash("Test-password-2026"),
                )
            )
        db.commit()


@pytest.fixture
def client():
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client


@pytest.fixture
def admin(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.test", "password": "Test-password-2026"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client


def configure(monkeypatch, **values):
    new = dataclasses.replace(settings, **values)
    import app.main, app.services, app.providers, app.worker

    for module in [app.main, app.services, app.providers, app.worker]:
        monkeypatch.setattr(module, "settings", new)
    return new


@pytest.fixture
def payment_settings(monkeypatch):
    return configure(
        monkeypatch,
        payment_mode="razorpay",
        pay_key="rzp_test_synthetic",
        pay_secret="synthetic-secret",
        pay_webhook="synthetic-webhook",
    )


@pytest.fixture
def whatsapp_settings(monkeypatch):
    return configure(
        monkeypatch,
        notification_mode="whatsapp",
        wa_token="synthetic-token",
        wa_phone="12345",
        wa_secret="synthetic-app-secret",
        wa_verify="synthetic-verify",
        wa_version="vSynthetic",
        wa_template="synthetic_template",
    )
