import hashlib, json, secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update, text, func
from sqlalchemy.exc import IntegrityError
from .config import settings
from .db import (
    SessionLocal,
    get_db,
    init_db,
    SchemaVersion,
    User,
    LoginSession,
    Case,
    Checkin,
    Payment,
    Job,
    WebhookEvent,
    Heartbeat,
    now,
)
from .security import (
    staff,
    qualified,
    staff_case,
    patient_case,
    password_hash,
    password_ok,
    digest,
    encrypt,
    decrypt,
    private_digest,
    audit,
)
from .schemas import (
    ReportIntake,
    DietIntake,
    Login,
    Review,
    Draft,
    Note,
    Assignment,
    Approval,
    CheckinInput,
    OptIn,
)
from .services import (
    PRODUCTS,
    rate_limit,
    create_intake,
    patient_view,
    staff_view,
    approved,
    released,
    activate,
    erase_case,
)
from . import providers

WEB = Path(__file__).resolve().parent.parent / "web"
DUMMY_PASSWORD = password_hash(secrets.token_urlsafe(32))


@asynccontextmanager
async def lifespan(_):
    if not settings.production:
        init_db()
    with SessionLocal() as db:
        version = db.get(SchemaVersion, 1)
        if not version or version.version != 1:
            raise RuntimeError("Run python -m app.cli init-db first")
    yield


app = FastAPI(
    title="ClarityBS MVP",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.production else "/docs",
    openapi_url=None if settings.production else "/openapi.json",
    redoc_url=None,
)


@app.middleware("http")
async def protections(request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 65536:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        if not request.url.path.startswith("/api/webhooks/"):
            origin = request.headers.get("origin")
            if (origin and origin != settings.origin) or (
                settings.production and not origin
            ):
                return JSONResponse({"detail": "Origin not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        }
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        {
            "detail": "Check required fields, explicit consent, adult age and supported units."
        },
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    return JSONResponse(
        {"detail": "Request already processing. Refresh before retrying."},
        status_code=409,
    )


@app.get("/api/public-config")
def config():
    return {
        "intake_enabled": settings.intake_enabled,
        "payment_enabled": settings.payment_mode == "razorpay",
        "business_name": settings.business,
        "support_email": settings.support,
        "consent_version": settings.consent_version,
        "retention_days": settings.retention,
        "environment": settings.environment,
    }


@app.get("/health/live")
def live():
    return {"status": "up"}


@app.get("/api/health", dependencies=[Depends(staff)])
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    beat = db.get(Heartbeat, "worker")
    pending = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.cancel_requested > 0)
    )
    return {
        "database": "reachable",
        "worker": "recent" if beat and beat.at > now() - 180 else "stale",
        "worker_last_seen": beat.at if beat else None,
        "payment_mode": settings.payment_mode,
        "notification_mode": settings.notification_mode,
        "public_intake": settings.intake_enabled,
        "payment_actions": pending,
    }


@app.post("/api/intake/report")
def report(payload: ReportIntake, request: Request, db=Depends(get_db)):
    rate_limit(db, "intake", request.client.host, 20)
    return create_intake(db, payload, "report")


@app.post("/api/intake/diet")
def diet(payload: DietIntake, request: Request, db=Depends(get_db)):
    rate_limit(db, "intake", request.client.host, 20)
    return create_intake(db, payload, "diet")


@app.post("/api/auth/login")
def login(payload: Login, request: Request, response: Response, db=Depends(get_db)):
    rate_limit(db, "login-ip", request.client.host, 30, 900)
    rate_limit(db, "login-account", payload.email.lower(), 8, 900)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    valid = password_ok(
        payload.password, user.password_hash if user else DUMMY_PASSWORD
    )
    if not valid or not user or not user.active:
        raise HTTPException(401, "Email or password incorrect.")
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            id=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            csrf_cipher=encrypt({"csrf": csrf}),
            expires=now() + 8 * 3600,
        )
    )
    audit(db, user.id, "signed_in")
    db.commit()
    response.set_cookie(
        "clarity_session",
        token,
        httponly=True,
        secure=settings.production,
        samesite="strict",
        max_age=8 * 3600,
        path="/",
    )
    return {
        "csrf": csrf,
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "credential": user.credential,
        },
    }


