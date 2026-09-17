from __future__ import annotations

import os
import uuid
from typing import Any

from app.services.persistence import DEMO_USER_ID, get_bag, save_checkout


def _item(value: Any, category: str = "other") -> dict[str, Any]:
    if isinstance(value, str):
        return {"name": value, "quantity": "1", "category": category}
    if isinstance(value, dict):
        return {
            "name": str(value.get("name") or value.get("item") or "Item"),
            "quantity": str(value.get("quantity") or "1"),
            "category": str(value.get("category") or category),
        }
    return {"name": "Item", "quantity": "1", "category": category}


def normalize_checkout_items(request: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(request.get("items"), list) and request["items"]:
        return [_item(value) for value in request["items"]]
    shopping_list = request.get("shopping_list") or {}
    categories = shopping_list.get("categories") if isinstance(shopping_list, dict) else None
    if isinstance(categories, dict):
        return [_item(value, category) for category, values in categories.items() for value in (values if isinstance(values, list) else [])]
    strategy = request.get("shopping_strategy") or {}
    if isinstance(strategy, dict) and isinstance(strategy.get("starter_items"), list):
        return [_item(value) for value in strategy["starter_items"]]
    return []


def prepare_checkout(request: dict[str, Any]) -> dict[str, Any]:
    items = normalize_checkout_items(request)
    if not items:
        raise ValueError("A shopping list or at least one checkout item is required.")
    retailer = str(request.get("retailer") or "preferred retailer")
    template = os.getenv("COMMERCE_CHECKOUT_URL_TEMPLATE")
    provisional_id = str(uuid.uuid4())
    checkout_url = template.format(checkout_id=provisional_id, retailer=retailer) if template else None
    status = "retailer_handoff_ready" if checkout_url else "prepared"
    result = save_checkout(client_id=request.get("client_id"), retailer=retailer, status=status, items=items, checkout_url=checkout_url, checkout_id=provisional_id, user_id=request.get("user_id"), provider="generic")
    result["next_action"] = "Open the configured retailer checkout." if result.get("checkout_url") else "Connect COMMERCE_CHECKOUT_URL_TEMPLATE to hand this basket to a retailer."
    return result


def prepare_instacart_checkout(request: dict[str, Any]) -> dict[str, Any]:
    user_id = str(request.get("user_id") or DEMO_USER_ID)
    items = normalize_checkout_items(request)
    if not items:
        items = [_item({**entry["product"], "quantity": entry.get("quantity", 1)}) for entry in get_bag(user_id)]
    if not items:
        raise ValueError("Add at least one item to the persistent bag before checkout.")
    checkout_url = "https://www.instacart.com/store/partner_recipe_mock"
    saved = save_checkout(
        client_id=request.get("client_id"), user_id=user_id, retailer="Instacart", provider="instacart",
        status="mock_ready", items=items, checkout_url=checkout_url,
    )
    return {
        "checkout_provider": "instacart",
        "status": "mock_ready",
        "checkout_url": checkout_url,
        "items": items,
        "checkout_id": saved["checkout_id"],
    }
