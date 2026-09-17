"""Fail-closed validation of catalog references and deterministic score claims."""
from typing import Any
from app.observability import observed

from app.domain.models import DailyNutritionState, UserProfile
from app.services.g_personal import base_score, hard_constraint_failures, score_product
from app.services.product_lookup import ProductLookup


@observed("guiltless.result.validate", "tool")
def validate_result(result: dict, profile: UserProfile, daily: DailyNutritionState, lookup: ProductLookup) -> list[str]:
    try:
        return _validate_result(result, profile, daily, lookup)
    except (KeyError, TypeError, ValueError, AttributeError):
        return ["Malformed product result rejected"]


def _validate_result(result: dict, profile: UserProfile, daily: DailyNutritionState, lookup: ProductLookup) -> list[str]:
    errors = []
    seen = set()
    recommendations = set(result.get("recommended_product_ids", []))

    def visit(value: Any, current_id: str | None = None):
        if isinstance(value, list):
            for item in value:
                visit(item, current_id)
            return
        if not isinstance(value, dict):
            return
        if isinstance(value.get("current_product"), dict):
            current_id = value["current_product"].get("product", {}).get("product_id")
        if "product_id" in value:
            pid = value["product_id"]
            canonical = lookup.find(product_id=pid)
            if canonical is None:
                errors.append(f"Unknown product reference: {pid}")
            else:
                seen.add(pid)
                if value != canonical.model_dump(mode="json"):
                    errors.append(f"Catalog facts altered: {pid}")
        if isinstance(value.get("product"), dict):
            pid = value["product"].get("product_id")
            canonical = lookup.find(product_id=pid) if pid else None
            if canonical:
                expected = score_product(canonical, profile, daily).model_dump()
                if value.get("scoring") != expected:
                    errors.append(f"Scoring mismatch: {pid}")
                if "personal_score" in value:
                    recommendations.add(pid)
                    if value["personal_score"] != expected["personal_score"]:
                        errors.append(f"Personal score altered: {pid}")
                if "base_score_delta" in value:
                    current = lookup.find(product_id=current_id) if current_id else None
                    if current is None or value["base_score_delta"] != base_score(canonical) - base_score(current):
                        errors.append(f"Base score delta altered: {pid}")
        for child in value.values():
            visit(child, current_id)

    visit(result)
    for pid in sorted(recommendations):
        product = lookup.find(product_id=pid)
        if pid not in seen or product is None:
            errors.append(f"Recommendation absent from tool records: {pid}")
        elif hard_constraint_failures(product, profile):
            errors.append(f"Incompatible recommendation rejected: {pid}")
        elif product.in_stock is False:
            errors.append(f"Unavailable recommendation rejected: {pid}")
    if "optimized_score" in result:
        originals = [lookup.find(product_id=p["product"]["product_id"]) for p in result.get("items", [])]
        if originals and all(originals):
            # Match swaps to occurrences, preserving duplicate bag items.
            replacement = list(originals)
            used = set()
            for swap in result.get("swaps", []):
                pid = swap["current_product"]["product"]["product_id"]
                for index, p in enumerate(originals):
                    if index not in used and p.product_id == pid:
                        replacement[index] = lookup.find(product_id=swap["alternative"]["product"]["product_id"])
                        used.add(index)
                        break
                if swap.get("score_improvement") != swap["alternative"].get("base_score_delta"):
                    errors.append("Swap score improvement altered")
            if all(replacement):
                before = round(sum(base_score(p) for p in originals) / len(originals), 3)
                after = round(sum(base_score(p) for p in replacement) / len(replacement), 3)
                if (result.get("current_score"), result.get("optimized_score"), result.get("score_gain")) != (before, after, round(after - before, 3)):
                    errors.append("Bag scores altered")
    return sorted(set(errors))


def validate_composition(proposed: dict, approved: dict) -> list[str]:
    """Free-form model output cannot replace the validated product narrative.

    A future LLM may select approved phrases. Until then all claims, including
    prose numbers and named recommendations, must match the approved rendering.
    """
    return [] if proposed == approved else ["Unverified response composition rejected"]
