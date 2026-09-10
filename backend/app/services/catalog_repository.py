"""SQLAlchemy canonical catalog, compatible with local SQLite and Postgres."""
import json
import threading

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.db import CatalogProductRecord, session_scope, utc_now
from app.domain.models import Product, SCORE_VERSION
from app.services.g_personal import base_score
from app.services.product_lookup import demo_catalog


class SqlProductRepository:
    def __init__(self, seed_demo: bool = True):
        self.seed_demo = seed_demo
        self._factory = None
        self._lock = threading.Lock()

    def ensure_seeded(self):
        db.init_db()
        if not self.seed_demo or self._factory is db._session_factory:
            return
        with self._lock:
            if self._factory is db._session_factory:
                return
            for product in demo_catalog():
                # A concurrent worker may seed the same record. Never overwrite
                # existing catalog data merely because the app restarted.
                try:
                    with session_scope() as session:
                        if session.get(CatalogProductRecord, product.product_id) is None:
                            session.add(self._record(product))
                except IntegrityError:
                    with session_scope() as session:
                        if session.get(CatalogProductRecord, product.product_id) is None:
                            raise
            self._factory = db._session_factory

    @staticmethod
    def _record(product: Product, source_record: dict | None = None):
        return CatalogProductRecord(product_id=product.product_id, barcode=product.barcode,
                                    source=product.provenance.source, payload_json=product.model_dump_json(),
                                    source_json=json.dumps(source_record) if source_record is not None else None,
                                    updated_at=utc_now())

    def by_id(self, product_id: str) -> Product | None:
        self.ensure_seeded()
        with session_scope() as session:
            row = session.get(CatalogProductRecord, product_id)
            return Product.model_validate_json(row.payload_json) if row else None

    def by_barcode(self, barcode: str) -> Product | None:
        self.ensure_seeded()
        with session_scope() as session:
            row = session.scalar(select(CatalogProductRecord).where(CatalogProductRecord.barcode == barcode))
            return Product.model_validate_json(row.payload_json) if row else None

    def list_products(self, limit: int = 100, offset: int = 0) -> list[Product]:
        self.ensure_seeded()
        with session_scope() as session:
            rows = session.scalars(select(CatalogProductRecord).order_by(CatalogProductRecord.product_id).offset(offset).limit(limit)).all()
            return [Product.model_validate_json(row.payload_json) for row in rows]

    def upsert(self, product: Product, source_record: dict | None = None) -> Product:
        self.ensure_seeded()
        product = product.model_copy(deep=True)
        product.base_score = base_score(product)
        product.score_version = SCORE_VERSION
        try:
            with session_scope() as session:
                row = session.get(CatalogProductRecord, product.product_id)
                if row is None:
                    session.add(self._record(product, source_record))
                else:
                    row.barcode = product.barcode
                    row.source = product.provenance.source
                    row.payload_json = product.model_dump_json()
                    row.source_json = json.dumps(source_record) if source_record is not None else row.source_json
                    row.updated_at = utc_now()
        except IntegrityError as exc:
            raise ValueError("Catalog identifier conflict; no records were changed") from exc
        return product

    def iter_products(self, batch_size: int = 200):
        """Keyset pagination: no first-page discovery cutoff or long-lived session."""
        self.ensure_seeded()
        cursor = ""
        while True:
            with session_scope() as session:
                rows = session.scalars(select(CatalogProductRecord).where(
                    CatalogProductRecord.product_id > cursor
                ).order_by(CatalogProductRecord.product_id).limit(batch_size)).all()
                products = [Product.model_validate_json(row.payload_json) for row in rows]
            if not products:
                return
            yield from products
            cursor = products[-1].product_id


class CatalogCandidateRetriever:
    """Full-catalog discovery, with safety filtering before the shortlist."""
    def __init__(self, repository: SqlProductRepository):
        self.repository = repository

    def retrieve(self, current: Product, query: str, limit: int = 50) -> list[Product]:
        from app.domain.models import UserProfile
        return [p for p, _, _ in self.retrieve_scored(current, query, UserProfile(), limit)]

    def retrieve_scored(self, current: Product, query: str, profile, limit: int = 50):
        import heapq
        from app.services.catalog_embeddings import EmbeddingStore
        from app.services.g_personal import hard_constraint_failures
        from app.services.product_retriever import relevance

        store = EmbeddingStore()
        anchor = store.load_many([current]).get(current.product_id)

        def candidates():
            batch = []
            for product in self.repository.iter_products():
                if (product.product_id == current.product_id or product.in_stock is False
                        or product.nutrition.basis != current.nutrition.basis
                        or hard_constraint_failures(product, profile)):
                    continue
                batch.append(product)
                if len(batch) == 200:
                    yield from score_batch(batch)
                    batch = []
            yield from score_batch(batch)

        def score_batch(batch):
            vectors = store.load_many(batch) if anchor else {}
            similarities, backend = store.similarities(anchor, vectors) if vectors else ({}, "local")
            for product in batch:
                lexical = relevance(current, product, query)
                vector = vectors.get(product.product_id)
                semantic = max(0.0, min(1.0, similarities[product.product_id])) if vector else None
                # Never penalize an unindexed item relative to lexical fallback.
                score = max(lexical, 0.6 * lexical + 0.4 * semantic) if semantic is not None else lexical
                yield product, score, {
                    "method": "hybrid" if semantic is not None else "lexical",
                    "vector_backend": backend if semantic is not None else None,
                    "lexical_score": round(lexical, 4),
                    "semantic_score": round(semantic, 4) if semantic is not None else None,
                    "fallback_reason": None if semantic is not None else "No current matching embeddings",
                }

        return heapq.nsmallest(limit, candidates(), key=lambda item: (-item[1], item[0].product_id))
