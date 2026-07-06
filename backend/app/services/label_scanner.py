from __future__ import annotations

import re
from typing import Any, Callable


NutritionExtractor = Callable[[str], dict[str, Any]]


DEMO_LABEL_TEXT = """Frosted Snack Bar
Quick Bite
Calories 260
Total Fat 8g
Sodium 310mg
Total Carbohydrate 42g
Dietary Fiber 1g
Total Sugars 24g
Protein 3g
Ingredients: oats, corn syrup, palm oil, artificial flavor
"""


def _number(text: str, patterns: list[str]) -> float:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
    return 0.0


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 1)


def _parse_ingredients(text: str) -> list[str]:
    match = re.search(r"ingredients?\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    ingredients_line = match.group(1).splitlines()[0]
    return [item.strip(" .") for item in re.split(r"[,;]", ingredients_line) if item.strip(" .")]


def _guess_identity(text: str, supplied_name: str | None, supplied_brand: str | None) -> tuple[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    nutrient_row = re.compile(
        r"^(nutrition facts|calories\b|serving\b|total (fat|carbohydrate|sugars?)\b|"
        r"sodium\b|protein\s*[:\d]|dietary fiber\b|ingredients?\b)",
        flags=re.IGNORECASE,
    )
    candidates = [line for line in lines if not nutrient_row.search(line) and not re.search(r"\d+\s*(g|mg|kcal|%)", line.lower())]
    name = supplied_name or (candidates[0] if candidates else "Scanned product")
    brand = supplied_brand or (candidates[1] if len(candidates) > 1 else "Label scan")
    return name[:100], brand[:100]


def parse_label_text(label_text: str, product_name: str | None = None, brand: str | None = None) -> dict[str, Any]:
    text = label_text.strip()
    if not text:
        raise ValueError("Paste nutrition-label text or upload an image.")

    name, resolved_brand = _guess_identity(text, product_name, brand)
    nutrition = {
        "calories": _clean_number(_number(text, [r"calories?\s*[:\-]?\s*(\d+(?:\.\d+)?)"])),
        "protein_g": _clean_number(_number(text, [r"protein\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g"])),
        "fiber_g": _clean_number(_number(text, [r"(?:dietary\s+)?fiber\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g"])),
        "sugar_g": _clean_number(_number(text, [r"(?:total\s+|added\s+)?sugars?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g"])),
        "sodium_mg": _clean_number(_number(text, [r"sodium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg"])),
    }
    ingredients = _parse_ingredients(text)
    found_fields = sum(1 for value in nutrition.values() if value)
    confidence = min(0.96, 0.42 + found_fields * 0.09 + (0.08 if ingredients else 0))
    warnings = []
    if found_fields < 3:
        warnings.append("Only part of the nutrition panel was detected; review the fields before using the score.")
    if not ingredients:
        warnings.append("No ingredient list was detected.")

    return {
        "product": {
            "name": name,
            "brand": resolved_brand,
            "category": "Scanned food",
            "nutrition": nutrition,
            "ingredients": ingredients,
        },
        "confidence": round(confidence, 2),
        "extraction_mode": "label_text",
        "extracted_fields": [key for key, value in nutrition.items() if value],
        "warnings": warnings,
    }


def scan_label(
    *,
    label_text: str | None = None,
    image_data_url: str | None = None,
    product_name: str | None = None,
    brand: str | None = None,
    image_extractor: NutritionExtractor | None = None,
) -> dict[str, Any]:
    if image_data_url and image_extractor:
        result = image_extractor(image_data_url)
        if not isinstance(result, dict) or not isinstance(result.get("product"), dict):
            raise ValueError("The image extractor returned an invalid product.")
        result.setdefault("confidence", 0.8)
        result.setdefault("extraction_mode", "vision")
        result.setdefault("extracted_fields", list((result["product"].get("nutrition") or {}).keys()))
        result.setdefault("warnings", [])
        return result

    if label_text and label_text.strip():
        result = parse_label_text(label_text, product_name, brand)
        if image_data_url:
            result["warnings"].append("Image OCR is unavailable, so the pasted label text was used.")
        return result

    if image_data_url:
        result = parse_label_text(DEMO_LABEL_TEXT, product_name, brand)
        result["extraction_mode"] = "demo_fallback"
        result["confidence"] = 0.35
        result["warnings"].append("Vision extraction requires OPENAI_API_KEY; demo label values are shown for now.")
        return result

    raise ValueError("Paste nutrition-label text or upload an image.")