@app.get("/api/auth/me")
def me(request: Request, user=Depends(staff)):
    return {
        "csrf": decrypt(request.state.auth_session.csrf_cipher)["csrf"],
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "credential": user.credential,
        },
    }


@app.post("/api/auth/logout")
def logout(
    request: Request, response: Response, user=Depends(staff), db=Depends(get_db)
):
    db.delete(db.get(LoginSession, request.state.auth_session.id))
    db.commit()
    response.delete_cookie("clarity_session", path="/")
    return {"ok": True}


@app.get("/api/staff/users")
def users(user=Depends(staff), db=Depends(get_db)):
    rows = (
        db.scalars(select(User).where(User.active == 1)).all()
        if user.role == "admin"
        else [user]
    )
    return [{"id": u.id, "name": u.name, "credential": u.credential} for u in rows]


@app.get("/api/staff/cases")
def list_cases(user=Depends(staff), db=Depends(get_db)):
    query = (
        select(Case)
        .where(Case.expires_at > now())
        .order_by(Case.created_at.desc())
        .limit(200)
    )
    if user.role != "admin":
        query = query.where(Case.assigned_to == user.id)
    return [
        {
            "id": c.id,
            "name": decrypt(c.data_cipher)["input"]["name"],
            "lane": c.lane,
            "product": c.product,
            "status": c.status,
            "assigned_to": c.assigned_to,
            "paid": bool(c.paid),
            "version": c.version,
            "approved_version": c.approved_version,
            "created_at": c.created_at,
        }
        for c in db.scalars(query).all()
    ]


@app.get("/api/staff/cases/{case_id}")
def detail(case_id: str, user=Depends(staff), db=Depends(get_db)):
    case = staff_case(db, case_id, user)
    audit(db, user.id, "case_viewed", case.id)
    db.commit()
    return staff_view(db, case)


