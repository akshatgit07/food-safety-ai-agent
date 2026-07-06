from __future__ import annotations

import re
from typing import Any, Callable, Optional

from app.services.bag_optimizer import optimize_bag
from app.services.action_recommender import recommend_actions
from app.services.coach_planner import build_client_plan
from app.services.commerce import prepare_checkout
from app.services.copilot_router import build_context_prompt, detect_intent
from app.services.product_intelligence import compare_products, explain_product
from app.services.workout_planner import build_workout_plan

AiRunner = Callable[[str, str], str]
MealPlanTool = Callable[[dict[str, Any]], Any]
ShoppingListTool = Callable[[Any, int], Any]


class CopilotRouter:
    """Small, deployable intent router with direct internal tool calls."""

    def __init__(
        self,
        ai_runner: Optional[AiRunner] = None,
        meal_plan_tool: Optional[MealPlanTool] = None,
        shopping_list_tool: Optional[ShoppingListTool] = None,
    ) -> None:
        self.ai_runner = ai_runner
        self.meal_plan_tool = meal_plan_tool
        self.shopping_list_tool = shopping_list_tool

    def route(self, message: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        context = context or {}
        intent = detect_intent(message)
        try:
            result = self._dispatch(intent, message, context)
            return {
                "intent": intent,
                "response": result["response"],
                "suggested_actions": recommend_actions(context, intent),
                "tool_result": result.get("tool_result"),
                "mode": result.get("mode", "tool"),
            }
        except Exception:
            try:
                fallback = self._general_chat(message, context, routing_failed=True)
            except Exception:
                fallback = self._deterministic_chat(context, routing_failed=True)
            return {
                "intent": "general_chat",
                "response": fallback["response"],
                "suggested_actions": recommend_actions(context, "general_chat"),
                "tool_result": None,
                "mode": "routing_fallback",
            }

    def _dispatch(self, intent: str, message: str, context: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "explain_product": self._explain_product,
            "compare_products": self._compare_products,
            "optimize_bag": self._optimize_bag,
            "meal_plan": self._meal_plan,
            "workout_plan": self._workout_plan,
            "client_plan": self._client_plan,
            "prepare_checkout": self._prepare_checkout,
            "shopping_list": self._shopping_list,
            "recipe": self._recipe,
            "general_chat": self._general_chat,
        }
        return handlers[intent](message, context)

    def _prepare_checkout(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        request = {
            "client_id": context.get("client_id"),
            "retailer": context.get("retailer", "preferred retailer"),
            "shopping_list": context.get("shopping_list"),
            "shopping_strategy": context.get("shopping_strategy"),
            "items": context.get("items") or [],
        }
        result = prepare_checkout(request)
        return {
            "response": f"I prepared {result['item_count']} items for {result['retailer']} checkout.",
            "tool_result": result,
        }

    def _workout_plan(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        request = {
            "goal": self._goal(context),
            "days_per_week": self._as_int(context.get("days_per_week"), self._extract_days(message), 1, 7),
            "equipment": context.get("equipment") or ["bodyweight"],
            "experience_level": context.get("experience_level", "beginner"),
            "limitations": context.get("limitations") or [],
            "session_minutes": self._as_int(context.get("session_minutes"), 60, 20, 120),
        }
        result = build_workout_plan(request)
        return {"response": result["summary"], "tool_result": result}

    def _client_plan(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        request = {
            "client_name": context.get("client_name", "Demo Client"),
            "goal": self._goal(context),
            "diet": context.get("diet", "high protein"),
            "allergies": context.get("allergies") or [],
            "days_per_week": self._as_int(context.get("days_per_week"), self._extract_days(message), 1, 7),
            "equipment": context.get("equipment") or ["gym"],
            "calorie_target": self._as_int(context.get("calorie_target"), 2200, 800, 6000),
            "experience_level": context.get("experience_level", "beginner"),
            "limitations": context.get("limitations") or [],
            "session_minutes": self._as_int(context.get("session_minutes"), 60, 20, 120),
        }
        result = build_client_plan(request)
        return {
            "response": f"I created a connected nutrition, workout, and shopping plan for {result['client_name']}.",
            "tool_result": result,
        }

    def _explain_product(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        product = context.get("product")
        if not isinstance(product, dict):
            raise ValueError("Product context is required")
        result = explain_product(product, self._goal(context))
        return {
            "response": result["summary"],
            "suggested_actions": ["Compare these products", "Optimize my bag"],
            "tool_result": result,
        }

    def _compare_products(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        products = context.get("products")
        if not isinstance(products, list) or len(products) < 2:
            bag = context.get("bag")
            products = bag if isinstance(bag, list) else []
        if len(products) < 2:
            raise ValueError("At least two products are required")
        result = compare_products(products, self._goal(context))
        return {
            "response": result["recommendation"],
            "suggested_actions": ["Why is this product score low?", "Optimize my bag"],
            "tool_result": result,
        }

    def _optimize_bag(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        items = context.get("bag") or context.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Bag context is required")
        result = optimize_bag(items, self._goal(context))
        return {
            "response": result["summary"],
            "suggested_actions": ["Review suggested swaps", "Build me a 5 day meal plan"],
            "tool_result": result,
        }

    def _meal_plan(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.meal_plan_tool is None:
            raise RuntimeError("Meal plan tool is unavailable")
        request = {
            "days": self._extract_days(message),
            "goal": self._goal(context),
            "diet": context.get("diet", "no restriction"),
            "allergies": context.get("allergies", []),
            "calorie_target": context.get("calorie_target"),
            "meals_per_day": context.get("meals_per_day", 3),
        }
        result = self.meal_plan_tool(request)
        return {
            "response": self._summary(result, f"I built a {request['days']}-day meal plan for {request['goal']}."),
            "suggested_actions": ["Turn this into a shopping list", "Give me a recipe"],
            "tool_result": result,
        }

    def _shopping_list(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.shopping_list_tool is None or not context.get("meal_plan"):
            raise RuntimeError("A meal plan is required for the shopping-list tool")
        servings = self._as_int(context.get("servings"), 1, 1, 20)
        result = self.shopping_list_tool(context["meal_plan"], servings)
        return {
            "response": "I consolidated the meal plan into a categorized shopping list.",
            "suggested_actions": ["Optimize my bag", "Give me a recipe"],
            "tool_result": result,
        }

    def _recipe(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        if self.ai_runner is None:
            ingredients = self._ingredient_names(context)
            response = (
                f"Try a simple bowl using {', '.join(ingredients[:4])}. Add a whole grain, vegetables, and a protein-friendly sauce."
                if ingredients
                else "Add ingredients or products to your bag and I can turn them into a recipe."
            )
            return {
                "response": response,
                "suggested_actions": ["Optimize my bag", "Build me a 5 day meal plan"],
                "tool_result": {"ingredients_used": ingredients, "source": "deterministic_fallback"},
                "mode": "deterministic_fallback",
            }
        prompt = build_context_prompt(message, context)
        response = self.ai_runner(
            "Create one concise, practical recipe from the supplied context. Respect allergies and do not make medical claims.",
            prompt,
        )
        return {
            "response": response,
            "suggested_actions": ["Add ingredients to my shopping list", "Build me a meal plan"],
            "tool_result": {"recipe": response},
            "mode": "openai",
        }

    def _general_chat(
        self,
        message: str,
        context: dict[str, Any],
        routing_failed: bool = False,
    ) -> dict[str, Any]:
        if self.ai_runner is not None:
            response = self.ai_runner(
                "You are a concise, evidence-aware nutrition copilot. Use supplied context, avoid diagnosis, and suggest a practical next step.",
                build_context_prompt(message, context),
            )
            mode = "openai"
        else:
            return self._deterministic_chat(context, routing_failed)
        return {
            "response": response,
            "suggested_actions": ["Why is this product score low?", "Optimize my bag", "Build me a 5 day meal plan"],
            "tool_result": None,
            "mode": mode,
        }

    def _deterministic_chat(self, context: dict[str, Any], routing_failed: bool) -> dict[str, Any]:
        goal = self._goal(context)
        prefix = "I could not complete that tool request. " if routing_failed else ""
        return {
            "response": prefix + f"I can help with product scores, comparisons, bag swaps, meal plans, shopping lists, or recipes for {goal}.",
            "suggested_actions": ["Why is this product score low?", "Optimize my bag", "Build me a 5 day meal plan"],
            "tool_result": None,
            "mode": "deterministic_fallback",
        }

    @staticmethod
    def _goal(context: dict[str, Any]) -> str:
        return str(context.get("goal") or "balanced nutrition")

    @staticmethod
    def _extract_days(message: str) -> int:
        match = re.search(r"\b(\d{1,2})\s*[- ]?day", message.lower())
        return CopilotRouter._as_int(match.group(1) if match else None, 5, 1, 7)

    @staticmethod
    def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _summary(result: Any, default: str) -> str:
        return str(result.get("summary") or default) if isinstance(result, dict) else default

    @staticmethod
    def _ingredient_names(context: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for product in context.get("bag") or []:
            if isinstance(product, dict):
                names.extend(str(item) for item in product.get("ingredients") or [])
        return list(dict.fromkeys(names))
