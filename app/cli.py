import argparse, getpass, json, os
from pathlib import Path
from sqlalchemy import select, delete
from .db import Base, engine, init_db, SessionLocal, User, LoginSession, Payment
from .security import password_hash, cipher, audit
from .services import maintenance
from . import providers


def new_password():
    value = getpass.getpass("Password (12+ characters): ")
    if not 12 <= len(value) <= 128 or value != getpass.getpass("Repeat: "):
        raise SystemExit("Passwords must match and contain 12–128 characters.")
    return password_hash(value)


def backup(path):
    data = {"format": 1, "tables": {}}
    with engine.connect() as conn, conn.begin():
        if engine.dialect.name == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        for table in Base.metadata.sorted_tables:
            if table.name not in {"sessions", "rate_limits", "heartbeat"}:
                data["tables"][table.name] = [
                    dict(row) for row in conn.execute(select(table)).mappings()
                ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as file:
        os.chmod(path, 0o600)
        file.write(cipher.encrypt(json.dumps(data).encode()))


def restore(path):
    data = json.loads(cipher.decrypt(Path(path).read_bytes()))
    if data.get("format") != 1:
        raise SystemExit("Unsupported backup format")
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if (
                table.name != "schema_version"
                and conn.execute(select(table).limit(1)).first()
            ):
                raise SystemExit("Restore requires an empty database.")
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
        for table in Base.metadata.sorted_tables:
            if data["tables"].get(table.name):
                conn.execute(table.insert(), data["tables"][table.name])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["init-db", "retention", "list-open-payments"]:
        sub.add_parser(name)
    create = sub.add_parser("create-user")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--role", choices=["admin", "practitioner"], default="practitioner"
    )
    create.add_argument("--credential", default="")
    create.add_argument("--verified-credential", action="store_true")
    for name in ["disable-user", "reset-password"]:
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
    for name in ["backup", "restore"]:
        p = sub.add_parser(name)
        p.add_argument("--file", required=True)
    p = sub.add_parser("recover-payment-link")
    p.add_argument("--attempt-id", required=True)
    p.add_argument("--provider-id", required=True)
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "backup":
        backup(args.file)
    elif args.command == "restore":
        restore(args.file)
    else:
        with SessionLocal() as db:
            if args.command == "create-user":
                if (
                    "@" not in args.email
                    or len(args.email) > 254
                    or not 1 <= len(args.name) <= 100
                    or len(args.credential) > 250
                ):
                    raise SystemExit("Invalid account details")
                if args.credential and not args.verified_credential:
                    raise SystemExit(
                        "Independently verify qualification, then pass --verified-credential"
                    )
                if db.scalar(select(User).where(User.email == args.email.lower())):
                    raise SystemExit("User already exists")
                db.add(
                    User(
                        email=args.email.lower(),
                        name=args.name,
                        role=args.role,
                        credential=args.credential,
                        password_hash=new_password(),
                    )
                )
                audit(db, "operator", "user_created")
            elif args.command in {"disable-user", "reset-password"}:
                user = db.scalar(select(User).where(User.email == args.email.lower()))
                if not user:
                    raise SystemExit("User not found")
                if args.command == "disable-user":
                    user.active = 0
                else:
                    user.password_hash = new_password()
                db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
                audit(db, "operator", args.command.replace("-", "_"))
            elif args.command == "retention":
                maintenance(db)
            elif args.command == "list-open-payments":
                for payment in db.scalars(
                    select(Payment).where(
                        (Payment.cancel_requested > 0) | (Payment.status == "uncertain")
                    )
                ).all():
                    print(
                        json.dumps(
                            {
                                "attempt_id": payment.id,
                                "provider_id": payment.provider_id,
                                "amount": payment.amount,
                                "status": payment.status,
                                "cancel_requested": payment.cancel_requested,
                            }
                        )
                    )
            elif args.command == "recover-payment-link":
                payment = db.get(Payment, args.attempt_id)
                if (
                    not payment
                    or payment.status not in {"creating", "uncertain"}
                    or not args.provider_id.startswith("plink_")
                ):
                    raise SystemExit("Attempt not recoverable")
                entity = providers.fetch_payment_link(args.provider_id)
                if (
                    entity.get("reference_id") != payment.id
                    or entity.get("amount") != payment.amount
                    or entity.get("currency") != "INR"
                ):
                    raise SystemExit("Provider link mismatch")
                payment.provider_id = entity["id"]
                payment.provider_url = entity["short_url"]
                payment.status = "created"
                if entity.get("status") == "paid":
                    providers.apply_paid_link(db, entity)
                audit(db, "operator", "payment_link_recovered", payment.case_id or "")
            db.commit()
    print("Completed.")


if __name__ == "__main__":
    main()