@app.post("/api/staff/cases/{case_id}/assign")
def assign(case_id: str, payload: Assignment, user=Depends(staff), db=Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator required.")
    case = staff_case(db, case_id, user, True)
    target = db.get(User, str(payload.user_id))
    if not target or not target.active:
        raise HTTPException(404, "Active practitioner not found.")
    case.assigned_to = target.id
    audit(db, user.id, "case_assigned", case.id)
    db.commit()
    return {"ok": True}


@app.post("/api/staff/cases/{case_id}/verify-contact")
def verify_contact(
    case_id: str, payload: Note, user=Depends(staff), db=Depends(get_db)
):
    case = staff_case(db, case_id, user, True)
    data = decrypt(case.data_cipher)
    data["contact_verification"] = {"note": payload.note, "by": user.id, "at": now()}
    case.data_cipher = encrypt(data)
    case.contact_verified = 1
    audit(db, user.id, "contact_verified", case.id)
    db.commit()
    return {"ok": True}


@app.post("/api/staff/cases/{case_id}/rotate-access-link")
def rotate(case_id: str, payload: Note, user=Depends(staff), db=Depends(get_db)):
    case = staff_case(db, case_id, user, True)
    if not case.contact_verified:
        raise HTTPException(409, "Verify contact before recovering access.")
    token = secrets.token_urlsafe(48)
    case.token_hash = digest(token)
    case.token_cipher = encrypt({"token": token})
    data = decrypt(case.data_cipher)
    data["access_recovery"] = {"note": payload.note, "by": user.id, "at": now()}
    case.data_cipher = encrypt(data)
    audit(db, user.id, "access_link_rotated", case.id)
    db.commit()
    return {"portal_url": settings.origin + "/portal#" + token}


@app.post("/api/staff/cases/{case_id}/review")
def review(case_id: str, payload: Review, user=Depends(staff), db=Depends(get_db)):
    qualified(user)
    case = staff_case(db, case_id, user, True)
    if (
        decrypt(case.data_cipher)["input"]["health_screening"] == "urgent"
        and payload.disposition != "referred"
    ):
        raise HTTPException(
            409,
            "Urgent-screen cases must be referred. Start a fresh intake after medical clearance.",
        )
    if case.status in {"cancelled", "referred"} and payload.disposition == "eligible":
        raise HTTPException(409, "Cancelled or referred cases need a new intake.")
    case.status = payload.disposition
    case.review_cipher = encrypt({"note": payload.note, "by": user.id, "at": now()})
    if case.status == "referred":
        payment = db.scalar(select(Payment).where(Payment.case_id == case.id))
        if payment and payment.status not in {"paid", "refunded", "cancelled"}:
            payment.cancel_requested = 1
        case.approved_version = 0
        db.execute(
            update(Job)
            .where(Job.case_id == case.id, Job.state.in_(["pending", "manual"]))
            .values(
                state="cancelled",
                reason="Referred; resolve any paid service/refund manually",
            )
        )
    audit(db, user.id, "suitability_reviewed", case.id)
    db.commit()
    return {"ok": True}


@app.put("/api/staff/cases/{case_id}/plan")
def draft(case_id: str, payload: Draft, user=Depends(staff), db=Depends(get_db)):
    qualified(user)
    case = staff_case(db, case_id, user, True)
    case.plan_cipher = encrypt({"text": payload.text})
    case.version += 1
    case.approved_version = 0
    case.signature_cipher = ""
    audit(db, user.id, "plan_draft_saved", case.id)
    db.commit()
    return {"version": case.version}


@app.post("/api/staff/cases/{case_id}/approve")
def approve(case_id: str, payload: Approval, user=Depends(staff), db=Depends(get_db)):
    qualified(user)
    case = staff_case(db, case_id, user, True)
    if case.status != "eligible" or not case.contact_verified or not case.plan_cipher:
        raise HTTPException(
            409, "Complete suitability, contact verification and a draft first."
        )
    if payload.version != case.version:
        raise HTTPException(409, "Plan changed. Review the current version.")
    case.approved_version = case.version
    case.signature_cipher = encrypt(
        {
            "name": user.name,
            "credential": user.credential,
            "by": user.id,
            "at": now(),
            "version": case.version,
        }
    )
    activate(db, case)
    audit(db, user.id, "plan_approved", case.id)
    db.commit()
    return {"ok": True, "released": released(case)}


@app.get("/api/portal")
def portal(case=Depends(patient_case), db=Depends(get_db)):
    if released(case) and not case.viewed_at:
        case.viewed_at = now()
        audit(db, "patient", "plan_viewed", case.id)
        db.commit()
    checks = db.scalars(select(Checkin).where(Checkin.case_id == case.id)).all()
    history = []
    for check in checks:
        data = decrypt(check.data_cipher)
        history.append(
            {
                "day": check.day,
                "adherence": data["adherence"],
                "note": data.get("note", ""),
                "created_at": check.created_at,
                "feedback": data.get("review", {}).get("note", "")
                if check.reviewed_at
                else "",
                "reviewed_at": check.reviewed_at,
            }
        )
    return {
        **patient_view(case),
        "completed_days": [c.day for c in checks],
        "checkin_history": history,
    }


@app.post("/api/portal/checkins")
def checkin(payload: CheckinInput, case=Depends(patient_case), db=Depends(get_db)):
    if not released(case) or payload.day not in PRODUCTS[case.product]["days"]:
        raise HTTPException(409, "No check-in available for that day.")
    if now() < case.activated_at + payload.day * 86400:
        raise HTTPException(409, "Check-in not due yet.")
    if db.scalar(
        select(Checkin).where(Checkin.case_id == case.id, Checkin.day == payload.day)
    ):
        raise HTTPException(409, "Check-in already submitted.")
    db.add(
        Checkin(
            case_id=case.id, day=payload.day, data_cipher=encrypt(payload.model_dump())
        )
    )
    audit(db, "patient", "checkin_submitted", case.id)
    db.commit()
    return {
        "ok": True,
        "message": "Saved for your practitioner. This inbox is not monitored for emergencies.",
    }


@app.post("/api/portal/notification-preference")
def preference(payload: OptIn, case=Depends(patient_case), db=Depends(get_db)):
    data = decrypt(case.data_cipher)
    data["input"]["whatsapp_opt_in"] = payload.whatsapp_opt_in
    data["whatsapp_opt_in_at"] = now() if payload.whatsapp_opt_in else None
    case.data_cipher = encrypt(data)
    audit(db, "patient", "notification_preference_changed", case.id)
    db.commit()
    return {"ok": True}


@app.delete("/api/portal/data")
def erase(case=Depends(patient_case), db=Depends(get_db)):
    erase_case(db, case, "patient")
    db.commit()
    return {
        "ok": True,
        "message": "Your intake, plan, check-ins, tasks and access link are removed. Separate payment records may remain; encrypted backups expire within seven days under our backup procedure.",
    }


@app.post("/api/staff/cases/{case_id}/checkins/{checkin_id}/review")
def checkin_review(
    case_id: str,
    checkin_id: str,
    payload: Note,
    user=Depends(staff),
    db=Depends(get_db),
):
    qualified(user)
    case = staff_case(db, case_id, user, True)
    check = db.get(Checkin, checkin_id)
    if not check or check.case_id != case.id:
        raise HTTPException(404, "Check-in not found.")
    data = decrypt(check.data_cipher)
    data["review"] = {"note": payload.note, "by": user.id, "at": now()}
    check.data_cipher = encrypt(data)
    check.reviewed_at = now()
    audit(db, user.id, "checkin_reviewed", case.id)
    db.commit()
    return {"ok": True}


@app.post("/api/staff/cases/{case_id}/jobs/{job_id}/manual-complete")
def complete(
    case_id: str, job_id: str, payload: Note, user=Depends(staff), db=Depends(get_db)
):
    case = staff_case(db, case_id, user, True)
    job = db.get(Job, job_id)
    if (
        not job
        or job.case_id != case.id
        or job.state not in {"manual", "failed", "uncertain"}
        or not released(case)
    ):
        raise HTTPException(409, "Task cannot be completed in its current state.")
    data = decrypt(case.data_cipher)
    data.setdefault("manual_tasks", []).append(
        {"job_id": job.id, "note": payload.note, "by": user.id, "at": now()}
    )
    case.data_cipher = encrypt(data)
    job.state = "manual_done"
    job.reason = "Staff attested completion"
    audit(db, user.id, "manual_task_completed", case.id)
    db.commit()
    return {"ok": True}


@app.post("/api/checkout")
def checkout(case=Depends(patient_case), db=Depends(get_db)):
    if settings.payment_mode != "razorpay":
        raise HTTPException(503, "Online payment unavailable.")
    case = db.scalar(select(Case).where(Case.id == case.id).with_for_update())
    if (
        case.status != "eligible"
        or not approved(case)
        or not case.contact_verified
        or case.product == "report"
        or case.paid
    ):
        raise HTTPException(
            409, "Only approved unpaid routines can proceed to payment."
        )
    payment = db.scalar(select(Payment).where(Payment.case_id == case.id))
    if payment:
        if payment.status == "created" and payment.provider_url:
            return {"checkout_url": payment.provider_url}
        raise HTTPException(
            409, "An attempt already exists. Support must reconcile it."
        )
    payment = Payment(case_id=case.id, amount=PRODUCTS[case.product]["amount"])
    db.add(payment)
    db.flush()
    id = payment.id
    db.commit()
    try:
        result = providers.payment_link(payment)
    except Exception:
        payment = db.get(Payment, id)
        payment.status = "uncertain"
        db.commit()
        raise HTTPException(
            502,
            "Payment setup was not confirmed. No new attempt will be created automatically; contact support.",
        )
    payment = db.scalar(select(Payment).where(Payment.id == id).with_for_update())
    payment.provider_id = result["id"]
    payment.provider_url = result["short_url"]
    if payment.status not in {"paid", "refunded"}:
        payment.status = "created"
    audit(db, "patient", "checkout_created", case.id)
    db.commit()
    return {"checkout_url": payment.provider_url}


@app.post("/api/staff/cases/{case_id}/payment-reconcile")
def reconcile(case_id: str, user=Depends(staff), db=Depends(get_db)):
    case = staff_case(db, case_id, user)
    payment = db.scalar(select(Payment).where(Payment.case_id == case.id))
    if settings.payment_mode != "razorpay" or not payment or not payment.provider_id:
        raise HTTPException(
            409,
            "No provider link. Recover uncertain creation via the CLI using the provider reference_id.",
        )
    try:
        entity = providers.fetch_payment_link(payment.provider_id)
        if entity.get("status") == "paid":
            providers.apply_paid_link(db, entity)
        if payment.payment_id:
            entity = providers.fetch_payment(payment.payment_id)
            if entity.get("amount_refunded", 0):
                providers.apply_refund(db, entity)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Provider reconciliation unavailable.")
    db.commit()
    return {"status": payment.status}


@app.post("/api/webhooks/razorpay")
async def payment_webhook(request: Request, db=Depends(get_db)):
    if settings.payment_mode != "razorpay":
        raise HTTPException(503, "Provider disabled.")
    body = await request.body()
    providers.verify_signature(
        body, request.headers.get("X-Razorpay-Signature"), settings.pay_webhook
    )
    try:
        payload = json.loads(body)
        id = "razorpay:" + (
            request.headers.get("X-Razorpay-Event-Id")
            or hashlib.sha256(body).hexdigest()
        )
        if len(id) > 240:
            raise ValueError()
        if db.get(WebhookEvent, id):
            return {"ok": True, "duplicate": True}
        if payload.get("event") == "payment_link.paid":
            providers.apply_paid_link(
                db,
                payload["payload"]["payment_link"]["entity"],
                payload.get("payload", {})
                .get("payment", {})
                .get("entity", {})
                .get("id", ""),
            )
        elif payload.get("event") == "payment.refunded":
            providers.apply_refund(db, payload["payload"]["payment"]["entity"])
        elif payload.get("event") == "refund.processed":
            payment_id = payload["payload"]["refund"]["entity"]["payment_id"]
            if not str(payment_id).startswith("pay_"):
                raise ValueError()
            try:
                providers.apply_refund(db, providers.fetch_payment(payment_id))
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    502, "Refund reconciliation unavailable; provider may retry."
                )
        db.add(WebhookEvent(id=id))
        db.commit()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid webhook payload.")
    return {"ok": True}


