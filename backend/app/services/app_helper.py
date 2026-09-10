"""Read-only, screen-aware guidance. No arbitrary navigation or write tools."""
import re
from typing import Literal

from pydantic import Field

from app.domain.models import DomainModel
from app.services.product_intelligence import explain_product

Screen = Literal["groceries", "product_detail", "comparison", "bag", "scan", "food_logging", "tracker"]
GUIDE_VERSION = "recording-review-2026-09-09"


class HelperRequest(DomainModel):
    message: str = Field(min_length=1, max_length=2000)
    screen: Screen = "product_detail"
    product_id: str | None = Field(default=None, max_length=150)
    bag_product_ids: list[str] = Field(default_factory=list, max_length=50)
    goal: str = Field(default="balanced nutrition", max_length=100)
    allergies: list[str] = Field(default_factory=list, max_length=30)
    # An external score has no known algorithm. Never explain it using ours.
    score_source: Literal["agent_catalog", "mobile_app"] = "agent_catalog"


GUIDES = {
    "groceries": ("Find products that fit your preferences", [
        "Search for a product or browse an aisle.",
        "Use Diet Type, Allergies, or Macros to narrow the list; review the filter and tap Apply.",
        "Open a product to review its ingredients and nutrition. A filter is not an allergen-safety guarantee."]),
    "product_detail": ("Understand a product before choosing it", [
        "Review Ingredients, Nutrition Facts, and Product Details.",
        "Check the serving size before comparing nutrition amounts.",
        "Ask for an explanation or compare an alternative. The mobile app's score formula is not connected yet."]),
    "comparison": ("Compare the trade-offs", [
        "Choose two products and check their serving sizes.",
        "Compare protein, sugar, fiber, and the score using the same declared basis.",
        "Check allergy and diet compatibility before choosing an alternative."]),
    "bag": ("Review before you swap", [
        "Choose the products to include in your bag review.",
        "Preview suggested alternatives and the before-and-after score.",
        "Review each swap before applying it. This helper does not change your bag or place orders."]),
    "scan": ("Get a clearer scan", [
        "Open Scan, then choose Scan Barcode, Snap Food, or Describe Food in the mobile app.",
        "For a barcode, keep the code visible and steady. For a meal description, include ingredients and quantities.",
        "Review the identified food, portion, and nutrition before logging. Use Fix result or edit ingredients if needed."]),
    "food_logging": ("Review, then log", [
        "Check the identified food and adjust serving size and quantity.",
        "Log Food is the entry point for recording intake; Save Food is a separate save action.",
        "Check My Tracker afterward. Exact save behavior and destinations need confirmation from the mobile app developer."]),
    "tracker": ("Understand your tracker", [
        "Review your configured goal and calorie or macro targets.",
        "Check logged foods and portions if totals look unexpected.",
        "The helper is not connected to your mobile tracker data and cannot report your actual progress yet."]),
}


def action(action_id, label, kind="navigate", requires_confirmation=False):
    return {"id": action_id, "label": label, "kind": kind, "requires_confirmation": requires_confirmation}


def helper_reply(request: HelperRequest, graph) -> dict:
    message = request.message.strip().lower()
    if not message:
        raise ValueError("Enter a question for the helper")
    response = {
        "intent": "app_guidance", "response": "", "steps": [], "actions": [],
        "tool_result": {}, "limitations": [], "errors": [],
        "context_used": {"screen": request.screen, "product_id": request.product_id,
                         "goal": request.goal, "score_source": request.score_source},
        "guide_version": GUIDE_VERSION,
    }
    # No write/commerce execution exists in this helper, even if prompted.
    if re.search(r"\b(log|save|apply|checkout|purchase|buy|order)\b", message) and not re.search(r"\b(how|where|difference)\b", message):
        response.update(intent="action_preview", response="I can guide you to review this action, but I have not changed your bag, logged food, saved anything, or placed an order.",
                        actions=[action("review_action", "Review in the app", "review", True)])
        return response
    guidance = re.search(r"\b(how|where)\b.*\b(use|scan|filter|log|save|find|button|tracker|navigate)\b|\b(help me use|guide me|what can i do)\b", message)
    if not guidance and re.search(r"\b(score|explain|compare|alternative|swap|optimize|optimise)\b", message):
        if request.score_source == "mobile_app":
            response.update(intent="score_source_unavailable", response="The mobile app's scoring formula is not connected. I cannot explain its displayed number using the agent's separate score.",
                            steps=["Review the product's nutrition and ingredients.", "Connect the mobile score and its contributing factors before requesting an exact explanation."],
                            limitations=["A nutrition score is not a percentage probability of safety or a medical assessment."])
            return response
        intent = "optimize_bag" if re.search(r"\b(bag|optimize|optimise)\b", message) else "find_swap" if re.search(r"\b(compare|alternative|swap)\b", message) else "explain_product"
        if intent != "optimize_bag" and not request.product_id:
            response.update(intent="needs_product", response="Choose a known catalog product first so I can explain real nutrition and score factors.",
                            actions=[action("open_explain", "Choose a product")])
            return response
        if intent == "optimize_bag" and not request.bag_product_ids:
            response.update(intent="needs_bag", response="Add known catalog products before requesting a bag review.", actions=[action("open_bag", "Review bag")])
            return response
        routed_message = {"explain_product": "Explain this product score", "find_swap": "Find a better alternative", "optimize_bag": "Optimize my bag"}[intent]
        result = graph.run({"message": routed_message, "product_id": request.product_id,
                            "bag_product_ids": request.bag_product_ids,
                            "user_profile": {"primary_goal": request.goal, "allergies": request.allergies}})
        response.update(intent=intent, response=result["response"], tool_result=result["tool_result"], errors=result["errors"],
                        limitations=["These are agent catalog scores, not the mobile app's existing scores.",
                                     "Only allergies entered in this helper were used; the saved mobile profile is not connected.",
                                     "A score does not guarantee safety; check the source and allergen information."])
        current = result["tool_result"].get("current_product")
        if current and not result["errors"]:
            # Reuse the exact neutral-goal function that calculates the base score,
            # not the goal-adjusted legacy explanation of a different number.
            explanation = explain_product(current["product"], "balanced nutrition")
            response["tool_result"]["base_explanation"] = {
                "score": explanation["score"], "positives": explanation["positives"],
                "cautions": explanation["cautions"],
            }
        if not result["errors"]:
            response["actions"] = [action("open_compare", "Compare products"), action("open_bag", "Review bag")]
        return response
    guide_screen = request.screen
    if guidance:
        if re.search(r"\b(scan|barcode)\b", message):
            guide_screen = "scan"
        elif re.search(r"\b(log|save)\b", message):
            guide_screen = "food_logging"
        elif re.search(r"\b(filter|filters)\b", message):
            guide_screen = "groceries"
        elif re.search(r"\b(tracker)\b", message):
            guide_screen = "tracker"
    title, steps = GUIDES[guide_screen]
    response.update(response=title, steps=steps, actions=[action("open_scan", "Open scanner"), action("open_explain", "Review product")],
                    limitations=["Mobile guidance is based on the supplied recording, not live access to the mobile app."])
    return response
