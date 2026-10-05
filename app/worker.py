import logging, time, httpx
from sqlalchemy import select, update
from .config import settings
from .db import SessionLocal, Case, Job, Payment, Heartbeat, now
from .security import decrypt, audit
from .services import maintenance, released
from . import providers


def tick():
    with SessionLocal() as db:
        heartbeat = db.get(Heartbeat, "worker")
        if heartbeat:
            heartbeat.at = now()
        else:
            db.add(Heartbeat(id="worker", at=now()))
        db.execute(
            update(Job)
            .where(Job.state == "sending", Job.lease_at < now() - 120)
            .values(
                state="uncertain", reason="Interrupted acknowledgement: review manually"
            )
        )
        maintenance(db)
        ids = list(
            db.scalars(
                select(Job.id)
                .join(Case, Case.id == Job.case_id)
                .where(
                    Job.state == "pending",
                    Job.due_at <= now(),
                    Case.expires_at > now(),
                    Case.status == "eligible",
                    Case.approved_version == Case.version,
                    Case.approved_version > 0,
                )
                .order_by(Job.due_at)
                .limit(100)
            ).all()
        )
    for id in ids:
        process_job(id)
    cancel_pending_payments()


def cancel_pending_payments():
    if settings.payment_mode != "razorpay":
        return
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(Payment.id)
                .where(
                    Payment.cancel_requested == 1,
                    Payment.provider_id.is_not(None),
                    Payment.next_cancel_at <= now(),
                )
                .limit(20)
            ).all()
        )
    for id in ids:
        with SessionLocal() as db:
            payment = db.get(Payment, id)
            provider_id = payment.provider_id
            payment.next_cancel_at = now() + 300
            db.commit()
        try:
            entity = providers.cancel_payment_link(provider_id)
        except Exception:
            continue
        with SessionLocal() as db:
            payment = db.scalar(
                select(Payment).where(Payment.id == id).with_for_update()
            )
            if (
                entity.get("id") != payment.provider_id
                or entity.get("reference_id") != payment.id
            ):
                continue
            if entity.get("status") in {"cancelled", "expired"}:
                payment.status = "cancelled"
                payment.cancel_requested = 0
            elif entity.get("status") == "paid":
                providers.apply_paid_link(db, entity)
                payment.cancel_requested = 2
            audit(db, "worker", "payment_cancellation_checked")
            db.commit()


def process_job(id):
    with SessionLocal() as db:
        job = db.get(Job, id)
        if not job or job.state != "pending":
            return
        case = db.get(Case, job.case_id)
        if not case or not released(case):
            return
        if job.day == 0 and job.version != case.version:
            job.state = "cancelled"
            job.reason = "Superseded plan"
            db.commit()
            return
        data = decrypt(case.data_cipher)["input"]
        if (
            settings.notification_mode != "whatsapp"
            or not data["whatsapp_opt_in"]
            or not case.contact_verified
        ):
            job.state = "manual"
            job.reason = "Messaging disabled, not opted in or unverified"
            db.commit()
            return
        claimed = db.execute(
            update(Job)
            .where(Job.id == id, Job.state == "pending")
            .values(state="sending", lease_at=now(), attempts=Job.attempts + 1)
        ).rowcount
        db.commit()
        if not claimed:
            return
        phone = data["phone"]
    provider_id = None
    retry = False
    try:
        provider_id = providers.whatsapp_send(phone)
        state, reason = "accepted", ""
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        retry = code == 429
        state = "pending" if retry else ("uncertain" if code >= 500 else "failed")
        reason = f"Provider HTTP {code}; review required"
    except Exception:
        state, reason = "uncertain", "Acknowledgement unavailable; no blind resend"
    with SessionLocal() as db:
        job = db.get(Job, id)
        if not job:
            return
        job.state, job.reason, job.provider_id = state, reason, provider_id
        if retry:
            if job.attempts >= 5:
                job.state = "failed"
                job.reason = "Retry limit reached"
            else:
                job.due_at = now() + min(3600, 60 * 2**job.attempts)
        audit(db, "worker", "notification_" + job.state, job.case_id)
        db.commit()


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            tick()
        except Exception as exc:
            logging.error("Worker cycle failed: %s", type(exc).__name__)
        time.sleep(15)


if __name__ == "__main__":
    main()
