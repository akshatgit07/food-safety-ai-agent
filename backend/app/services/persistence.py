from __future__ import annotations

import json
import uuid
from typing import Any

from app.db import (
    BagItem,
    CheckoutRecord,
    ClientPlanRecord,
    CoachClient,
    CopilotMessage,
    MealPlanRecord,
    ProductRecord,
    ScanHistory,
    User,
    UserPreference,
    WorkoutPlanRecord,
    session_scope,
    utc_now,
)


DEMO_USER_ID = "demo-user"


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def ensure_user(user_id: str = DEMO_USER_ID) -> None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id, display_name="Demo User", created_at=utc_now(), updated_at=utc_now()))
            session.flush()
        if session.get(UserPreference, user_id) is None:
            session.add(UserPreference(user_id=user_id, updated_at=utc_now()))


def get_profile(user_id: str = DEMO_USER_ID) -> dict[str, Any]:
    ensure_user(user_id)
    with session_scope() as session:
        pref = session.get(UserPreference, user_id)
        return {
            "user_id": user_id,
            "goal": pref.goal,
            "diet": pref.diet,
            "allergies": _json(pref.allergies_json, []),
            "disliked_foods": _json(pref.disliked_foods_json, []),
            "budget": pref.budget,
            "preferred_store": pref.preferred_store,
            "training_days": pref.training_days,
            "equipment": _json(pref.equipment_json, []),
            "calorie_target": pref.calorie_target,
            "updated_at": pref.updated_at.isoformat(),
        }


