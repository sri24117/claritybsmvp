import argparse, base64, os, secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--local", action="store_true")
args = parser.parse_args()
if Path(".env").exists():
    raise SystemExit(".env already exists and was not overwritten.")
text = Path(".env.example").read_text()
password = secrets.token_hex(32)
text = text.replace("REPLACE_DB_PASSWORD", password).replace(
    "REPLACE_WITH_GENERATED_FERNET_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)
if args.local:
    text = (
        text.replace("ENVIRONMENT=production", "ENVIRONMENT=development")
        .replace("APP_ORIGIN=https://claritybs.in", "APP_ORIGIN=http://localhost:8000")
        .replace(
            "DATABASE_URL=postgresql+psycopg://clarity:"
            + password
            + "@db:5432/claritybs",
            "DATABASE_URL=sqlite:///./data/claritybs.db",
        )
    )
with Path(".env").open("x") as file:
    os.chmod(".env", 0o600)
    file.write(text)
print(
    "Created .env. Store the encryption key securely outside the server. Intake remains paused."
)
