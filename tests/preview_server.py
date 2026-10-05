"""Disposable browser-test fixture. Never used by the production server."""

import os, sys, tempfile
from pathlib import Path
from cryptography.fernet import Fernet

directory = tempfile.TemporaryDirectory(prefix="claritybs-browser-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.update(
    {
        "ENVIRONMENT": "development",
        "DATABASE_URL": "sqlite:///" + directory.name + "/preview.db",
        "DATA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "APP_ORIGIN": "http://localhost:8000",
        "PUBLIC_INTAKE_ENABLED": "true",
        "BUSINESS_NAME": "Synthetic Browser Test",
        "SUPPORT_EMAIL": "preview@example.test",
        "PAYMENT_MODE": "disabled",
        "NOTIFICATION_MODE": "manual",
    }
)
from app.db import init_db, SessionLocal, User
from app.security import password_hash

init_db()
with SessionLocal() as db:
    db.add(
        User(
            email="preview@example.test",
            name="Preview Practitioner",
            role="admin",
            credential="Synthetic qualification — testing only",
            password_hash=password_hash("Synthetic-preview-2026"),
        )
    )
    db.commit()
import threading, uvicorn
from app.worker import main

threading.Thread(target=main, daemon=True).start()
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False)
