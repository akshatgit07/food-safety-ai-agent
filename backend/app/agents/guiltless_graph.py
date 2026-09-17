from typing import Any, Callable, TypedDict
import logging
from copy import deepcopy

from langgraph.graph import END, START, StateGraph

from app.agent.router import CopilotRouter, TOOL_CONTEXT_ERRORS
from app.domain.models import DailyNutritionState, Product, SCORE_VERSION, UserProfile
from app.services.copilot_router import detect_intent
from app.services.personalized_tools import product_decision
from app.services.product_lookup import ProductLookup
from app.services.product_retriever import CandidateRetriever
from app.services.result_validator import validate_result, validate_composition
from app.services.g_personal import normalize

PRODUCT_INTENTS = {"explain_product", "compare_products", "optimize_bag", "find_swap"}
BRANCHES = PRODUCT_INTENTS | {"meal_plan", "shopping_list", "workout_plan", "general_chat"}


class GuiltlessState(TypedDict, total=False):
    message: str
    request: dict[str, Any]
    user_profile: UserProfile
    daily_nutrition_state: DailyNutritionState
    current_product: Product | None
    bag: list[Product]
    intent: str
    retrieved_candidates: list[dict]
    tool_result: dict
    response: str
    grounding: dict
    suggested_actions: list[str]
    errors: list[str]


