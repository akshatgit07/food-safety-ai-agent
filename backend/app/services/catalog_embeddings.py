"""Offline public-product embeddings; requests never call an embedding provider."""
import hashlib
import json
import logging
import math
import os

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import CatalogEmbeddingRecord, session_scope
from app.domain.models import Product

MODEL = "text-embedding-3-small"
DIMENSIONS = 256


def product_text(product: Product) -> str:
    # Exclude personal data and mutable prices/scores from semantic identity.
    return json.dumps({"name": product.name, "category": product.category,
                       "ingredients": product.ingredients}, sort_keys=True, ensure_ascii=False)


def fingerprint(product: Product) -> str:
    return hashlib.sha256(product_text(product).encode()).hexdigest()


def valid_vector(vector) -> bool:
    return (isinstance(vector, list) and len(vector) == DIMENSIONS
            and all(type(x) in (float, int) and math.isfinite(x) for x in vector)
            and 0 < sum(x * x for x in vector) < float("inf"))


def cosine(a, b) -> float:
    a_norm, b_norm = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    return sum((x / a_norm) * (y / b_norm) for x, y in zip(a, b))


class EmbeddingStore:
    def load_many(self, products: list[Product]) -> dict[str, list[float]]:
        if not products:
            return {}
        expected = {p.product_id: fingerprint(p) for p in products}
        with session_scope() as session:
            rows = session.scalars(select(CatalogEmbeddingRecord).where(
                CatalogEmbeddingRecord.product_id.in_(expected), CatalogEmbeddingRecord.model == MODEL
            )).all()
            result = {}
            for row in rows:
                if row.fingerprint != expected[row.product_id]:
                    continue
                try:
                    vector = json.loads(row.vector_json)
                except (ValueError, TypeError):
                    continue
                if valid_vector(vector):
                    result[row.product_id] = vector
            return result

    def save(self, product: Product, vector: list[float]):
        if not valid_vector(vector):
            raise ValueError("Embedding must contain 256 finite values and have nonzero norm")
        with session_scope() as session:
            session.merge(CatalogEmbeddingRecord(product_id=product.product_id, model=MODEL,
                          fingerprint=fingerprint(product), vector_json=json.dumps(vector)))

    def similarities(self, anchor, vectors):
        """Optional exact pgvector distance, falling back to identical local cosine.

        Safety filtering happens before IDs reach this query. This first version
        is intentionally exact and batch-bounded, not an approximate ANN index.
        """
        if os.getenv("CATALOG_VECTOR_BACKEND", "local") == "pgvector" and vectors:
            try:
                with session_scope() as session:
                    if session.bind.dialect.name == "postgresql":
                        # Values are already validated. Pass vectors as JSON data;
                        # never interpolate product identifiers into SQL.
                        rows = session.execute(text("""
                            SELECT item->>'id' AS id,
                                   1 - (CAST(item->>'vector' AS vector(256))
                                        <=> CAST(:anchor AS vector(256))) AS similarity
                            FROM jsonb_array_elements(CAST(:items AS jsonb)) AS item
                        """), {"anchor": json.dumps(anchor), "items": json.dumps([
                            {"id": key, "vector": json.dumps(value)} for key, value in vectors.items()
                        ])}).all()
                        return {row.id: float(row.similarity) for row in rows}, "pgvector"
            except SQLAlchemyError:
                # No raw DB errors or source text in logs; optional extension failure
                # must not disable product recommendations.
                logging.getLogger(__name__).warning("pgvector unavailable; using local cosine")
        return {key: cosine(anchor, value) for key, value in vectors.items()}, "local"
