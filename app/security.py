import hashlib, hmac, json, secrets
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .config import settings
from .db import get_db, LoginSession, User, Case, Audit, now

cipher = Fernet(settings.key.encode())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def private_digest(value):
    return hmac.new(settings.key.encode(), value.encode(), hashlib.sha256).hexdigest()


def encrypt(value):
    return cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def decrypt(value):
    return json.loads(cipher.decrypt(value.encode())) if value else {}


def password_hash(password):
    salt = secrets.token_bytes(16)
    return (
        salt.hex()
        + ":"
        + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    )


def password_ok(password, encoded):
    try:
        salt, expected = encoded.split(":")
        return hmac.compare_digest(
            hashlib.scrypt(
                password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
            ).hex(),
            expected,
        )
    except (ValueError, TypeError):
        return False


def staff(request: Request, db=Depends(get_db)):
    session = db.get(LoginSession, digest(request.cookies.get("clarity_session", "")))
    if not session or session.expires <= now():
        raise HTTPException(401, "Please sign in.")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account inactive.")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not hmac.compare_digest(
        session.csrf_hash, digest(request.headers.get("X-CSRF-Token", ""))
    ):
        raise HTTPException(403, "Refresh the workspace before trying again.")
    request.state.auth_session = session
    return user


def qualified(user):
    if not user.credential:
        raise HTTPException(403, "Verified practitioner qualification required.")


def staff_case(db, case_id, user, lock=False):
    query = select(Case).where(Case.id == case_id)
    if lock:
        query = query.with_for_update()
    case = db.scalar(query)
    if not case or (user.role != "admin" and case.assigned_to != user.id):
        raise HTTPException(404, "Case not found.")
    if case.expires_at <= now():
        raise HTTPException(410, "Case expired.")
    return case


def patient_case(request: Request, db=Depends(get_db)):
    value = request.headers.get("Authorization", "")
    token = value[7:] if value.startswith("Bearer ") else ""
    if len(token) < 40:
        raise HTTPException(401, "Open your private access link.")
    case = db.scalar(select(Case).where(Case.token_hash == digest(token)))
    if not case or case.expires_at <= now():
        raise HTTPException(401, "Invalid or expired access link.")
    return case


def audit(db, actor, action, case_id=""):
    db.add(Audit(actor=actor, action=action, case_id=case_id))