class GuiltlessGraph:
    def __init__(self, lookup: ProductLookup, retriever: CandidateRetriever, router: CopilotRouter,
                 memory_loader: Callable[[str], dict], validator: Callable = validate_result,
                 composer: Callable[[dict], dict] | None = None):
        self.lookup, self.retriever, self.router = lookup, retriever, router
        self.memory_loader, self.validator = memory_loader, validator
        self.composer = composer
        graph = StateGraph(GuiltlessState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("route_intent", self._route_intent)
        for name in sorted(BRANCHES):
            graph.add_node(name, self._tool)
            graph.add_edge(name, "validate_result")
        graph.add_node("validate_result", self._validate)
        graph.add_node("compose_response", self._compose)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "route_intent")
        graph.add_conditional_edges("route_intent", lambda s: s["intent"], {name: name for name in BRANCHES})
        graph.add_edge("validate_result", "compose_response")
        graph.add_edge("compose_response", END)
        self.graph = graph.compile()

    def run(self, request: dict) -> dict:
        state = self.graph.invoke({"message": request["message"], "request": request, "errors": [], "retrieved_candidates": []},
                                  config={"run_name": "guiltless.graph.v2", "tags": ["copilot-v2"], "metadata": {"score_version": SCORE_VERSION}})
        approved = {"intent": state["intent"], "response": state["response"], "grounding": state["grounding"],
                "confidence": 0 if state["errors"] else self._confidence(state),
                "suggested_actions": state["suggested_actions"], "tool_result": state["tool_result"],
                "errors": state["errors"], "context_used": {"user_profile": state["user_profile"].model_dump(),
                "daily_nutrition_state": state["daily_nutrition_state"].model_dump(mode="json")}}
        if self.composer and not approved["errors"]:
            proposed = self.composer(deepcopy(approved))
            errors = validate_composition(proposed, approved)
            if errors:
                logging.getLogger(__name__).warning("Composition validation failed: %s", errors)
                approved.update(response="I could not validate the proposed explanation.", tool_result={}, confidence=0, errors=errors)
                approved["grounding"] = {**approved["grounding"], "product_ids": [], "data_sources": []}
        return approved

    def _load_context(self, state: GuiltlessState) -> dict:
        req = state["request"]
        saved = {}
        memory = {}
        if req.get("load_memory"):
            memory = self.memory_loader(req.get("user_id", "demo-user"))
            p = memory.get("profile", {})
            saved = {"primary_goal": p.get("goal", "balanced nutrition"), "allergies": p.get("allergies", []),
                     "dietary_preferences": [p["diet"]] if p.get("diet") else [],
                     "calorie_target": p.get("calorie_target"), "dislikes": p.get("disliked_foods", []),
                     "preferred_stores": [p["preferred_store"]] if p.get("preferred_store") else []}
        profile = UserProfile.model_validate({**saved, **req.get("user_profile", {}), "user_id": req.get("user_id", "demo-user")})
        current = None
        errors = []
        if req.get("barcode") is not None or req.get("product_id") is not None:
            current = self.lookup.find(barcode=req.get("barcode"), product_id=req.get("product_id"))
            if current is None:
                errors.append("Product identifier was not found in the catalog")
        bag_ids = req.get("bag_product_ids")
        if bag_ids is None:
            bag_ids = [p["product_id"] for p in memory.get("bag", []) if p.get("product_id")]
        bag = []
        for pid in bag_ids:
            product = self.lookup.find(product_id=pid)
            if product is None:
                errors.append(f"Bag product not found: {pid}")
            else:
                bag.append(product)
        planning = dict(req.get("planning_context", {}))
        saved_meals = memory.get("recent_plans", {}).get("meal_plans", [])
        if saved_meals:
            planning.setdefault("meal_plan", saved_meals[0]["plan"])
        return {"request": {**req, "planning_context": planning}, "user_profile": profile, "daily_nutrition_state": DailyNutritionState.model_validate(req.get("daily_nutrition_state", {})),
                "current_product": current, "bag": bag, "errors": errors}

    def _route_intent(self, state: GuiltlessState) -> dict:
        message = state["message"].lower()
        intent = "find_swap" if any(word in message for word in ("swap", "alternative", "replace")) and "bag" not in message else detect_intent(message)
        if intent not in BRANCHES:
            intent = "general_chat"
        # The keyword router misses natural phrasings ("explain", "is this good
        # for me?"), which returned an ungrounded canned menu even though the
        # caller had already resolved an exact product. An explicit identifier is
        # a stronger signal of intent than the wording of the question.
        if intent == "general_chat" and state.get("current_product") is not None:
            intent = "explain_product"
        return {"intent": intent}

    def _tool(self, state: GuiltlessState) -> dict:
        if state["errors"]:
            return {"tool_result": {}}
        try:
            if state["intent"] in PRODUCT_INTENTS:
                result = product_decision(state["intent"], state["current_product"], state["bag"], state["user_profile"], state["daily_nutrition_state"], self.retriever, state["message"])
            else:
                profile = state["user_profile"]
                # General chat has no ungrounded product recommendations in v2.
                if state["intent"] == "general_chat":
                    result = {"summary": "Select a product to explain its score, find a compatible swap, or ask for a workout plan."}
                else:
                    hard_diets = [p for p in profile.dietary_preferences if normalize(p) not in {"balanced", "no restriction", "high protein"}]
                    if state["intent"] in {"meal_plan", "shopping_list"} and (profile.allergies or hard_diets or profile.ingredients_to_avoid):
                        raise ValueError("Constrained meal ingredients need verified catalog coverage before this workflow can recommend a plan")
                    context = {**state["request"].get("planning_context", {}), "goal": profile.primary_goal,
                               "allergies": profile.allergies, "calorie_target": profile.calorie_target}
                    result = self.router._dispatch(state["intent"], state["message"], context)
            return {"tool_result": result, "retrieved_candidates": result.get("ranked_alternatives", [])}
        except TOOL_CONTEXT_ERRORS as exc:
            return {"tool_result": {}, "errors": [str(exc)]}

    def _validate(self, state: GuiltlessState) -> dict:
        if self.validator and not state["errors"]:
            errors = self.validator(state["tool_result"], state["user_profile"], state["daily_nutrition_state"], self.lookup)
            if errors:
                logging.getLogger(__name__).warning("Product result validation failed: %s", errors)
                return {"errors": errors, "tool_result": {}}
        return {}

    @staticmethod
    def _records(value: Any) -> list[dict]:
        if isinstance(value, dict):
            found = [value] if "product_id" in value and "provenance" in value else []
            return found + [p for child in value.values() for p in GuiltlessGraph._records(child)]
        if isinstance(value, list):
            return [p for child in value for p in GuiltlessGraph._records(child)]
        return []

    @classmethod
    def _confidence(cls, state: GuiltlessState) -> float:
        records = cls._records(state["tool_result"])
        return min((min(p["provenance"]["confidence"], 0.5 if not p["provenance"]["verified"] else 1) for p in records), default=0.2)

    def _compose(self, state: GuiltlessState) -> dict:
        result = state["tool_result"]
        records = self._records(result)
        grounding = {"product_ids": sorted({p["product_id"] for p in records}), "score_version": SCORE_VERSION,
                     "data_sources": sorted({p["provenance"]["source"] for p in records}),
                     "method": "deterministic catalog scoring; retrieval method reported per alternative"}
        if state["errors"]:
            response = "I could not validate a recommendation. Check the product selection and constraints."
        elif "current_product" in result:
            current = result["current_product"]
            score = current["scoring"]
            response = f"{current['product']['name']}: base score {score['base_score']:g}. "
            response += f"G-Personal score {score['personal_score']:g}." if score["compatibility"] == "compatible" else "Incompatible with your constraints."
            if state["intent"] == "find_swap":
                response += f" Found {len(result.get('ranked_alternatives', []))} compatible improving alternatives."
        elif state["intent"] == "optimize_bag":
            response = f"Catalog swaps change the bag base score from {result['current_score']:g} to {result['optimized_score']:g}. Review each item's compatibility before applying."
        elif state["intent"] == "compare_products":
            response = "Compared catalog products; only compatible products are eligible for recommendation."
        else:
            response = result.get("response", result.get("summary", "Plan prepared."))
            grounding["data_sources"] = ["existing_planning_service"] if state["intent"] != "general_chat" else []
        return {"response": response, "grounding": grounding,
                "suggested_actions": ["explain_score", "compare_alternatives", "optimize_bag", "build_workout_plan"]}
