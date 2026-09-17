"""Product decisions over actual records, separate from graph orchestration."""
from app.domain.models import DailyNutritionState, Product, UserProfile
from app.services.g_personal import base_score, score_product
from app.services.product_retriever import CandidateRetriever, find_alternatives


def scored(product: Product, profile: UserProfile, daily: DailyNutritionState) -> dict:
    record = product.model_dump(mode="json")
    record["base_score"] = base_score(product)
    return {"product": record, "scoring": score_product(product, profile, daily).model_dump()}


def product_decision(intent: str, current: Product | None, bag: list[Product],
                     profile: UserProfile, daily: DailyNutritionState, retriever: CandidateRetriever,
                     message: str) -> dict:
    if intent in {"explain_product", "find_swap"}:
        if current is None:
            raise ValueError("Select a catalog product or supply an exact barcode")
        result = {"current_product": scored(current, profile, daily), "recommended_product_ids": []}
        if intent == "find_swap":
            alternatives = find_alternatives(current, profile, daily, retriever, message)
            # A swap must improve quality or replace an incompatible item.
            current_score = result["current_product"]["scoring"]
            alternatives = [a for a in alternatives if current_score["compatibility"] == "incompatible" or a["personal_score"] > current_score["personal_score"]]
            result["ranked_alternatives"] = alternatives
            result["recommended_product_ids"] = [a["product"]["product_id"] for a in alternatives]
        return result
    if not bag:
        raise ValueError("Add catalog products to the bag first")
    items = [scored(p, profile, daily) for p in bag]
    if intent == "compare_products":
        if len(items) < 2:
            raise ValueError("Select at least two products to compare")
        compatible = [p for p in items if p["scoring"]["compatibility"] == "compatible"]
        compatible.sort(key=lambda p: (-p["scoring"]["personal_score"], p["product"]["product_id"]))
        return {"items": items, "recommended_product_ids": [compatible[0]["product"]["product_id"]] if compatible else []}
    swaps = []
    optimized = list(bag)
    for index, p in enumerate(bag):
        alternatives = find_alternatives(p, profile, daily, retriever, message)
        current_score = items[index]["scoring"]
        options = [a for a in alternatives if current_score["compatibility"] == "incompatible" or a["personal_score"] > current_score["personal_score"]]
        if options:
            alternative = options[0]
            optimized[index] = Product.model_validate(alternative["product"])
            swaps.append({"current_product": items[index], "alternative": alternative,
                          "score_improvement": alternative["base_score_delta"]})
    before = round(sum(base_score(p) for p in bag) / len(bag), 3)
    after = round(sum(base_score(p) for p in optimized) / len(optimized), 3)
    return {"items": items, "swaps": swaps, "current_score": before, "optimized_score": after,
            "score_gain": round(after - before, 3),
            "recommended_product_ids": [s["alternative"]["product"]["product_id"] for s in swaps]}
