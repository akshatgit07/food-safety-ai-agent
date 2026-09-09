"""Local lexical discovery adapter; no claim of embedding/vector retrieval."""
from typing import Protocol

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


def relevance(current: Product, candidate: Product, query: str) -> float:
    source = set(normalize(f"{current.name} {current.category} {query}").split())
    target = set(normalize(f"{candidate.name} {candidate.category}").split())
    overlap = len(source & target) / max(1, len(source | target))
    return min(1, overlap + (0.6 if normalize(current.category) == normalize(candidate.category) else 0))


def find_alternatives(current: Product, profile: UserProfile, daily: DailyNutritionState,
                      retriever: CandidateRetriever, query: str = "") -> list[dict]:
    retrieved = retriever.retrieve(current, query)
    # No excluded product is handed to a scorer, reranker, or language model.
    safe = [p for p in retrieved if p.product_id != current.product_id and not hard_constraint_failures(p, profile) and p.in_stock is not False]
    relevant = [(p, relevance(current, p, query)) for p in safe]
    relevant = [(p, s) for p, s in relevant if s > 0 and p.nutrition.basis == current.nutrition.basis]
    return rerank(current, relevant, profile, daily)[:5]
