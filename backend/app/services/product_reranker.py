from app.domain.models import DailyNutritionState, Product, UserProfile
from app.services.g_personal import base_score, hard_constraint_failures, score_product


def rerank(current: Product, candidates: list[tuple[Product, float]], profile: UserProfile,
           daily: DailyNutritionState) -> list[dict]:
    ranked = []
    for product, similarity in candidates:
        # Defense in depth for callers other than the retrieval pipeline.
        if hard_constraint_failures(product, profile) or product.in_stock is False:
            continue
        score = score_product(product, profile, daily)
        delta = score.base_score - base_score(current)
        nutrition = {"protein_g_delta": product.nutrition.protein_g - current.nutrition.protein_g,
                     "sugar_g_reduction": current.nutrition.sugar_g - product.nutrition.sugar_g,
                     "fiber_g_delta": product.nutrition.fiber_g - current.nutrition.fiber_g}
        max_price = profile.budget_preferences.get("max_price")
        price_fit = 0 if product.price is None or not max_price else (2 if product.price <= max_price else -2)
        rank_score = round(0.5 * score.personal_score + 20 * similarity + 0.3 * delta + price_fit, 4)
        ranked.append({"product": product.model_dump(mode="json"), "semantic_similarity": round(similarity, 4),
                       "base_score_delta": delta, "personal_score": score.personal_score,
                       "scoring": score.model_dump(), "nutrition_improvement": nutrition, "rank_score": rank_score,
                       "ranking_reasons": [f"Base quality change: {delta:+g}", f"Local relevance: {similarity:.2f}",
                                           *[d.reason for d in score.drivers if d.impact > 0],
                                           *[p.reason for p in score.penalties],
                                           "Price unavailable" if product.price is None else f"Price fit impact: {price_fit:+g}",
                                           "Inventory unknown" if product.in_stock is None else "In stock in supplied catalog"]})
    return sorted(ranked, key=lambda item: (-item["rank_score"], item["product"]["product_id"]))
