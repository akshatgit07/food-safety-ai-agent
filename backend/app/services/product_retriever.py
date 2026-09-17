"""Local lexical discovery adapter; no claim of embedding/vector retrieval."""
from typing import Protocol
from app.observability import observed

from app.domain.models import DailyNutritionState, Product, UserProfile
from app.services.g_personal import hard_constraint_failures, normalize
from app.services.product_reranker import rerank


class CandidateRetriever(Protocol):
    def retrieve(self, current: Product, query: str, limit: int = 50) -> list[Product]: ...


class LocalCandidateRetriever:
    def __init__(self, products: list[Product]):
        self.products = products

    def retrieve(self, current: Product, query: str, limit: int = 50) -> list[Product]:
        return [p.model_copy(deep=True) for p in self.products if p.product_id != current.product_id][:limit]


# A candidate scoring 0 is discarded outright. With free-text categories and pure
# token overlap that silently returned NO alternatives whenever the safe options
# sat in a different category - a milk-allergic yogurt shopper was offered nothing
# even though two dairy-free products were in the catalog. The floor keeps safe,
# constraint-passing products eligible; the 0.6 same-category bonus and the 20x
# similarity weight in rerank() still put closer matches on top.
WEAK_MATCH_FLOOR = 0.05


def relevance(current: Product, candidate: Product, query: str) -> float:
    source = set(normalize(f"{current.name} {current.category} {query}").split())
    target = set(normalize(f"{candidate.name} {candidate.category}").split())
    overlap = len(source & target) / max(1, len(source | target))
    same_category = normalize(current.category) == normalize(candidate.category)
    return min(1, max(WEAK_MATCH_FLOOR, overlap + (0.6 if same_category else 0)))


@observed("guiltless.alternatives.retrieve", "retriever")
def find_alternatives(current: Product, profile: UserProfile, daily: DailyNutritionState,
                      retriever: CandidateRetriever, query: str = "") -> list[dict]:
    metadata = {}
    if callable(getattr(type(retriever), "retrieve_scored", None)):
        batch = retriever.retrieve_scored(current, query, profile)
        retrieved = [p for p, _, _ in batch]
        similarities = {p.product_id: s for p, s, _ in batch}
        metadata = {p.product_id: details for p, _, details in batch}
    else:
        retrieved = retriever.retrieve(current, query)
        similarities = {}
    # No excluded product is handed to a scorer, reranker, or language model.
    safe = [p for p in retrieved if p.product_id != current.product_id and not hard_constraint_failures(p, profile) and p.in_stock is not False]
    relevant = [(p, similarities.get(p.product_id, relevance(current, p, query))) for p in safe]
    relevant = [(p, s) for p, s in relevant if s > 0 and p.nutrition.basis == current.nutrition.basis]
    ranked = rerank(current, relevant, profile, daily)[:5]
    for item in ranked:
        item["retrieval"] = metadata.get(item["product"]["product_id"], {"method": "lexical"})
    return ranked
