import uuid, json, hmac, hashlib, dataclasses
import httpx, pytest
from sqlalchemy import select
from app.db import (
    SessionLocal,
    Case,
    Job,
    Payment,
    Checkin,
    User,
    now,
    Base,
    engine,
    init_db,
)
from app.security import decrypt
from app.worker import tick
from app.cli import backup, restore
from app.services import activate
from app.config import settings
from app import providers


def payload(lane="report", **changes):
    data = {
        "intake_key": str(uuid.uuid4()),
        "name": "Synthetic Person",
        "phone": "+919999999999",
        "age": 35,
        "health_screening": "clear",
        "consent": True,
        "consent_version": "2026-09-30-v1",
        "whatsapp_opt_in": False,
    }
    data.update(
        {"hba1c": 6.4, "sugar_unit": "mg/dL"}
        if lane == "report"
        else {
            "plan": "routine14",
            "goal": "Healthier everyday eating",
            "food_preference": "Vegetarian",
            "allergies": "None",
            "daily_routine": "Synthetic routine",
        }
    )
    return {**data, **changes}


def create(client, lane="report", **changes):
    response = client.post("/api/intake/" + lane, json=payload(lane, **changes))
    assert response.status_code == 200, response.text
    data = response.json()
    return data["case_id"], {
        "Authorization": "Bearer " + data["portal_url"].split("#")[1]
    }


def prepare(client, id):
    base = "/api/staff/cases/" + id
    assert (
        client.post(
            base + "/verify-contact",
            json={"note": "Synthetic inbound contact verified for tests only."},
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/review",
            json={
                "disposition": "eligible",
                "note": "Synthetic suitability review completed. Not real clinical advice.",
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            base + "/plan",
            json={
                "text": "SYNTHETIC REVIEWED CONTENT. This is used only for automated tests, not for patient nutrition advice."
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/approve", json={"version": 1, "confirm_reviewed": True}
        ).status_code
        == 200
    )


def fake_link(payment):
    return {
        "id": "plink_" + payment.id,
        "short_url": "https://rzp.io/synthetic",
        "reference_id": payment.id,
        "amount": payment.amount,
        "currency": "INR",
    }


def event_for(payment, **changes):
    return {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": payment.provider_id,
                    "reference_id": payment.id,
                    "status": "paid",
                    "amount": payment.amount,
                    "amount_paid": payment.amount,
                    "currency": "INR",
                    **changes,
                }
            },
            "payment": {"entity": {"id": "pay_synthetic"}},
        },
    }


def webhook(client, event, secret, id="synthetic-event"):
    body = json.dumps(event).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": id,
        },
    )


def start_payment(admin, monkeypatch):
    monkeypatch.setattr(providers, "payment_link", fake_link)
    id, token = create(admin, "diet")
    prepare(admin, id)
    assert admin.post("/api/checkout", headers=token).status_code == 200
    with SessionLocal() as db:
        event = event_for(db.scalar(select(Payment).where(Payment.case_id == id)))
    return id, token, event


def active(admin, product="routine14"):
    id, token = create(admin, "diet", plan=product)
    prepare(admin, id)
    with SessionLocal() as db:
        case = db.get(Case, id)
        case.paid = 1
        activate(db, case)
        case.activated_at = now() - 31 * 86400
        db.commit()
    return id, token


def test_mock_endpoints_and_invalid_login_blocked(client):
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@example.test", "password": "wrong"}
        ).status_code
        == 401
    )
    assert client.get("/api/staff/cases").status_code == 401
    assert client.get("/api/health").status_code == 401
    assert client.get("/patients").status_code == 404
    assert client.post("/plans/ghost/approve").status_code == 404


