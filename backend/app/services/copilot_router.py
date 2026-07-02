from __future__ import annotations

from typing import Any


def detect_intent(message: str) -> str:
    text = message.lower()
    if any(word in text for word in ["compare", "versus", " vs "]):
        return "compare_products"
    if any(word in text for word in ["bag", "cart", "swap", "optimize"]):
        return "optimize_bag"
    if any(word in text for word in ["recipe", "cook", "pantry", "ingredients I have"]):
        return "recipe"
    if any(word in text for word in ["meal plan", "weekly plan", "what should i eat"]):
        return "meal_plan"
    if any(word in text for word in ["why", "score", "healthy", "product"]):
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