def update_profile(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_user(user_id)
    with session_scope() as session:
        pref = session.get(UserPreference, user_id)
        for key in ("goal", "diet", "budget", "preferred_store"):
            if payload.get(key) is not None:
                setattr(pref, key, str(payload[key]))
        if payload.get("training_days") is not None:
            pref.training_days = int(payload["training_days"])
        if payload.get("calorie_target") is not None:
            pref.calorie_target = int(payload["calorie_target"])
        for key in ("allergies", "disliked_foods", "equipment"):
            if payload.get(key) is not None:
                setattr(pref, f"{key}_json", json.dumps(payload[key]))
        pref.updated_at = utc_now()
    return get_profile(user_id)


def save_product(product: dict[str, Any]) -> str:
    product_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(ProductRecord(
            id=product_id,
            name=str(product.get("name") or "Unknown product"),
            brand=product.get("brand"),
            category=product.get("category"),
            nutrition_json=json.dumps(product.get("nutrition") or {}),
            ingredients_json=json.dumps(product.get("ingredients") or []),
            created_at=utc_now(),
        ))
    return product_id


def save_scan_history(user_id: str, scan: dict[str, Any]) -> dict[str, Any]:
    ensure_user(user_id)
    product_id = save_product(scan.get("product") or {})
    record_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(ScanHistory(id=record_id, user_id=user_id, product_id=product_id, extraction_mode=str(scan.get("extraction_mode") or "unknown"), payload_json=json.dumps(scan), created_at=utc_now()))
    return {"scan_id": record_id, "product_id": product_id}


def recent_scans(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    ensure_user(user_id)
    with session_scope() as session:
        records = session.query(ScanHistory).filter(ScanHistory.user_id == user_id).order_by(ScanHistory.created_at.desc()).limit(limit).all()
        return [{"id": row.id, "product_id": row.product_id, "extraction_mode": row.extraction_mode, "scan": _json(row.payload_json, {}), "created_at": row.created_at.isoformat()} for row in records]


def add_bag_item(user_id: str, product: dict[str, Any], quantity: int = 1) -> dict[str, Any]:
    ensure_user(user_id)
    product_id = save_product(product)
    item_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(BagItem(id=item_id, user_id=user_id, product_id=product_id, product_json=json.dumps(product), quantity=max(1, quantity), created_at=utc_now()))
    return {"id": item_id, "product_id": product_id, "product": product, "quantity": max(1, quantity)}


def get_bag(user_id: str) -> list[dict[str, Any]]:
    ensure_user(user_id)
    with session_scope() as session:
        rows = session.query(BagItem).filter(BagItem.user_id == user_id).order_by(BagItem.created_at.asc()).all()
        return [{"id": row.id, "product_id": row.product_id, "product": _json(row.product_json, {}), "quantity": row.quantity, "created_at": row.created_at.isoformat()} for row in rows]


def clear_bag(user_id: str) -> int:
    ensure_user(user_id)
    with session_scope() as session:
        return session.query(BagItem).filter(BagItem.user_id == user_id).delete()


def save_user_plan(user_id: str, kind: str, plan: dict[str, Any]) -> dict[str, Any]:
    ensure_user(user_id)
    plan_id = str(uuid.uuid4())
    model = MealPlanRecord if kind == "meal" else WorkoutPlanRecord
    with session_scope() as session:
        session.add(model(id=plan_id, user_id=user_id, payload_json=json.dumps(plan), created_at=utc_now()))
    return {"id": plan_id, "type": kind, "user_id": user_id, "plan": plan}


def get_user_plans(user_id: str, limit: int = 20) -> dict[str, Any]:
    ensure_user(user_id)
    with session_scope() as session:
        meals = session.query(MealPlanRecord).filter(MealPlanRecord.user_id == user_id).order_by(MealPlanRecord.created_at.desc()).limit(limit).all()
        workouts = session.query(WorkoutPlanRecord).filter(WorkoutPlanRecord.user_id == user_id).order_by(WorkoutPlanRecord.created_at.desc()).limit(limit).all()
        serialize = lambda row: {"id": row.id, "plan": _json(row.payload_json, {}), "created_at": row.created_at.isoformat()}
        return {"meal_plans": [serialize(row) for row in meals], "workout_plans": [serialize(row) for row in workouts]}


def _client_dict(profile: CoachClient) -> dict[str, Any]:
    return {"id": profile.id, "client_name": profile.client_name, "goal": profile.goal, "diet": profile.diet, "allergies": _json(profile.allergies_json, []), "days_per_week": profile.days_per_week, "equipment": _json(profile.equipment_json, []), "calorie_target": profile.calorie_target, "created_at": profile.created_at.isoformat(), "updated_at": profile.updated_at.isoformat()}


class ClientNotFound(ValueError):
    """Raised when a caller references a coach client that they cannot address."""


def _owned_client(session, client_id: str, owner_user_id: str) -> CoachClient | None:
    """Look a client up *within the owner's scope*.

    Resolving by primary key alone let any caller address — and overwrite — another
    coach's client simply by supplying its id.
    """
    profile = session.get(CoachClient, client_id)
    if profile is None or profile.owner_user_id != owner_user_id:
        return None
    return profile


def create_or_update_client(payload: dict[str, Any], owner_user_id: str = DEMO_USER_ID) -> dict[str, Any]:
    ensure_user(owner_user_id)
    client_id = payload.get("client_id")
    with session_scope() as session:
        if client_id:
            profile = _owned_client(session, str(client_id), owner_user_id)
            if profile is None:
                # Previously this silently created a *different* client and returned an
                # id the caller never asked for. Fail loudly instead.
                raise ClientNotFound("Client profile not found.")
        else:
            # Without this lookup every /coach/client-plan call created another row for
            # the same person, filling the coach's roster with duplicates.
            profile = session.query(CoachClient).filter(
                CoachClient.owner_user_id == owner_user_id,
                CoachClient.client_name == str(payload.get("client_name") or "Demo Client"),
            ).order_by(CoachClient.created_at.asc()).first()
        if profile is None:
            profile = CoachClient(id=str(uuid.uuid4()), owner_user_id=owner_user_id, created_at=utc_now(), updated_at=utc_now())
            session.add(profile)
        profile.client_name = str(payload.get("client_name") or "Demo Client")
        profile.goal = str(payload.get("goal") or "general fitness")
        profile.diet = str(payload.get("diet") or "balanced")
        profile.allergies_json = json.dumps(payload.get("allergies") or [])
        profile.days_per_week = int(payload.get("days_per_week") or 3)
        profile.equipment_json = json.dumps(payload.get("equipment") or [])
        profile.calorie_target = int(payload.get("calorie_target") or 2200)
        profile.updated_at = utc_now()
        session.flush()
        result = _client_dict(profile)
    return result


def save_client_plan(request: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    owner_user_id = str(request.get("owner_user_id") or DEMO_USER_ID)
    profile = create_or_update_client(request, owner_user_id)
    record = save_plan_for_client(profile["id"], plan, owner_user_id)
    return {"profile_id": profile["id"], "plan_id": record["id"], "saved_at": record["created_at"]}


def list_clients(owner_user_id: str = DEMO_USER_ID) -> list[dict[str, Any]]:
    ensure_user(owner_user_id)
    with session_scope() as session:
        profiles = session.query(CoachClient).filter(CoachClient.owner_user_id == owner_user_id).order_by(CoachClient.updated_at.desc()).all()
        return [_client_dict(profile) for profile in profiles]


def get_client(client_id: str, owner_user_id: str = DEMO_USER_ID) -> dict[str, Any] | None:
    with session_scope() as session:
        profile = _owned_client(session, client_id, owner_user_id)
        return _client_dict(profile) if profile else None


def save_plan_for_client(client_id: str, plan: dict[str, Any], owner_user_id: str = DEMO_USER_ID) -> dict[str, Any]:
    plan_id = str(uuid.uuid4())
    now = utc_now()
    with session_scope() as session:
        if _owned_client(session, client_id, owner_user_id) is None:
            raise ClientNotFound("Client profile not found.")
        session.add(ClientPlanRecord(id=plan_id, client_id=client_id, payload_json=json.dumps(plan), created_at=now))
    return {"id": plan_id, "client_id": client_id, "plan": plan, "created_at": now.isoformat()}


def get_client_plans(client_id: str, owner_user_id: str = DEMO_USER_ID) -> list[dict[str, Any]]:
    with session_scope() as session:
        if _owned_client(session, client_id, owner_user_id) is None:
            raise ClientNotFound("Client profile not found.")
        records = session.query(ClientPlanRecord).filter(ClientPlanRecord.client_id == client_id).order_by(ClientPlanRecord.created_at.desc()).all()
        return [{"id": row.id, "client_id": row.client_id, "plan": _json(row.payload_json, {}), "created_at": row.created_at.isoformat()} for row in records]


def save_copilot_message(user_id: str, role: str, content: str, intent: str | None, context: dict[str, Any]) -> str:
    ensure_user(user_id)
    message_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(CopilotMessage(id=message_id, user_id=user_id, role=role, content=content, intent=intent, context_json=json.dumps(context), created_at=utc_now()))
    return message_id


def client_exists(client_id: str, owner_user_id: str = DEMO_USER_ID) -> bool:
    with session_scope() as session:
        return _owned_client(session, client_id, owner_user_id) is not None


def save_checkout(*, client_id: str | None, retailer: str, status: str, items: list[dict[str, Any]], checkout_url: str | None, checkout_id: str | None = None, user_id: str | None = None, provider: str = "generic") -> dict[str, Any]:
    if user_id:
        ensure_user(user_id)
    if client_id and not client_exists(client_id):
        # checkout_sessions.client_id is a foreign key: SQLite silently accepted a
        # dangling id, Postgres raised IntegrityError and returned a 500.
        raise ClientNotFound("Client profile not found.")
    record_id = checkout_id or str(uuid.uuid4())
    now = utc_now()
    with session_scope() as session:
        session.add(CheckoutRecord(id=record_id, user_id=user_id, client_id=client_id, provider=provider, status=status, items_json=json.dumps(items), checkout_url=checkout_url, created_at=now))
    return {"checkout_id": record_id, "user_id": user_id, "client_id": client_id, "checkout_provider": provider, "retailer": retailer, "status": status, "item_count": len(items), "items": items, "checkout_url": checkout_url, "created_at": now.isoformat()}


def get_checkout(checkout_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(CheckoutRecord, checkout_id)
        if row is None:
            return None
        items = _json(row.items_json, [])
        return {"checkout_id": row.id, "user_id": row.user_id, "client_id": row.client_id, "checkout_provider": row.provider, "status": row.status, "item_count": len(items), "items": items, "checkout_url": row.checkout_url, "created_at": row.created_at.isoformat()}


def load_user_memory(user_id: str = DEMO_USER_ID) -> dict[str, Any]:
    plans = get_user_plans(user_id, limit=3)
    with session_scope() as session:
        rows = session.query(CopilotMessage).filter(CopilotMessage.user_id == user_id).order_by(CopilotMessage.created_at.desc()).limit(6).all()
        messages = [{"role": row.role, "content": row.content[:4000], "intent": row.intent} for row in reversed(rows)]
    return {"profile": get_profile(user_id), "bag": [item["product"] for item in get_bag(user_id)], "recent_plans": plans, "recent_scans": recent_scans(user_id, limit=3), "recent_messages": messages}
