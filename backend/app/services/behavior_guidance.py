"""Privacy-conscious behavior memory and proactive in-app guidance."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
import json
import uuid
from typing import Any, Literal

from pydantic import Field

from app.db import AppBehaviorEvent, session_scope, utc_now
from app.domain.models import DomainModel
from app.services.persistence import ensure_user, get_profile


EventType = Literal[
    "screen_viewed", "product_scanned", "health_score_opened", "product_added_to_bag",
    "comparison_started", "comparison_abandoned", "meal_plan_viewed", "suggestion_dismissed",
    "suggestion_accepted",
]
GuideScreen = Literal["groceries", "product_detail", "comparison", "bag", "scan", "food_logging", "tracker"]


class AppEventRequest(DomainModel):
    event_type: EventType
    screen: GuideScreen
    product_id: str | None = Field(default=None, max_length=150)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProactiveContext(DomainModel):
    screen: GuideScreen
    product_id: str | None = Field(default=None, max_length=150)
    product_name: str | None = Field(default=None, max_length=200)
    product_score: int | None = Field(default=None, ge=0, le=100)
    bag_product_ids: list[str] = Field(default_factory=list, max_length=50)


def record_event(user_id: str, request: AppEventRequest) -> dict[str, Any]:
    ensure_user(user_id)
    event_id = str(uuid.uuid4())
    # Metadata is deliberately bounded so this endpoint cannot become a raw telemetry dump.
    encoded = json.dumps(request.metadata, default=str)
    if len(encoded) > 4000:
        raise ValueError("Event metadata must be 4 KB or less")
    now = utc_now()
    with session_scope() as session:
        session.add(AppBehaviorEvent(id=event_id, user_id=user_id, event_type=request.event_type,
                                     screen=request.screen, product_id=request.product_id,
                                     metadata_json=encoded, created_at=now))
    return {"accepted": True, "event_id": event_id, "recorded_at": now.isoformat()}


def recent_events(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_user(user_id)
    with session_scope() as session:
        rows = (session.query(AppBehaviorEvent).filter(AppBehaviorEvent.user_id == user_id)
                .order_by(AppBehaviorEvent.created_at.desc()).limit(limit).all())
        return [{"event_type": row.event_type, "screen": row.screen, "product_id": row.product_id,
                 "metadata": json.loads(row.metadata_json or "{}"), "created_at": row.created_at.isoformat()}
                for row in rows]


def behavior_summary(user_id: str) -> dict[str, Any]:
    events = recent_events(user_id)
    return {
        "event_count": len(events),
        "top_screens": [screen for screen, _ in Counter(e["screen"] for e in events).most_common(3)],
        "recent_event_types": [e["event_type"] for e in events[:5]],
        "frequent_products": [product for product, _ in Counter(e["product_id"] for e in events if e["product_id"]).most_common(3)],
    }


def proactive_suggestion(user_id: str, context: ProactiveContext) -> dict[str, Any]:
    events = recent_events(user_id)
    profile = get_profile(user_id)
    recent_types = [event["event_type"] for event in events[:12]]

    candidates: list[dict[str, Any]] = []
    if context.screen == "product_detail" and context.product_id:
        candidates.append({"id": f"explain:{context.product_id}", "intent": "explain_health_score",
                           "message": f"Want me to explain what drives {context.product_name or 'this product'}’s health score for your {profile['goal']} goal?",
                           "action": {"id": "open_explain", "label": "Explain this score", "kind": "navigate", "requires_confirmation": False},
                           "reason": "You are viewing a product with score context available."})
    if context.screen == "comparison" and "comparison_abandoned" in recent_types:
        candidates.insert(0, {"id": "resume-comparison", "intent": "compare_alternatives",
                              "message": "You left a comparison unfinished. I can help compare the nutrition trade-offs.",
                              "action": {"id": "open_compare", "label": "Resume comparison", "kind": "navigate", "requires_confirmation": False},
                              "reason": "A recent comparison was not completed."})
    bag_activity = recent_types.count("product_added_to_bag")
    if context.screen == "bag" and (len(context.bag_product_ids) >= 2 or bag_activity >= 2):
        candidates.insert(0, {"id": "optimize-current-bag", "intent": "optimize_bag",
                              "message": "Your bag has enough products for a nutrition review. Want to preview healthier swaps?",
                              "action": {"id": "open_bag", "label": "Optimize my bag", "kind": "navigate", "requires_confirmation": False},
                              "reason": "Multiple bag products are available to compare."})
    if context.screen == "scan" and recent_types.count("screen_viewed") >= 3:
        candidates.append({"id": "scan-help", "intent": "app_guidance",
                           "message": "Need help getting a clean scan? I can walk you through barcode or label capture.",
                           "action": {"id": "open_scan", "label": "Show scan tips", "kind": "navigate", "requires_confirmation": False},
                           "reason": "You have recently navigated through several app screens."})

    cutoff = utc_now() - timedelta(hours=24)
    dismissed = set()
    with session_scope() as session:
        rows = session.query(AppBehaviorEvent).filter(AppBehaviorEvent.user_id == user_id,
                                                       AppBehaviorEvent.event_type == "suggestion_dismissed",
                                                       AppBehaviorEvent.created_at >= cutoff).all()
        for row in rows:
            dismissed.add(json.loads(row.metadata_json or "{}").get("suggestion_id"))
    suggestion = next((item for item in candidates if item["id"] not in dismissed), None)
    return {"show": suggestion is not None, "suggestion": suggestion,
            "context_used": {"screen": context.screen, "product_id": context.product_id,
                             "goal": profile["goal"], "bag_item_count": len(context.bag_product_ids)},
            "behavior_summary": behavior_summary(user_id)}
