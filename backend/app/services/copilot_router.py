from __future__ import annotations

from typing import Any


def detect_intent(message: str) -> str:
    text = message.lower()
    if any(phrase in text for phrase in ["prepare checkout", "checkout", "buy this list", "send to retailer"]):
        return "prepare_checkout"
    if any(phrase in text for phrase in ["client plan", "trainer plan", "coach plan", "plan for my client", "trainer client"]):
        return "client_plan"
    if any(phrase in text for phrase in ["workout plan", "training plan", "exercise plan", "gym plan", "weekly split"]):
        return "workout_plan"
    if any(phrase in text for phrase in ["shopping list", "grocery list", "groceries", "what should i buy"]):
        return "shopping_list"
    if any(word in text for word in ["compare", "versus", " vs ", "better product"]):
        return "compare_products"
    if any(word in text for word in ["bag", "cart", "swap", "optimize"]):
        return "optimize_bag"
    if any(word in text for word in ["recipe", "cook", "pantry", "ingredients i have", "make with"]):
        return "recipe"
    if any(word in text for word in ["meal plan", "meal-plan", "weekly plan", "what should i eat", "days of meals", "day plan"]):
        return "meal_plan"
    if any(word in text for word in ["why", "score", "healthy", "product", "nutrition label"]):
        return "explain_product"
    return "general_chat"


def build_context_prompt(message: str, context: dict[str, Any] | None = None) -> str:
    context = context or {}
    parts = [f"User message: {message}"]
    if context.get("goal"):
        parts.append(f"User goal: {context['goal']}")
    if context.get("product"):
        parts.append(f"Current product context: {context['product']}")
    if context.get("bag"):
        parts.append(f"Current bag: {context['bag']}")
    if context.get("preferences"):
        parts.append(f"Preferences and restrictions: {context['preferences']}")
    return "\n".join(parts)
