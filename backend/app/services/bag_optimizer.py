from __future__ import annotations

from typing import Any

from app.services.product_intelligence import explain_product


def optimize_bag(items: list[dict[str, Any]], goal: str = "balanced nutrition") -> dict[str, Any]:
    scored = [explain_product(item, goal) for item in items]
    current_score = round(sum(item["score"] for item in scored) / len(scored)) if scored else 0

    swaps: list[dict[str, Any]] = []
    for original, explanation in zip(items, scored):
        if explanation["score"] >= 70:
            continue
        nutrition = dict(original.get("nutrition") or {})
        improved = dict(original)
        improved["name"] = f"Healthier {original.get('name', 'alternative')}"
        improved["nutrition"] = {
            **nutrition,
            "sugar_g": max(0, float(nutrition.get("sugar_g") or 0) - 6),
            "fiber_g": float(nutrition.get("fiber_g") or 0) + 3,
            "protein_g": float(nutrition.get("protein_g") or 0) + 4,
            "sodium_mg": max(0, float(nutrition.get("sodium_mg") or 0) - 100),
        }
        improved_explanation = explain_product(improved, goal)
        swaps.append(
            {
                "replace": original.get("name", "Item"),
                "with": improved["name"],
                "current_score": explanation["score"],
                "new_score": improved_explanation["score"],
                "score_gain": improved_explanation["score"] - explanation["score"],
                "reason": improved_explanation["summary"],
            }
        )

    projected_scores = [item["score"] for item in scored]
    for swap in swaps:
        try:
            index = next(i for i, item in enumerate(scored) if item["product"]["name"] == swap["replace"])
            projected_scores[index] = swap["new_score"]
        except StopIteration:
            continue

    projected_score = round(sum(projected_scores) / len(projected_scores)) if projected_scores else current_score
    return {
        "goal": goal,
        "current_score": current_score,
        "projected_score": projected_score,
        "score_gain": projected_score - current_score,
        "items": scored,
        "swaps": swaps,
        "summary": (
            f"The bag can improve from {current_score} to {projected_score} with {len(swaps)} suggested swap(s)."
            if items
            else "Add products to receive bag recommendations."
        ),
    }
