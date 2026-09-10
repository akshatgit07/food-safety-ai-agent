"""Import an explicitly identified USDA branded food; never guess missing values."""
import math
import os

import requests

from app.db import utc_now
from app.domain.models import Product
from app.observability import observed


class SourceUnavailable(ValueError):
    pass


def number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Missing or invalid source nutrient: {name}")
    return float(value)


def normalize_usda_food(food: dict) -> Product:
    if food.get("dataType") != "Branded":
        raise ValueError("Only branded USDA foods with a declared serving are supported")
    fdc_id = food.get("fdcId")
    if not isinstance(fdc_id, int) or isinstance(fdc_id, bool) or fdc_id <= 0:
        raise ValueError("A valid FDC identifier is required")
    serving = number(food.get("servingSize"), "serving size")
    if serving <= 0:
        raise ValueError("Serving size must be positive")
    unit = str(food.get("servingSizeUnit") or "").lower()
    unit = {"grm": "g", "mlt": "ml"}.get(unit, unit)
    if unit not in {"g", "ml"}:
        raise ValueError("Serving size must use grams or milliliters")
    fields = {"calories": ("calories", 1008, "kcal"), "protein_g": ("protein", 1003, "g"),
              "carbs_g": ("carbohydrates", 1005, "g"), "fat_g": ("fat", 1004, "g"),
              "fiber_g": ("fiber", 1079, "g"), "sugar_g": ("sugars", 2000, "g"), "sodium_mg": ("sodium", 1093, "mg")}
    labels = food.get("labelNutrients") or {}
    rows = food.get("foodNutrients") or []
    if not isinstance(labels, dict) or not all(isinstance(v, dict) for v in labels.values()) or not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("nutrient", {}), dict) for r in rows):
        raise ValueError("Invalid nutrient structure in source record")
    nutrition = {"basis": "per serving"}
    for output, (label, nutrient_id, expected_unit) in fields.items():
        if labels.get(label, {}).get("value") is not None:
            nutrition[output] = number(labels[label]["value"], output)
        else:
            # USDA nutrient table is standardized per 100 units. Do not infer
            # density for ml servings; require label values for liquids.
            if unit != "g":
                raise ValueError(f"Per-serving label value required for {output} in a liquid")
            matches = [r.get("amount") for r in rows if r.get("nutrient", {}).get("id") == nutrient_id and str(r.get("nutrient", {}).get("unitName", "")).lower() == expected_unit]
            if len(matches) != 1:
                raise ValueError(f"Missing or ambiguous source nutrient: {output}")
            nutrition[output] = round(number(matches[0], output) * serving / 100, 6)
    barcode = food.get("gtinUpc")
    if barcode is not None and (not isinstance(barcode, str) or not barcode.isdigit() or len(barcode) not in {8, 12, 13, 14}):
        raise ValueError("Invalid source barcode; expected a GTIN string")
    name = str(food.get("description") or "").strip()
    if not name:
        raise ValueError("Product description is missing")
    return Product(product_id=f"usda-{fdc_id}", barcode=barcode, name=name,
                   brand=food.get("brandName") or food.get("brandOwner") or "", category=food.get("brandedFoodCategory") or "",
                   nutrition=nutrition, ingredients=[food["ingredients"]] if food.get("ingredients") else [],
                   allergen_info_complete=False, allergens=[], diet_flags=[],
                   processing_metadata={"serving_size": str(serving), "serving_unit": unit, "fdc_id": str(fdc_id), "data_type": "Branded"},
                   provenance={"source": "USDA FoodData Central", "verified": False, "confidence": 0.5,
                               "reference": f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients", "retrieved_at": utc_now().isoformat()})


@observed("guiltless.catalog.usda_import", "tool")
def fetch_usda_food(fdc_id: int) -> tuple[Product, dict]:
    if fdc_id <= 0:
        raise ValueError("FDC ID must be positive")
    key = os.getenv("USDA_API_KEY")
    if not key:
        raise SourceUnavailable("USDA_API_KEY is not configured")
    try:
        response = requests.get(f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}", headers={"X-Api-Key": key}, timeout=8)
        response.raise_for_status()
        food = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SourceUnavailable("USDA details request failed; no product was imported") from exc
    if not isinstance(food, dict) or food.get("fdcId") != fdc_id:
        raise ValueError("USDA returned a different product identifier")
    return normalize_usda_food(food), food
