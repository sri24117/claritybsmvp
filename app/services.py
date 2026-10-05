import secrets
from fastapi import HTTPException
from sqlalchemy import select, delete
from .config import settings
from .db import (
    Case,
    User,
    Rate,
    Job,
    LoginSession,
    WebhookEvent,
    DeletedIntake,
    Audit,
    now,
)
from .security import encrypt, decrypt, digest, private_digest, audit

PRODUCTS = {
    "report": {"name": "Sugar Report Clarity", "amount": 0, "days": []},
    "routine14": {"name": "14-Day Food Routine", "amount": 29900, "days": [3, 7, 14]},
    "support30": {
        "name": "30-Day Dietitian Support",
        "amount": 99900,
        "days": [3, 7, 14, 21, 30],
    },
}


def rate_limit(db, bucket, identity, maximum, window=3600):
    key = bucket + ":" + private_digest(identity) + ":" + str(now() // window)
    row = db.scalar(select(Rate).where(Rate.id == key).with_for_update())
    if row:
        row.count += 1
    else:
        row = Rate(id=key, count=1, expires=now() + window * 2)
        db.add(row)
    db.commit()
    if row.count > maximum:
        raise HTTPException(429, "Too many requests. Try again later.")


def create_intake(db, payload, lane):
    if not settings.intake_enabled or not db.scalar(
        select(User).where(User.active == 1, User.credential != "")
    ):
        raise HTTPException(503, "New submissions are paused. Please check back soon.")
    values = payload.model_dump(mode="json")
    key = str(payload.intake_key)
    if db.get(DeletedIntake, key):
        raise HTTPException(
            410, "This submission was deleted. Start a new intake to continue."
        )
    case = db.scalar(select(Case).where(Case.intake_key == key))
    if case:
        if decrypt(case.data_cipher)["original_input"] != values:
            raise HTTPException(409, "Submission key already used.")
        token = decrypt(case.token_cipher)["token"]
    else:
        token = secrets.token_urlsafe(48)
        case = Case(
            intake_key=key,
            token_hash=digest(token),
            token_cipher=encrypt({"token": token}),
            phone_hash=private_digest(payload.phone),
            lane=lane,
            product="report" if lane == "report" else payload.plan,
            data_cipher=encrypt(
                {
                    "original_input": values,
                    "input": values.copy(),
                    "consent_at": now(),
                    "whatsapp_opt_in_at": now() if payload.whatsapp_opt_in else None,
                }
            ),
            expires_at=now() + settings.retention * 86400,
        )
        db.add(case)
        db.flush()
        audit(db, "patient", "intake_created", case.id)
        db.commit()
    urgent = (
        "Seek urgent medical help for severe or worsening symptoms. This service is not monitored for emergencies. "
        if payload.health_screening == "urgent"
        else ""
    )
    return {
        "case_id": case.id,
        "status": case.status,
        "review_required": True,
        "portal_url": "/portal#" + token,
        "message": urgent
        + "Your intake is saved for practitioner review. Save your private access link. You will not be charged before review.",
    }


def approved(case):
    return bool(
        case.version and case.approved_version == case.version and case.signature_cipher
    )


def released(case):
    return (
        case.status == "eligible"
        and approved(case)
        and (case.product == "report" or bool(case.paid))
    )


def activate(db, case):
    if not released(case):
        return
    if not case.activated_at:
        case.activated_at = now()
        case.expires_at = max(case.expires_at, now() + settings.retention * 86400)
    tasks = [("plan_available", 0, now())] + [
        ("checkin_due", day, case.activated_at + day * 86400)
        for day in PRODUCTS[case.product]["days"]
    ]
    for kind, day, due in tasks:
        key = f"{case.id}:{kind}:{case.version if day == 0 else day}"
        job = db.scalar(select(Job).where(Job.dedup_key == key))
        if not job:
            db.add(
                Job(
                    case_id=case.id,
                    dedup_key=key,
                    kind=kind,
                    day=day,
                    version=case.version,
                    due_at=due,
                )
            )
        elif day and job.state == "pending":
            job.version = case.version


def patient_view(case):
    data = decrypt(case.data_cipher)["input"]
    available = released(case)
    return {
        "case_id": case.id,
        "name": data["name"],
        "status": case.status,
        "product": PRODUCTS[case.product]["name"],
        "amount": PRODUCTS[case.product]["amount"],
        "paid": bool(case.paid),
        "contact_verified": bool(case.contact_verified),
        "can_pay": bool(
            case.status == "eligible"
            and approved(case)
            and case.contact_verified
            and case.product != "report"
            and not case.paid
            and settings.payment_mode == "razorpay"
        ),
        "payment_enabled": settings.payment_mode == "razorpay",
        "review_note": decrypt(case.review_cipher).get("note", ""),
        "plan": decrypt(case.plan_cipher).get("text", "") if available else "",
        "plan_version": case.version if available else None,
        "signature": decrypt(case.signature_cipher) if available else {},
        "checkin_days": PRODUCTS[case.product]["days"] if available else [],
        "activated_at": case.activated_at,
        "whatsapp_opt_in": data["whatsapp_opt_in"],
        "expires_at": case.expires_at,
    }


def staff_view(db, case):
    from .db import Checkin, Payment

    data = decrypt(case.data_cipher)
    checks = db.scalars(
        select(Checkin).where(Checkin.case_id == case.id).order_by(Checkin.day)
    ).all()
    jobs = db.scalars(
        select(Job).where(Job.case_id == case.id).order_by(Job.due_at)
    ).all()
    payment = db.scalar(select(Payment).where(Payment.case_id == case.id))
    return {
        "id": case.id,
        "created_at": case.created_at,
        "lane": case.lane,
        "product": case.product,
        "status": case.status,
        "assigned_to": case.assigned_to,
        "intake": data["input"],
        "consent_at": data["consent_at"],
        "contact_verified": bool(case.contact_verified),
        "contact_verification": data.get("contact_verification", {}),
        "review": decrypt(case.review_cipher),
        "plan": decrypt(case.plan_cipher).get("text", ""),
        "version": case.version,
        "approved_version": case.approved_version,
        "signature": decrypt(case.signature_cipher),
        "paid": bool(case.paid),
        "payment_status": payment.status if payment else "none",
        "payment_attempt_id": payment.id if payment else None,
        "refunded_amount": payment.refunded_amount if payment else 0,
        "activated_at": case.activated_at,
        "viewed_at": case.viewed_at,
        "checkins": [
            {
                "id": c.id,
                "day": c.day,
                "data": decrypt(c.data_cipher),
                "created_at": c.created_at,
                "reviewed_at": c.reviewed_at,
            }
            for c in checks
        ],
        "jobs": [
            {
                "id": j.id,
                "kind": j.kind,
                "day": j.day,
                "due_at": j.due_at,
                "state": j.state,
                "reason": j.reason,
                "attempts": j.attempts,
            }
            for j in jobs
        ],
    }


def erase_case(db, case, actor):
    from .db import Payment

    payment = db.scalar(select(Payment).where(Payment.case_id == case.id))
    if payment and payment.status not in {"paid", "refunded", "cancelled"}:
        payment.cancel_requested = 1
    if not db.get(DeletedIntake, case.intake_key):
        db.add(
            DeletedIntake(
                id=case.intake_key, expires_at=now() + settings.retention * 86400
            )
        )
    db.delete(case)
    audit(db, actor, "case_erased", case.id)


def maintenance(db):
    for case in db.scalars(select(Case).where(Case.expires_at <= now())).all():
        erase_case(db, case, "retention_worker")
    for model, condition in [
        (LoginSession, LoginSession.expires <= now()),
        (Rate, Rate.expires <= now()),
        (DeletedIntake, DeletedIntake.expires_at < now()),
        (WebhookEvent, WebhookEvent.created_at < now() - 30 * 86400),
        (Audit, Audit.created_at < now() - 365 * 86400),
    ]:
        db.execute(delete(model).where(condition))
    db.commit()
