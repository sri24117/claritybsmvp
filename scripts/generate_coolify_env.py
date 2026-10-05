#!/usr/bin/env python3
"""Print a production-safe environment block for a first Coolify deployment."""

from __future__ import annotations

import argparse
import base64
import secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate environment variables to paste into Coolify."
    )
    parser.add_argument(
        "--support-email",
        required=True,
        help="Monitored support email shown to users.",
    )
    parser.add_argument(
        "--business-name",
        default="Clarity Blood Sugar",
        help="Public business name (default: Clarity Blood Sugar).",
    )
    parser.add_argument(
        "--domain",
        default="claritybs.in",
        help="Public domain without a scheme (default: claritybs.in).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_password = secrets.token_hex(32)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

    values = {
        "ENVIRONMENT": "production",
        "DOMAIN": args.domain,
        "APP_ORIGIN": f"https://{args.domain}",
        "POSTGRES_PASSWORD": database_password,
        "DATABASE_URL": (
            "postgresql+psycopg://clarity:"
            f"{database_password}@db:5432/claritybs"
        ),
        "DATA_ENCRYPTION_KEY": encryption_key,
        "PUBLIC_INTAKE_ENABLED": "false",
        "BUSINESS_NAME": args.business_name,
        "SUPPORT_EMAIL": args.support_email,
        "RETENTION_DAYS": "90",
        "PAYMENT_MODE": "disabled",
        "NOTIFICATION_MODE": "manual",
    }

    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()