@app.get("/api/webhooks/whatsapp")
def verify_whatsapp(request: Request):
    q = request.query_params
    if (
        settings.notification_mode != "whatsapp"
        or q.get("hub.mode") != "subscribe"
        or not secrets.compare_digest(q.get("hub.verify_token", ""), settings.wa_verify)
    ):
        raise HTTPException(403, "Verification failed.")
    return PlainTextResponse(q.get("hub.challenge", ""))


@app.post("/api/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db=Depends(get_db)):
    if settings.notification_mode != "whatsapp":
        raise HTTPException(503, "Provider disabled.")
    body = await request.body()
    providers.verify_signature(
        body, request.headers.get("X-Hub-Signature-256"), settings.wa_secret, "sha256="
    )
    try:
        payload = json.loads(body)
        ranks = {"accepted": 0, "sent": 1, "delivered": 2, "read": 3}
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if (
                    value.get("metadata", {}).get("phone_number_id")
                    != settings.wa_phone
                ):
                    continue
                for status in value.get("statuses", []):
                    job = db.scalar(
                        select(Job)
                        .where(Job.provider_id == status.get("id"))
                        .with_for_update()
                    )
                    incoming = status.get("status")
                    if (
                        job
                        and incoming in ranks
                        and ranks[incoming] > ranks.get(job.state, -1)
                    ):
                        job.state = incoming
                    elif job and incoming == "failed" and ranks.get(job.state, -1) < 2:
                        job.state = "failed"
                        job.reason = "Provider reported failure"
                for message in value.get("messages", []):
                    if message.get("type") == "text" and message.get("text", {}).get(
                        "body", ""
                    ).strip().upper() in {"STOP", "UNSUBSCRIBE"}:
                        for case in db.scalars(
                            select(Case).where(
                                Case.phone_hash
                                == private_digest("+" + message.get("from", "")),
                                Case.contact_verified == 1,
                            )
                        ).all():
                            data = decrypt(case.data_cipher)
                            data["input"]["whatsapp_opt_in"] = False
                            case.data_cipher = encrypt(data)
                            audit(db, "whatsapp", "notifications_opted_out", case.id)
        db.commit()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid webhook payload.")
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/app")
def workspace():
    return FileResponse(WEB / "workspace.html")


@app.get("/portal")
def portal_page():
    return FileResponse(WEB / "portal.html")


@app.get("/robots.txt")
def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /portal\nDisallow: /api/\nSitemap: "
        + settings.origin
        + "/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap():
    return Response(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'
        + settings.origin
        + "/</loc></url></urlset>",
        media_type="application/xml",
    )


app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")
