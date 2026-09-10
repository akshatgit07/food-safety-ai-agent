import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError

from app.catalog_index_cli import index_catalog
from app.domain.models import DailyNutritionState, UserProfile
from app.services.catalog_embeddings import DIMENSIONS, EmbeddingStore, cosine
from app.services.catalog_repository import CatalogCandidateRetriever, SqlProductRepository
from app.services.product_lookup import demo_catalog
from app.services.product_retriever import find_alternatives


def vector(first=1.0, second=0.0):
    return [first, second] + [0.0] * (DIMENSIONS - 2)


class HybridRetrievalTests(unittest.TestCase):
    def product(self, **updates):
        return demo_catalog()[0].model_copy(update={"product_id": str(uuid4()), "barcode": None, **updates})

    def retriever(self, products):
        repo = Mock()
        repo.iter_products.side_effect = lambda: iter(products)
        return CatalogCandidateRetriever(repo)

    def test_safe_product_after_first_fifty_is_not_starved(self):
        current = self.product()
        unsafe = [self.product(allergens=["milk"]) for _ in range(65)]
        safe = self.product(name="Oat snack", category="Snack", allergens=[], ingredients=["oats"], allergen_info_complete=True)
        results = find_alternatives(current, UserProfile(allergies=["milk"]), DailyNutritionState(),
                                    self.retriever(unsafe + [safe]))
        self.assertEqual([r["product"]["product_id"] for r in results], [safe.product_id])

    def test_full_catalog_relevance_precedes_limit(self):
        current = self.product(name="Unique yogurt", category="Yogurt")
        weak = [self.product(name="Bread", category="Bread") for _ in range(70)]
        strong = self.product(name="Unique yogurt", category="Yogurt")
        result = self.retriever(weak + [strong]).retrieve(current, "", limit=1)
        self.assertEqual(result[0].product_id, strong.product_id)

    def test_embeddings_survive_new_store_but_content_changes_expire_them(self):
        product = SqlProductRepository(False).upsert(self.product())
        EmbeddingStore().save(product, vector())
        self.assertEqual(EmbeddingStore().load_many([product])[product.product_id], vector())
        changed = product.model_copy(update={"ingredients": ["New ingredient"]})
        self.assertEqual(EmbeddingStore().load_many([changed]), {})

    def test_malformed_vectors_rejected(self):
        for value in ([], [1], vector(float("nan")), vector(float("inf")), vector(0), vector(True)):
            with self.assertRaises(ValueError):
                EmbeddingStore().save(self.product(), value)

    def test_hybrid_metadata_and_missing_embedding_fallback(self):
        repo = SqlProductRepository(False)
        current, candidate = [repo.upsert(self.product()) for _ in range(2)]
        store = EmbeddingStore()
        store.save(current, vector())
        store.save(candidate, vector())
        missing = self.product()
        result = self.retriever([candidate, missing]).retrieve_scored(current, "", UserProfile())
        details = {p.product_id: metadata for p, _, metadata in result}
        self.assertEqual(details[candidate.product_id]["method"], "hybrid")
        self.assertEqual(details[missing.product_id]["method"], "lexical")
        self.assertEqual(details[candidate.product_id]["semantic_score"], 1)

    def test_sqlite_pgvector_setting_gracefully_uses_local_cosine(self):
        with patch.dict("os.environ", {"CATALOG_VECTOR_BACKEND": "pgvector"}):
            scores, backend = EmbeddingStore().similarities(vector(), {"id": vector()})
        self.assertEqual(backend, "local")
        self.assertEqual(scores["id"], 1)
        self.assertEqual(cosine(vector(), vector(0, 1)), 0)

    def test_indexing_idempotent_and_provider_receives_only_product_text(self):
        product = SqlProductRepository(False).upsert(self.product())
        repo, client = Mock(), Mock()
        repo.iter_products.side_effect = lambda: iter([product])
        client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=vector())])
        self.assertEqual(index_catalog(repo, client)["indexed"], 1)
        self.assertEqual(index_catalog(repo, client)["indexed"], 0)
        client.embeddings.create.assert_called_once()
        payload = client.embeddings.create.call_args.kwargs["input"][0]
        self.assertNotIn("user_id", payload)
        self.assertNotIn("allergies", payload)

    def test_pgvector_parameters_and_backend_metadata(self):
        with patch("app.services.catalog_embeddings.session_scope") as scope, patch.dict(
                "os.environ", {"CATALOG_VECTOR_BACKEND": "pgvector"}):
            session = scope.return_value.__enter__.return_value
            session.bind.dialect.name = "postgresql"
            session.execute.return_value.all.return_value = [SimpleNamespace(id="product", similarity=0.75)]
            scores, backend = EmbeddingStore().similarities(vector(), {"product": vector()})
            self.assertEqual((scores, backend), ({"product": 0.75}, "pgvector"))
            self.assertIn("items", session.execute.call_args.args[1])

    def test_pgvector_error_falls_back_without_disabling_retrieval(self):
        with patch("app.services.catalog_embeddings.session_scope") as scope, patch.dict(
                "os.environ", {"CATALOG_VECTOR_BACKEND": "pgvector"}):
            session = scope.return_value.__enter__.return_value
            session.bind.dialect.name = "postgresql"
            session.execute.side_effect = SQLAlchemyError("extension unavailable")
            scores, backend = EmbeddingStore().similarities(vector(), {"product": vector()})
            self.assertEqual((scores, backend), ({"product": 1}, "local"))

    def test_invalid_provider_batch_does_not_write(self):
        product = SqlProductRepository(False).upsert(self.product())
        repo, client = Mock(), Mock()
        repo.iter_products.return_value = iter([product])
        client.embeddings.create.return_value = SimpleNamespace(data=[])
        with self.assertRaises(ValueError):
            index_catalog(repo, client)
        self.assertEqual(EmbeddingStore().load_many([product]), {})

    def test_keyset_pagination_has_no_duplicates_or_missing_records(self):
        repo = SqlProductRepository(False)
        ids = {repo.upsert(self.product()).product_id for _ in range(5)}
        fetched = [p.product_id for p in repo.iter_products(batch_size=2)]
        self.assertTrue(ids.issubset(set(fetched)))
        self.assertEqual(len(fetched), len(set(fetched)))