def test_csrf_origin_assignment_and_qualification(admin):
    id, _ = create(admin)
    admin.headers.pop("X-CSRF-Token")
    assert (
        admin.post(
            "/api/staff/cases/" + id + "/review",
            json={
                "disposition": "eligible",
                "note": "Synthetic review note, long enough.",
            },
        ).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.test"},
            json={"email": "admin@example.test", "password": "Test-password-2026"},
        ).status_code
        == 403
    )
    login = admin.post(
        "/api/auth/login",
        json={"email": "dt@example.test", "password": "Test-password-2026"},
    ).json()
    admin.headers["X-CSRF-Token"] = login["csrf"]
    assert (
        admin.get("/api/staff/cases").json() == []
        and admin.get("/api/staff/cases/" + id).status_code == 404
    )
    login = admin.post(
        "/api/auth/login",
        json={"email": "ops@example.test", "password": "Test-password-2026"},
    ).json()
    admin.headers["X-CSRF-Token"] = login["csrf"]
    assert (
        admin.post(
            "/api/staff/cases/" + id + "/review",
            json={
                "disposition": "eligible",
                "note": "Synthetic review note, long enough.",
            },
        ).status_code
        == 403
    )


def test_session_flags_logout_and_disabled_user(admin):
    r = admin.post(
        "/api/auth/login",
        json={"email": "admin@example.test", "password": "Test-password-2026"},
    )
    assert (
        "HttpOnly" in r.headers["set-cookie"]
        and "SameSite=strict" in r.headers["set-cookie"]
    )
    admin.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert (
        admin.post("/api/auth/logout").status_code == 200
        and admin.get("/api/auth/me").status_code == 401
    )
    admin.post(
        "/api/auth/login",
        json={"email": "admin@example.test", "password": "Test-password-2026"},
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.test"))
        user.active = 0
        db.commit()
    assert admin.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"age": 16},
        {"age": "35"},
        {"consent": False},
        {"consent": 1},
        {"whatsapp_opt_in": "true"},
        {"consent_version": "old"},
        {"sugar_unit": "mmol/L"},
        {"hba1c": None},
        {"hba1c": 90},
        {"health_screening": ""},
        {"phone": "9999999999"},
        {"review_required": False},
    ],
)
def test_input_validation(client, changes):
    assert client.post("/api/intake/report", json=payload(**changes)).status_code == 422


def test_idempotency_and_messaging_preference_does_not_change_original_input(admin):
    data = payload()
    first = admin.post("/api/intake/report", json=data).json()
    second = admin.post("/api/intake/report", json=data).json()
    assert (
        first["case_id"] == second["case_id"]
        and first["portal_url"] == second["portal_url"]
        and first["review_required"] is True
    )
    token = {"Authorization": "Bearer " + first["portal_url"].split("#")[1]}
    admin.post(
        "/api/portal/notification-preference",
        headers=token,
        json={"whatsapp_opt_in": True},
    )
    assert admin.post("/api/intake/report", json=data).status_code == 200
    data["name"] = "Different person"
    assert admin.post("/api/intake/report", json=data).status_code == 409


def test_urgent_referral_required(admin):
    id, token = create(admin, health_screening="urgent")
    base = "/api/staff/cases/" + id + "/review"
    assert (
        admin.post(
            base,
            json={
                "disposition": "eligible",
                "note": "Synthetic eligibility note, long enough.",
            },
        ).status_code
        == 409
    )
    assert (
        admin.post(
            base,
            json={
                "disposition": "referred",
                "note": "Please seek appropriate urgent medical care for symptoms.",
            },
        ).status_code
        == 200
    )
    assert admin.get("/api/portal", headers=token).json()["status"] == "referred"


def test_approval_publication_edit_and_stale_version(admin):
    id, token = create(admin)
    base = "/api/staff/cases/" + id
    assert admin.get("/api/portal", headers=token).json()["plan"] == ""
    assert (
        admin.post(
            base + "/approve", json={"version": 1, "confirm_reviewed": True}
        ).status_code
        == 409
    )
    prepare(admin, id)
    view = admin.get("/api/portal", headers=token).json()
    assert view["plan"] and view["signature"]["name"] == "admin"
    tick()
    with SessionLocal() as db:
        assert db.scalar(select(Job).where(Job.case_id == id)).state == "manual"
    admin.put(
        base + "/plan",
        json={
            "text": "UPDATED SYNTHETIC DRAFT. This revision requires actual review and a new approval before publication."
        },
    )
    assert admin.get("/api/portal", headers=token).json()["plan"] == ""
    assert (
        admin.post(
            base + "/approve", json={"version": 1, "confirm_reviewed": True}
        ).status_code
        == 409
    )
    assert (
        admin.post(
            base + "/approve", json={"version": 2, "confirm_reviewed": True}
        ).status_code
        == 200
    )


