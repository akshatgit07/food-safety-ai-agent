from __future__ import annotations

from typing import Any


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def explain_product(product: dict[str, Any], goal: str = "balanced nutrition") -> dict[str, Any]:
    nutrition = product.get("nutrition") or {}
    ingredients = [str(item).lower() for item in product.get("ingredients") or []]

    calories = _as_number(nutrition.get("calories"))
    protein = _as_number(nutrition.get("protein_g"))
    fiber = _as_number(nutrition.get("fiber_g"))
    sugar = _as_number(nutrition.get("sugar_g"))
    sodium = _as_number(nutrition.get("sodium_mg"))

    score = 60.0
    positives: list[str] = []
    cautions: list[str] = []

    if protein >= 15:
        score += 14
        positives.append(f"High protein ({protein:g} g)")
    elif protein >= 8:
        score += 7
        positives.append(f"Useful protein ({protein:g} g)")
    else:
        cautions.append("Low protein for a filling snack")

    if fiber >= 5:
        score += 10
        positives.append(f"Good fiber ({fiber:g} g)")
    elif fiber >= 3:
        score += 5
        positives.append(f"Some fiber ({fiber:g} g)")
    else:
        score -= 8
        cautions.append("Low fiber")

    if sugar <= 5:
        score += 8
        positives.append("Low sugar")
    elif sugar <= 10:
        cautions.append(f"Moderate sugar ({sugar:g} g)")
    else:
        score -= 14
        cautions.append(f"High sugar ({sugar:g} g)")

    if sodium > 500:
        score -= 10
        cautions.append(f"High sodium ({sodium:g} mg)")
    elif sodium <= 250:
        score += 4
        positives.append("Moderate sodium")

    processing_markers = [
        "corn syrup",
        "maltodextrin",
        "artificial flavor",
        "hydrogenated",
        "soy protein isolate",
    ]
    matched_markers = [marker for marker in processing_markers if any(marker in ingredient for ingredient in ingredients)]
    if matched_markers:
        score -= min(12, len(matched_markers) * 4)
        cautions.append("Contains highly processed ingredients")

    goal_lower = goal.lower()
    fit_reasons: list[str] = []
    if "muscle" in goal_lower or "protein" in goal_lower:
        if protein >= 15:
            fit_reasons.append("Fits a high-protein goal")
            score += 4
        else:
            fit_reasons.append("Protein is modest for a muscle-gain goal")
    if "weight" in goal_lower or "fat loss" in goal_lower:
        if calories <= 250 and sugar <= 10:
            fit_reasons.append("Reasonable calorie density for weight management")
        elif calories > 350:
            fit_reasons.append("Calorie dense for a snack")
            score -= 4

    score = int(max(0, min(100, round(score))))
    verdict = "Strong choice" if score >= 80 else "Reasonable option" if score >= 65 else "Okay occasionally" if score >= 50 else "Look for a better alternative"

    return {
        "product": {
            "name": product.get("name", "Unknown product"),
            "brand": product.get("brand"),
            "category": product.get("category"),
        },
        "score": score,
        "verdict": verdict,
        "positives": positives,
        "cautions": cautions,
        "goal": goal,
        "goal_fit": fit_reasons,
        "summary": _build_summary(product.get("name", "This product"), verdict, positives, cautions, goal),
        "recommended_actions": [
            "Compare with a healthier alternative",
            "Ask how it fits your goal",
            "Add the better option to your bag",
        ],
    }


def compare_products(products: list[dict[str, Any]], goal: str = "balanced nutrition") -> dict[str, Any]:
    explanations = [explain_product(product, goal) for product in products]
    ranked = sorted(explanations, key=lambda item: item["score"], reverse=True)
    winner = ranked[0] if ranked else None
    return {
        "goal": goal,
        "products": explanations,
        "winner": winner["product"] if winner else None,
        "recommendation": (
            f"{winner['product']['name']} is the better fit for {goal} with a score of {winner['score']}."
            if winner
            else "No products were supplied."
        ),
    }


def _build_summary(name: str, verdict: str, positives: list[str], cautions: list[str], goal: str) -> str:
    good = positives[0] if positives else "It does not have a standout nutrition advantage"
    watch = cautions[0] if cautions else "there are no major red flags from the supplied data"
    return f"{name}: {verdict}. {good}; however, {watch}. This assessment is personalized for {goal}."
