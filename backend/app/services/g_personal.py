"""Versioned demo scoring policy, never an LLM or clinical recommendation.

Base quality reuses the existing rubric with no user goal adjustment. Personal
factors apply to one declared serving. Missing targets add no target-based bonus.
"""
import re

from app.domain.models import DailyNutritionState, FactorImpact, GPersonalScore, Product, UserProfile
from app.services.product_intelligence import explain_product


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


ALLERGENS = {
    "milk": {"milk", "dairy", "whey", "casein", "cheese", "yogurt", "butter", "cream"},
    "peanut": {"peanut", "peanuts", "groundnut"},
    "tree nut": {"tree nut", "tree nuts", "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "hazelnut", "pistachio", "pecan"},
    "soy": {"soy", "soya", "soybean", "tofu", "edamame"},
    "wheat": {"wheat", "semolina", "spelt", "bulgur"},
    "gluten": {"gluten", "wheat", "barley", "rye", "malt", "spelt"},
    "egg": {"egg", "eggs", "albumin", "mayonnaise"},
    "fish": {"fish", "salmon", "tuna", "anchovy", "cod"},
    "shellfish": {"shellfish", "shrimp", "prawn", "crab", "lobster", "mussel", "clam", "oyster"},
    "sesame": {"sesame", "tahini"},
}


def contains(text: str, word: str) -> bool:
    return f" {normalize(word)} " in f" {normalize(text)} "


def aliases(value: str) -> set[str]:
    key = normalize(value)
    if key in {"nuts", "nut"}:
        return ALLERGENS["peanut"] | ALLERGENS["tree nut"]
    return next((terms for root, terms in ALLERGENS.items() if key == root or key in terms), {key})


def hard_constraint_failures(product: Product, profile: UserProfile) -> list[str]:
    failures = []
    text = " ".join(product.ingredients + product.allergens)
    for allergy in profile.allergies:
        if any(contains(text, term) for term in aliases(allergy)):
            failures.append(f"Allergy conflict: {allergy}")
    if profile.allergies and not product.allergen_info_complete:
        failures.append("Allergen information is incomplete; compatibility cannot be confirmed")
    for ingredient in profile.ingredients_to_avoid:
        if any(contains(text, term) for term in aliases(ingredient)):
            failures.append(f"Excluded ingredient: {ingredient}")
    if profile.ingredients_to_avoid and not product.ingredients:
        failures.append("Ingredient information is missing")
    flags = {normalize(flag) for flag in product.diet_flags}
    meat = {"beef", "chicken", "pork", "gelatin", "lamb", "bacon"} | ALLERGENS["fish"] | ALLERGENS["shellfish"]
    forbidden = {"vegan": meat | ALLERGENS["milk"] | ALLERGENS["egg"] | {"honey"},
                 "vegetarian": meat, "gluten free": ALLERGENS["gluten"], "dairy free": ALLERGENS["milk"]}
    for diet in profile.dietary_preferences:
        label = normalize(diet)
        if label in {"balanced", "no restriction", "high protein"}:
            continue
        if label not in flags or any(contains(text, term) for term in forbidden.get(label, set())):
            failures.append(f"Diet constraint not satisfied: {diet}")
    return failures


def base_score(product: Product) -> float:
    # Ignore caller-supplied scores: recompute from nutrition and ingredients.
    return float(explain_product(product.model_dump(), "balanced nutrition")["score"])


def score_product(product: Product, profile: UserProfile, daily: DailyNutritionState) -> GPersonalScore:
    base = base_score(product)
    failures = hard_constraint_failures(product, profile)
    if failures:
        return GPersonalScore(base_score=base, personal_score=None, compatibility="incompatible", hard_constraint_failures=failures)
    factors = []
    n = product.nutrition
    for name, target, consumed, amount, weight in (
        ("protein", profile.protein_target, daily.protein_consumed, n.protein_g, 12),
        ("carbs", profile.carb_target, daily.carbs_consumed, n.carbs_g, 4),
        ("fat", profile.fat_target, daily.fat_consumed, n.fat_g, 4),
        ("calories", profile.calorie_target, daily.calories_consumed, n.calories, 3),
    ):
        if target and amount:
            remaining = max(0, target - consumed)
            impact = weight * min(amount, remaining) / target
            excess = max(0, amount - remaining)
            impact -= min(weight / 2, weight * excess / target)
            factors.append(FactorImpact(factor=f"remaining_{name}", impact=round(impact, 3), reason=f"{remaining:g} remaining of {target:g}; serving provides {amount:g}"))
    for nutrient, target in sorted(profile.micronutrient_targets.items()):
        if target and nutrient in n.micronutrients:
            gap = max(0, target - daily.micronutrients_consumed.get(nutrient, 0))
            impact = 3 * min(gap, n.micronutrients[nutrient]) / target
            factors.append(FactorImpact(factor=nutrient, impact=round(impact, 3), reason=f"Fills {min(gap, n.micronutrients[nutrient]):g} of a {gap:g} gap ({nutrient})"))
    goal = normalize(" ".join([profile.primary_goal, *profile.secondary_goals]))
    if "muscle" in goal or "protein" in goal:
        remaining_fraction = max(0, 1 - daily.protein_consumed / profile.protein_target) if profile.protein_target else 1
        factors.append(FactorImpact(factor="goal_fit", impact=round(min(4, n.protein_g / 5) * remaining_fraction, 3), reason="Protein supports the selected goal; benefit decreases as the daily target is met"))
    elif "fat loss" in goal or "weight" in goal:
        factors.append(FactorImpact(factor="goal_fit", impact=2 if n.fiber_g >= 3 and n.calories <= 250 else 0, reason="Fiber and serving calories considered for the selected goal"))
    if any(contains(" ".join([product.name, *product.ingredients]), dislike) for dislike in profile.dislikes):
        factors.append(FactorImpact(factor="dislike", impact=-5, reason="Matches a stated dislike"))
    if set(product.stores) & set(profile.preferred_stores):
        factors.append(FactorImpact(factor="preferred_store", impact=1, reason="Available from a preferred store"))
    return GPersonalScore(base_score=base, personal_score=round(max(0, min(100, base + sum(f.impact for f in factors))), 3), compatibility="compatible", drivers=[f for f in factors if f.impact >= 0], penalties=[f for f in factors if f.impact < 0])