def test_contact_gate_and_scoped_tokens(admin):
    id, token = create(admin)
    other, other_token = create(admin)
    base = "/api/staff/cases/" + id
    admin.put(
        base + "/plan",
        json={
            "text": "SYNTHETIC DRAFT CONTENT. This plan cannot be approved without verified contact and suitability."
        },
    )
    admin.post(
        base + "/review",
        json={"disposition": "eligible", "note": "Synthetic review note long enough."},
    )
    assert (
        admin.post(
            base + "/approve", json={"version": 1, "confirm_reviewed": True}
        ).status_code
        == 409
    )
    assert (
        admin.get("/api/portal", headers=token).json()["case_id"] == id
        and admin.get("/api/portal", headers=other_token).json()["case_id"] == other
    )
    assert (
        admin.get("/api/portal", headers={"Authorization": "Bearer forged"}).status_code
        == 401
    )


def test_checkout_gate_webhook_and_duplicate_schedule(
    admin, payment_settings, monkeypatch
):
    monkeypatch.setattr(providers, "payment_link", fake_link)
    id, token = create(admin, "diet")
    assert admin.post("/api/checkout", headers=token).status_code == 409
    prepare(admin, id)
    first = admin.post("/api/checkout", headers=token)
    assert (
        first.status_code == 200
        and admin.post("/api/checkout", headers=token).json() == first.json()
    )
    assert admin.get("/api/portal", headers=token).json()["plan"] == ""
    with SessionLocal() as db:
        event = event_for(db.scalar(select(Payment).where(Payment.case_id == id)))
    assert webhook(admin, event, "wrong").status_code == 401
    assert webhook(admin, event, payment_settings.pay_webhook).status_code == 200
    assert (
        webhook(admin, event, payment_settings.pay_webhook).json()["duplicate"] is True
    )
    assert admin.get("/api/portal", headers=token).json()["plan"]
    with SessionLocal() as db:
        assert sorted(
            j.day for j in db.scalars(select(Job).where(Job.case_id == id)).all()
        ) == [0, 3, 7, 14]


@pytest.mark.parametrize(
    "mismatch",
    [
        {"amount_paid": 1},
        {"currency": "USD"},
        {"id": "plink_wrong"},
        {"status": "cancelled"},
    ],
)
def test_payment_mismatch(admin, payment_settings, monkeypatch, mismatch):
    id, token, event = start_payment(admin, monkeypatch)
    event["payload"]["payment_link"]["entity"].update(mismatch)
    assert (
        webhook(admin, event, payment_settings.pay_webhook).status_code == 400
        and admin.get("/api/portal", headers=token).json()["paid"] is False
    )


def test_uncertain_creation_never_duplicate(admin, payment_settings, monkeypatch):
    calls = []

    def timeout(p):
        calls.append(p.id)
        raise httpx.ReadTimeout("synthetic")

    monkeypatch.setattr(providers, "payment_link", timeout)
    id, token = create(admin, "diet")
    prepare(admin, id)
    assert (
        admin.post("/api/checkout", headers=token).status_code == 502
        and admin.post("/api/checkout", headers=token).status_code == 409
        and len(calls) == 1
    )


def test_refund_blocks_access_and_late_paid_replay(
    admin, payment_settings, monkeypatch
):
    id, token, event = start_payment(admin, monkeypatch)
    assert webhook(admin, event, payment_settings.pay_webhook).status_code == 200
    refund = {
        "event": "payment.refunded",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_synthetic",
                    "amount": 29900,
                    "amount_refunded": 29900,
                    "currency": "INR",
                }
            }
        },
    }
    assert (
        webhook(admin, refund, payment_settings.pay_webhook, "refund-event").status_code
        == 200
    )
    assert (
        webhook(
            admin, event, payment_settings.pay_webhook, "late-paid-event"
        ).status_code
        == 200
    )
    view = admin.get("/api/portal", headers=token).json()
    assert (
        view["status"] == "cancelled" and view["plan"] == "" and view["paid"] is False
    )
    with SessionLocal() as db:
        assert all(
            j.state == "cancelled"
            for j in db.scalars(select(Job).where(Job.case_id == id)).all()
        )


