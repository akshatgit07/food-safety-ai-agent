import os
from difflib import get_close_matches
from typing import Any

import requests

USDA_FDC_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

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


def _extract_nutrient(food: dict[str, Any], nutrient_name: str) -> float | None:
    for nutrient in food.get("foodNutrients", []):
        name = (nutrient.get("nutrientName") or "").lower()
        if nutrient_name.lower() in name:
            value = nutrient.get("value")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _fallback_lookup(query: str) -> dict[str, Any] | None:
    lowered = query.lower().strip()
    if lowered in FALLBACK_NUTRITION_DB:
        return FALLBACK_NUTRITION_DB[lowered]

    matches = get_close_matches(lowered, FALLBACK_NUTRITION_DB.keys(), n=1, cutoff=0.75)
    if matches:
        return FALLBACK_NUTRITION_DB[matches[0]]
    return None


def lookup_food(query: str) -> dict[str, Any]:
    api_key = os.getenv("USDA_API_KEY")
    if api_key:
        try:
            response = requests.get(
                USDA_FDC_API_URL,
                params={"api_key": api_key, "query": query, "pageSize": 1},
                timeout=12,
            )
            response.raise_for_status()
            foods = response.json().get("foods", [])
            if foods:
                food = foods[0]
                calories = _extract_nutrient(food, "energy") or 0
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
    days = meal_plan.get("days", [])
    total_grounded = 0
    total_ingredients = 0

    for day in days:
        for meal in day.get("meals", []):
            ingredient_names = meal.get("ingredients", []) or []
            enriched_ingredients: list[dict[str, Any]] = []
            meal_calories = 0.0
            meal_protein = 0.0
            grounded = 0

            for ingredient in ingredient_names:
                if isinstance(ingredient, dict):
                    ingredient_name = ingredient.get("name") or ingredient.get("ingredient") or ""
                else:
                    ingredient_name = str(ingredient)

                nutrition = lookup_food(ingredient_name)
                enriched_ingredients.append({
                    "name": ingredient_name,
                    "nutrition": nutrition,
                })

                total_ingredients += 1
                if nutrition.get("source") != "unknown":
                    grounded += 1
                    total_grounded += 1
                if isinstance(nutrition.get("calories"), (int, float)):
                    meal_calories += float(nutrition["calories"])
                if isinstance(nutrition.get("protein_g"), (int, float)):
                    meal_protein += float(nutrition["protein_g"])

            meal["ingredient_details"] = enriched_ingredients
            if meal_calories:
                meal["estimated_calories"] = round(meal_calories)
            if meal_protein:
                meal["estimated_protein_g"] = round(meal_protein, 1)
            meal["nutrition_source"] = "USDA" if grounded else "model estimate"
            meal["grounded_ingredient_ratio"] = f"{grounded}/{max(len(ingredient_names), 1)}"

    meal_plan["nutrition_grounding"] = {
        "source": "USDA API + fallback database" if os.getenv("USDA_API_KEY") else "fallback nutrition database",
        "grounded_ingredients": total_grounded,
        "total_ingredients": total_ingredients,
    }
    return meal_plan
