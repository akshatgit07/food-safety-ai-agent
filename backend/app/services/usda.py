import os
import threading
import time
from difflib import get_close_matches
from typing import Any

import requests

USDA_FDC_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# A 5-day x 3-meal x 6-ingredient plan is 90 ingredients. Serial lookups at the old
# 12s timeout could hold a request open for ~18 minutes, well past any Render or
# browser timeout. Bound both the per-call wait and the total time spent per plan.
USDA_REQUEST_TIMEOUT_SECONDS = 4.0
USDA_ENRICHMENT_BUDGET_SECONDS = 8.0

_lookup_cache: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()

FALLBACK_NUTRITION_DB: dict[str, dict[str, float | str]] = {
    "greek yogurt": {"display_name": "Greek Yogurt", "calories": 120, "protein_g": 17, "source": "fallback"},
    "egg": {"display_name": "Egg", "calories": 72, "protein_g": 6, "source": "fallback"},
    "oats": {"display_name": "Oats", "calories": 150, "protein_g": 5, "source": "fallback"},
    "chicken breast": {"display_name": "Chicken Breast", "calories": 165, "protein_g": 31, "source": "fallback"},
    "salmon": {"display_name": "Salmon", "calories": 206, "protein_g": 22, "source": "fallback"},
    "tofu": {"display_name": "Tofu", "calories": 80, "protein_g": 10, "source": "fallback"},
    "cottage cheese": {"display_name": "Cottage Cheese", "calories": 110, "protein_g": 13, "source": "fallback"},
    "lentils": {"display_name": "Lentils", "calories": 180, "protein_g": 14, "source": "fallback"},
    "black beans": {"display_name": "Black Beans", "calories": 160, "protein_g": 9, "source": "fallback"},
    "brown rice": {"display_name": "Brown Rice", "calories": 215, "protein_g": 5, "source": "fallback"},
    "quinoa": {"display_name": "Quinoa", "calories": 222, "protein_g": 8, "source": "fallback"},
    "spinach": {"display_name": "Spinach", "calories": 23, "protein_g": 3, "source": "fallback"},
    "broccoli": {"display_name": "Broccoli", "calories": 55, "protein_g": 4, "source": "fallback"},
    "banana": {"display_name": "Banana", "calories": 105, "protein_g": 1, "source": "fallback"},
    "berries": {"display_name": "Mixed Berries", "calories": 70, "protein_g": 1, "source": "fallback"},
    "avocado": {"display_name": "Avocado", "calories": 160, "protein_g": 2, "source": "fallback"},
    "almonds": {"display_name": "Almonds", "calories": 170, "protein_g": 6, "source": "fallback"},
    "peanut butter": {"display_name": "Peanut Butter", "calories": 190, "protein_g": 8, "source": "fallback"},
    "protein powder": {"display_name": "Protein Powder", "calories": 120, "protein_g": 24, "source": "fallback"},
    "sweet potato": {"display_name": "Sweet Potato", "calories": 112, "protein_g": 2, "source": "fallback"},
}


def _extract_nutrient(food: dict[str, Any], nutrient_name: str, unit: str | None = None) -> float | None:
    """Return a nutrient value, optionally restricted to a unit.

    FoodData Central reports Energy twice, in kJ and in kcal, and the kJ row usually
    comes first. Matching on name alone silently returned kilojoules - a 4.2x
    overstatement of every calorie figure.
    """
    fallback: float | None = None
    for nutrient in food.get("foodNutrients", []):
        name = (nutrient.get("nutrientName") or "").lower()
        if nutrient_name.lower() not in name:
            continue
        value = nutrient.get("value")
        if not isinstance(value, (int, float)):
            continue
        if unit is None:
            return float(value)
        if (nutrient.get("unitName") or "").lower() == unit.lower():
            return float(value)
        if fallback is None:
            fallback = float(value)
    return None if unit else fallback


def _fallback_lookup(query: str) -> dict[str, Any] | None:
    lowered = query.lower().strip()
    if lowered in FALLBACK_NUTRITION_DB:
        return FALLBACK_NUTRITION_DB[lowered]

    matches = get_close_matches(lowered, FALLBACK_NUTRITION_DB.keys(), n=1, cutoff=0.75)
    if matches:
        return FALLBACK_NUTRITION_DB[matches[0]]
    return None


