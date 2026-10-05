import hashlib, hmac
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from sqlalchemy import select, update
from .config import settings
from .db import Payment, Case, Job, now
from .security import audit
from .services import activate


def verify_signature(body, signature, secret, prefix=""):
    if not secret:
        raise HTTPException(503, "Provider not configured.")
    expected = prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid signature.")


def provider_get(resource):
    with httpx.Client(
        timeout=20, auth=(settings.pay_key, settings.pay_secret)
    ) as client:
        response = client.get("https://api.razorpay.com/v1/" + resource)
        response.raise_for_status()
        return response.json()


def fetch_payment_link(id):
    return provider_get("payment_links/" + id)


def fetch_payment(id):
    return provider_get("payments/" + id)


def payment_link(payment):
    body = {
        "amount": payment.amount,
        "currency": "INR",
        "accept_partial": False,
        "reference_id": payment.id,
        "expire_by": now() + 86400,
        "description": "ClarityBS nutrition support",
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "callback_url": settings.origin + "/portal",
        "callback_method": "get",
    }
    with httpx.Client(
        timeout=20, auth=(settings.pay_key, settings.pay_secret)
    ) as client:
        response = client.post("https://api.razorpay.com/v1/payment_links", json=body)
        response.raise_for_status()
        data = response.json()
    parsed = urlparse(data.get("short_url", ""))
    if (
        not data.get("id", "").startswith("plink_")
        or parsed.scheme != "https"
        or parsed.hostname != "rzp.io"
        or data.get("amount") != payment.amount
        or data.get("currency") != "INR"
        or data.get("reference_id") != payment.id
    ):
        raise ValueError("Payment response mismatch")
    return data


def cancel_payment_link(id):
    with httpx.Client(
        timeout=20, auth=(settings.pay_key, settings.pay_secret)
    ) as client:
        response = client.post(
            "https://api.razorpay.com/v1/payment_links/" + id + "/cancel"
        )
        if response.status_code == 400:
            return fetch_payment_link(id)
        response.raise_for_status()
        return response.json()


def apply_paid_link(db, entity, payment_id=""):
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == entity.get("reference_id", ""))
        .with_for_update()
    )
    if not payment or (payment.provider_id and payment.provider_id != entity.get("id")):
        raise HTTPException(400, "Unknown payment link.")
    if (
        not str(entity.get("id", "")).startswith("plink_")
        or entity.get("status") != "paid"
        or entity.get("amount") != payment.amount
        or entity.get("amount_paid") != payment.amount
        or entity.get("currency") != "INR"
    ):
        raise HTTPException(400, "Payment details do not match.")
    if payment_id:
        if payment.payment_id and payment.payment_id != payment_id:
            raise HTTPException(400, "Payment identifier mismatch.")
        payment.payment_id = payment_id
    if payment.status in {"paid", "refunded"}:
        return
    payment.provider_id = entity["id"]
    payment.status = "paid"
    case = (
        db.scalar(select(Case).where(Case.id == payment.case_id).with_for_update())
        if payment.case_id
        else None
    )
    if case:
        case.paid = 1
        activate(db, case)
        audit(db, "razorpay", "payment_confirmed", case.id)


def apply_refund(db, entity):
    payment = db.scalar(
        select(Payment)
        .where(Payment.payment_id == entity.get("id", ""), Payment.payment_id != "")
        .with_for_update()
    )
    if not payment:
        raise HTTPException(400, "Unknown payment for refund.")
    amount = entity.get("amount_refunded")
    if (
        entity.get("amount") != payment.amount
        or entity.get("currency") != "INR"
        or not isinstance(amount, int)
        or not 0 <= amount <= payment.amount
    ):
        raise HTTPException(400, "Refund details do not match.")
    payment.refunded_amount = max(payment.refunded_amount, amount)
    if payment.refunded_amount == payment.amount:
        payment.status = "refunded"
        case = (
            db.scalar(select(Case).where(Case.id == payment.case_id).with_for_update())
            if payment.case_id
            else None
        )
        if case:
            case.paid = 0
            case.status = "cancelled"
            case.approved_version = 0
            db.execute(
                update(Job)
                .where(Job.case_id == case.id, Job.state.in_(["pending", "manual"]))
                .values(state="cancelled", reason="Fully refunded")
            )
            audit(db, "razorpay", "full_refund_confirmed", case.id)


def whatsapp_send(phone):
    body = {
        "messaging_product": "whatsapp",
        "to": phone.removeprefix("+"),
        "type": "template",
        "template": {
            "name": settings.wa_template,
            "language": {"code": settings.wa_language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": settings.origin + "/portal"}
                    ],
                }
            ],
        },
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            f"https://graph.facebook.com/{settings.wa_version}/{settings.wa_phone}/messages",
            headers={"Authorization": "Bearer " + settings.wa_token},
            json=body,
        )
        response.raise_for_status()
        data = response.json()
    id = data["messages"][0]["id"]
    if not isinstance(id, str) or not id:
        raise ValueError("Invalid message response")
    return id