def test_checkins_review_and_30_day_schedule(admin):
    id, token = active(admin, "support30")
    body = {"day": 3, "adherence": "need_help", "note": "Synthetic difficulty."}
    assert (
        admin.post("/api/portal/checkins", headers=token, json=body).status_code == 200
        and admin.post("/api/portal/checkins", headers=token, json=body).status_code
        == 409
    )
    check = admin.get("/api/staff/cases/" + id).json()["checkins"][0]
    assert (
        admin.post(
            "/api/staff/cases/" + id + "/checkins/" + check["id"] + "/review",
            json={"note": "Synthetic follow-up action documented by the practitioner."},
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert sorted(
            j.day for j in db.scalars(select(Job).where(Job.case_id == id)).all()
        ) == [0, 3, 7, 14, 21, 30]
    feedback = admin.get("/api/portal", headers=token).json()["checkin_history"]
    assert (
        feedback[0]["feedback"]
        == "Synthetic follow-up action documented by the practitioner."
    )


def test_checkin_not_due_or_outside_product(admin):
    id, token = create(admin, "diet")
    prepare(admin, id)
    with SessionLocal() as db:
        case = db.get(Case, id)
        case.paid = 1
        activate(db, case)
        db.commit()
    assert (
        admin.post(
            "/api/portal/checkins",
            headers=token,
            json={"day": 3, "adherence": "going_well"},
        ).status_code
        == 409
    )
    assert (
        admin.post(
            "/api/portal/checkins",
            headers=token,
            json={"day": 21, "adherence": "going_well"},
        ).status_code
        == 409
    )


def wa_event(admin, data, secret):
    body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {"value": {"metadata": {"phone_number_id": "12345"}, **data}}
                    ]
                }
            ]
        }
    ).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return admin.post(
        "/api/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig}
    )


def test_whatsapp_acceptance_status_order_and_stop(
    admin, whatsapp_settings, monkeypatch
):
    monkeypatch.setattr(providers, "whatsapp_send", lambda phone: "wamid_synthetic")
    id, token = create(admin, whatsapp_opt_in=True)
    prepare(admin, id)
    tick()
    with SessionLocal() as db:
        assert db.scalar(select(Job).where(Job.case_id == id)).state == "accepted"
    assert (
        wa_event(
            admin,
            {"statuses": [{"id": "wamid_synthetic", "status": "delivered"}]},
            "wrong",
        ).status_code
        == 401
    )
    for status in ["delivered", "sent", "failed"]:
        assert (
            wa_event(
                admin,
                {"statuses": [{"id": "wamid_synthetic", "status": status}]},
                whatsapp_settings.wa_secret,
            ).status_code
            == 200
        )
    with SessionLocal() as db:
        assert db.scalar(select(Job).where(Job.case_id == id)).state == "delivered"
    assert (
        wa_event(
            admin,
            {
                "messages": [
                    {"from": "919999999999", "type": "text", "text": {"body": "STOP"}}
                ]
            },
            whatsapp_settings.wa_secret,
        ).status_code
        == 200
    )
    assert admin.get("/api/portal", headers=token).json()["whatsapp_opt_in"] is False


def test_whatsapp_timeout_no_blind_retry(admin, whatsapp_settings, monkeypatch):
    calls = []

    def timeout(phone):
        calls.append(phone)
        raise httpx.ReadTimeout("synthetic")

    monkeypatch.setattr(providers, "whatsapp_send", timeout)
    id, _ = create(admin, whatsapp_opt_in=True)
    prepare(admin, id)
    tick()
    tick()
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.scalar(select(Job).where(Job.case_id == id)).state == "uncertain"


def test_whatsapp_429_retry_has_backoff(admin, whatsapp_settings, monkeypatch):
    def reject(phone):
        raise httpx.HTTPStatusError(
            "synthetic",
            request=httpx.Request("POST", "https://example.test"),
            response=httpx.Response(429),
        )

    monkeypatch.setattr(providers, "whatsapp_send", reject)
    id, _ = create(admin, whatsapp_opt_in=True)
    prepare(admin, id)
    tick()
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.case_id == id))
        assert job.state == "pending" and job.attempts == 1 and job.due_at > now()