def lookup_food(query: str, allow_network: bool = True) -> dict[str, Any]:
    key = query.lower().strip()
    with _cache_lock:
        cached = _lookup_cache.get(key)
    if cached is not None:
        return cached
    result = _lookup_food_uncached(query, allow_network)
    with _cache_lock:
        _lookup_cache[key] = result
    return result


def _lookup_food_uncached(query: str, allow_network: bool = True) -> dict[str, Any]:
    api_key = os.getenv("USDA_API_KEY")
    if api_key and allow_network:
        try:
            response = requests.get(
                USDA_FDC_API_URL,
                params={"api_key": api_key, "query": query, "pageSize": 1},
                timeout=USDA_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            foods = response.json().get("foods", [])
            if foods:
                food = foods[0]
                calories = _extract_nutrient(food, "energy", unit="KCAL") or 0
                protein = _extract_nutrient(food, "protein") or 0
                return {
                    "display_name": food.get("description", query.title()),
                    "calories": round(calories, 1),
                    "protein_g": round(protein, 1),
                    "source": "usda",
                }
        except Exception:
            pass

    fallback = _fallback_lookup(query)
    if fallback:
        return fallback

    return {
        "display_name": query.title(),
        "calories": None,
        "protein_g": None,
        "source": "unknown",
    }


def enrich_meal_plan_with_usda(meal_plan: dict[str, Any]) -> dict[str, Any]:
    """Attach USDA reference nutrition to each meal.

    Reference values are per FoodData Central's standard serving. The plan does not
    carry portion sizes, so these are NOT a portion-accurate total and must not
    overwrite the model's own estimate.
    """
    days = meal_plan.get("days", [])
    total_grounded = 0
    total_ingredients = 0
    deadline = time.monotonic() + USDA_ENRICHMENT_BUDGET_SECONDS
    budget_exhausted = False

    for day in days:
        if not isinstance(day, dict):
            continue
        for meal in day.get("meals", []):
            if not isinstance(meal, dict):
                continue
            ingredient_names = meal.get("ingredients", []) or []
            enriched_ingredients: list[dict[str, Any]] = []
            reference_calories = 0.0
            reference_protein = 0.0
            grounded = 0

            for ingredient in ingredient_names:
                if isinstance(ingredient, dict):
                    ingredient_name = ingredient.get("name") or ingredient.get("ingredient") or ""
                else:
                    ingredient_name = str(ingredient)

                # Past the budget, keep serving the local table instead of stalling
                # the request on more network round-trips.
                allow_network = time.monotonic() < deadline
                if not allow_network:
                    budget_exhausted = True
                nutrition = lookup_food(ingredient_name, allow_network=allow_network)
                enriched_ingredients.append({
                    "name": ingredient_name,
                    "nutrition": nutrition,
                })

                total_ingredients += 1
                if nutrition.get("source") != "unknown":
                    grounded += 1
                    total_grounded += 1
                if isinstance(nutrition.get("calories"), (int, float)):
                    reference_calories += float(nutrition["calories"])
                if isinstance(nutrition.get("protein_g"), (int, float)):
                    reference_protein += float(nutrition["protein_g"])

            meal["ingredient_details"] = enriched_ingredients
            # Kept alongside the model estimate rather than replacing it: summing
            # reference servings ignores the portion each recipe actually calls for.
            meal["reference_nutrition"] = {
                "calories": round(reference_calories) if reference_calories else None,
                "protein_g": round(reference_protein, 1) if reference_protein else None,
                "basis": "sum of USDA reference servings, not portion-scaled",
            }
            meal["nutrition_source"] = "model estimate + USDA reference" if grounded else "model estimate"
            meal["grounded_ingredient_ratio"] = f"{grounded}/{max(len(ingredient_names), 1)}"

    meal_plan["nutrition_grounding"] = {
        "source": "USDA API + fallback database" if os.getenv("USDA_API_KEY") else "fallback nutrition database",
        "grounded_ingredients": total_grounded,
        "total_ingredients": total_ingredients,
        "basis": "Reference servings only. Calorie and protein figures are estimates, not portion-accurate totals.",
        "budget_exhausted": budget_exhausted,
    }
    return meal_plan
