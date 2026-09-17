from __future__ import annotations

from typing import Any


ACTION_ORDER = [
    "explain_score",
    "compare_alternatives",
    "optimize_bag",
    "build_meal_plan",
    "build_workout_plan",
    "create_client_plan",
    "add_to_shopping_list",
    "prepare_checkout",
]


def recommend_actions(context: dict[str, Any] | None = None, intent: str | None = None, limit: int = 6) -> list[str]:
    context = context or {}
    recommended: list[str] = []

    def add(action: str) -> None:
        if action not in recommended:
            recommended.append(action)

    if context.get("product"):
        add("explain_score")
        add("compare_alternatives")
    if context.get("bag") or context.get("items"):
        add("optimize_bag")
    if context.get("meal_plan"):
        add("add_to_shopping_list")
    if context.get("shopping_list"):
        add("prepare_checkout")
    if context.get("client_name") or context.get("coach_mode") or intent == "client_plan":
        add("create_client_plan")

    intent_next = {
        "explain_product": ["compare_alternatives", "optimize_bag"],
        "compare_products": ["optimize_bag", "build_meal_plan"],
        "optimize_bag": ["add_to_shopping_list", "prepare_checkout"],
        "meal_plan": ["add_to_shopping_list", "build_workout_plan"],
        "workout_plan": ["build_meal_plan", "create_client_plan"],
        "client_plan": ["add_to_shopping_list", "prepare_checkout"],
        "shopping_list": ["prepare_checkout", "optimize_bag"],
        "prepare_checkout": ["optimize_bag", "create_client_plan"],
    }
    for action in intent_next.get(intent or "", []):
        add(action)
    for action in ACTION_ORDER:
        add(action)
    return recommended[: max(1, min(limit, len(ACTION_ORDER)))]