def test_delete_children_token_finance_and_stale_retry(admin):
    data = payload("diet")
    response = admin.post("/api/intake/diet", json=data).json()
    id = response["case_id"]
    token = {"Authorization": "Bearer " + response["portal_url"].split("#")[1]}
    prepare(admin, id)
    with SessionLocal() as db:
        case = db.get(Case, id)
        case.paid = 1
        activate(db, case)
        case.activated_at = now() - 5 * 86400
        db.add(Payment(case_id=id, amount=29900, status="paid"))
        db.commit()
    admin.post(
        "/api/portal/checkins",
        headers=token,
        json={"day": 3, "adherence": "going_well"},
    )
    assert (
        admin.delete("/api/portal/data", headers=token).status_code == 200
        and admin.get("/api/portal", headers=token).status_code == 401
    )
    assert admin.post("/api/intake/diet", json=data).status_code == 410
    with SessionLocal() as db:
        assert (
            db.get(Case, id) is None
            and db.scalars(select(Job)).all() == []
            and db.scalars(select(Checkin)).all() == []
            and db.scalar(select(Payment)).case_id is None
        )


def test_encryption_and_retention(admin):
    id, token = create(admin)
    with SessionLocal() as db:
        case = db.get(Case, id)
        assert (
            "Synthetic Person" not in case.data_cipher
            and "9999999999" not in case.data_cipher
            and token["Authorization"].split()[1] not in case.token_cipher
        )
        assert decrypt(case.data_cipher)["input"]["age"] == 35
        case.expires_at = now() - 1
        db.commit()
    tick()
    assert admin.get("/api/portal", headers=token).status_code == 401


def test_encrypted_backup_restore(admin, tmp_path):
    id, token = create(admin)
    path = tmp_path / "backup.enc"
    backup(path)
    assert b"Synthetic Person" not in path.read_bytes()
    with pytest.raises(SystemExit):
        restore(path)
    Base.metadata.drop_all(engine)
    init_db()
    restore(path)
    assert admin.get("/api/portal", headers=token).json()["case_id"] == id


def test_rotation_revokes_old_patient_link(admin):
    id, token = create(admin)
    base = "/api/staff/cases/" + id + "/rotate-access-link"
    assert (
        admin.post(
            base, json={"note": "Synthetic recovery evidence long enough."}
        ).status_code
        == 409
    )
    prepare(admin, id)
    response = admin.post(
        base, json={"note": "Synthetic identity verification repeated for recovery."}
    )
    assert response.status_code == 200
    assert admin.get("/api/portal", headers=token).status_code == 401
    new = {"Authorization": "Bearer " + response.json()["portal_url"].split("#")[1]}
    assert admin.get("/api/portal", headers=new).status_code == 200


def test_deleted_unpaid_case_cancels_provider_link(
    admin, payment_settings, monkeypatch
):
    id, token, event = start_payment(admin, monkeypatch)
    entity = event["payload"]["payment_link"]["entity"].copy()
    entity["status"] = "cancelled"
    calls = []

    def cancel(provider_id):
        calls.append(provider_id)
        return entity

    monkeypatch.setattr(providers, "cancel_payment_link", cancel)
    assert admin.delete("/api/portal/data", headers=token).status_code == 200
    tick()
    with SessionLocal() as db:
        payment = db.scalar(select(Payment))
        assert (
            payment.case_id is None
            and payment.status == "cancelled"
            and payment.cancel_requested == 0
        )
    assert len(calls) == 1


def test_size_errors_static_pages_and_production_guards(client):
    assert (
        client.post("/api/intake/report", json=payload(notes="x" * 70000)).status_code
        == 413
    )
    response = client.post(
        "/api/intake/report", json=payload(age=0, name="Private synthetic name")
    )
    assert response.status_code == 422 and "Private synthetic name" not in response.text
    for path in ["/", "/app", "/portal", "/assets/landing.js"]:
        r = client.get(path)
        assert r.status_code == 200 and r.headers["referrer-policy"] == "no-referrer"
    with pytest.raises(RuntimeError):
        dataclasses.replace(settings, environment="production").validate()
