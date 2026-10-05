import os, time, uuid
from sqlalchemy import (
    create_engine,
    event,
    String,
    Integer,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    version: Mapped[int] = mapped_column(default=1)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="practitioner")
    credential: Mapped[str] = mapped_column(String(250), default="")
    active: Mapped[int] = mapped_column(default=1)


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    csrf_cipher: Mapped[str] = mapped_column(Text)
    expires: Mapped[int] = mapped_column(Integer)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    intake_key: Mapped[str] = mapped_column(String(36), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_cipher: Mapped[str] = mapped_column(Text)
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    lane: Mapped[str] = mapped_column(String(20))
    product: Mapped[str] = mapped_column(String(20))
    data_cipher: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="awaiting_review")
    contact_verified: Mapped[int] = mapped_column(default=0)
    review_cipher: Mapped[str] = mapped_column(Text, default="")
    plan_cipher: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(default=0)
    approved_version: Mapped[int] = mapped_column(default=0)
    signature_cipher: Mapped[str] = mapped_column(Text, default="")
    paid: Mapped[int] = mapped_column(default=0)
    activated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    viewed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(default=now)
    expires_at: Mapped[int] = mapped_column(Integer)


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (UniqueConstraint("case_id", "day"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)
    data_cipher: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(default=now)
    reviewed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    provider_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    provider_url: Mapped[str] = mapped_column(Text, default="")
    payment_id: Mapped[str] = mapped_column(String(100), default="")
    amount: Mapped[int] = mapped_column(Integer)
    refunded_amount: Mapped[int] = mapped_column(default=0)
    cancel_requested: Mapped[int] = mapped_column(default=0)
    next_cancel_at: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default="creating")
    created_at: Mapped[int] = mapped_column(default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    dedup_key: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    day: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[int] = mapped_column(Integer, index=True)
    state: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    lease_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(
        String(200), unique=True, nullable=True
    )
    reason: Mapped[str] = mapped_column(String(200), default="")


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    case_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[int] = mapped_column(default=now)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    created_at: Mapped[int] = mapped_column(default=now)


class DeletedIntake(Base):
    __tablename__ = "deleted_intakes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[int] = mapped_column(Integer)


class Rate(Base):
    __tablename__ = "rate_limits"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    expires: Mapped[int] = mapped_column(Integer)


class Heartbeat(Base):
    __tablename__ = "heartbeat"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    at: Mapped[int] = mapped_column(Integer)


if settings.database_url.startswith("sqlite:"):
    os.makedirs("data", mode=0o700, exist_ok=True)
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 20}
    if settings.database_url.startswith("sqlite:")
    else {},
)
if settings.database_url.startswith("sqlite:"):

    @event.listens_for(engine, "connect")
    def sqlite_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(SchemaVersion, 1):
            db.add(SchemaVersion(id=1, version=1))
            db.commit()


def get_db():
    with SessionLocal() as db:
        yield db
