from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


Base = declarative_base()
_engine = None
_session_factory = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or "sqlite:////tmp/guiltless_ai_phase4.db"
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def init_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        return
    url = database_url()
    engine_kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    _engine = create_engine(url, **engine_kwargs)
    Base.metadata.create_all(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)


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
