from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker


Base = declarative_base()


class CatalogEmbeddingRecord(Base):
    __tablename__ = "catalog_embeddings"
    product_id = Column(String(150), ForeignKey("catalog_products.product_id"), primary_key=True)
    model = Column(String(100), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    vector_json = Column(Text, nullable=False)


_engine = None
_session_factory = None
_init_lock = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or "sqlite:////tmp/guiltless_ai_phase4.db"
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def _enable_sqlite_foreign_keys(engine) -> None:
    """SQLite ignores foreign keys unless asked, which hides referential bugs that
    only surface on the Postgres deployment. Enforce them in every environment."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    """Initialise the engine exactly once, even under concurrent first requests."""
    global _engine, _session_factory
    if _session_factory is not None:
        return
    with _init_lock:
        if _session_factory is not None:
            return
        url = database_url()
        engine_kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {
            "pool_pre_ping": True, "pool_size": 3, "max_overflow": 2,
            "pool_timeout": 10, "connect_args": {"connect_timeout": 10},
        }
        engine = create_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        # Publish the factory before the engine so no thread can observe a
        # non-None _engine with a still-unset _session_factory.
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        _engine = engine


def database_readiness() -> dict:
    """Confirm connectivity without disclosing hostnames, users, or credentials."""
    init_db()
    with _engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"ready": True, "database": _engine.dialect.name}


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class User(Base):
    __tablename__ = "users"
    id = Column(String(100), primary_key=True)
    display_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id = Column(String(100), ForeignKey("users.id"), primary_key=True)
    goal = Column(String(100), nullable=False, default="balanced nutrition")
    diet = Column(String(100), nullable=False, default="no restriction")
    allergies_json = Column(Text, nullable=False, default="[]")
    disliked_foods_json = Column(Text, nullable=False, default="[]")
    budget = Column(String(100), nullable=False, default="flexible")
    preferred_store = Column(String(100), nullable=False, default="Instacart")
    training_days = Column(Integer, nullable=False, default=3)
    equipment_json = Column(Text, nullable=False, default="[]")
    calorie_target = Column(Integer, nullable=False, default=2200)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProductRecord(Base):
    __tablename__ = "products"
    id = Column(String(36), primary_key=True)
    name = Column(String(150), nullable=False, index=True)
    brand = Column(String(150), nullable=True)
    category = Column(String(100), nullable=True)
    nutrition_json = Column(Text, nullable=False, default="{}")
    ingredients_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class CatalogProductRecord(Base):
    """Canonical source-backed catalog; separate from legacy scan records."""
    __tablename__ = "catalog_products"
    product_id = Column(String(150), primary_key=True)
    barcode = Column(String(100), unique=True, nullable=True, index=True)
    source = Column(String(100), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    source_json = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ScanHistory(Base):
    __tablename__ = "scan_history"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=True)
    extraction_mode = Column(String(50), nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class BagItem(Base):
    __tablename__ = "bag_items"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=True)
    product_json = Column(Text, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class MealPlanRecord(Base):
    __tablename__ = "meal_plans"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class WorkoutPlanRecord(Base):
    __tablename__ = "workout_plans"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class CoachClient(Base):
    __tablename__ = "coach_clients"
    id = Column(String(36), primary_key=True)
    owner_user_id = Column(String(100), ForeignKey("users.id"), nullable=False, default="demo-user", index=True)
    client_name = Column(String(100), nullable=False, index=True)
    goal = Column(String(100), nullable=False)
    diet = Column(String(100), nullable=False)
    allergies_json = Column(Text, nullable=False, default="[]")
    days_per_week = Column(Integer, nullable=False, default=3)
    equipment_json = Column(Text, nullable=False, default="[]")
    calorie_target = Column(Integer, nullable=False, default=2200)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class ClientPlanRecord(Base):
    __tablename__ = "client_plans"
    id = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("coach_clients.id"), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(100), nullable=True)
    context_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class CheckoutRecord(Base):
    __tablename__ = "checkout_sessions"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("coach_clients.id"), nullable=True, index=True)
    provider = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    items_json = Column(Text, nullable=False)
    checkout_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
