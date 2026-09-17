import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.catalog_repository import SqlProductRepository, CatalogCandidateRetriever
from app.services.product_lookup import MemoryCache, ProductLookup, demo_catalog
from app.services.usda_catalog import normalize_usda_food, fetch_usda_food, SourceUnavailable


def source_record():
    return {"fdcId": 123, "dataType": "Branded", "description": "Source snack", "gtinUpc": "001234567890",
            "brandName": "Test source", "servingSize": 40, "servingSizeUnit": "g", "ingredients": "OATS, MILK",
            "labelNutrients": {k: {"value": v} for k, v in {"calories": 180, "protein": 6, "carbohydrates": 24, "fat": 7, "fiber": 3, "sugars": 4, "sodium": 100}.items()}}


class CatalogTests(unittest.TestCase):
    def test_saved_product_survives_new_repository_and_lookup(self):
        p = demo_catalog()[0].model_copy(update={"product_id": str(uuid4()), "barcode": str(uuid4())})
        SqlProductRepository(seed_demo=False).upsert(p)
        lookup = ProductLookup(SqlProductRepository(seed_demo=False))
        self.assertEqual(lookup.find(barcode=p.barcode).product_id, p.product_id)

    def test_duplicate_barcode_cannot_overwrite_another_product(self):
        repo = SqlProductRepository(seed_demo=False)
        p = demo_catalog()[0].model_copy(update={"product_id": str(uuid4()), "barcode": str(uuid4())})
        repo.upsert(p)
        with self.assertRaises(ValueError):
            repo.upsert(p.model_copy(update={"product_id": str(uuid4()), "name": "Wrong identity"}))
        self.assertEqual(repo.by_barcode(p.barcode).name, p.name)

    def test_cache_expiry_reloads_store(self):
        p = demo_catalog()[0]
        repo = Mock()
        repo.by_id.return_value = p
        with patch("app.services.product_lookup.time.monotonic", return_value=0):
            lookup = ProductLookup(repo, MemoryCache(ttl_seconds=2))
            lookup.find(product_id=p.product_id)
        with patch("app.services.product_lookup.time.monotonic", return_value=3):
            lookup.find(product_id=p.product_id)
        self.assertEqual(repo.by_id.call_count, 2)

    def test_candidate_adapter_reads_persistent_catalog(self):
        repo = Mock()
        repo.iter_products.return_value = iter(demo_catalog())
        candidates = CatalogCandidateRetriever(repo).retrieve(demo_catalog()[0], "alternatives")
        self.assertNotIn("demo-yogurt", [p.product_id for p in candidates])
        repo.iter_products.assert_called_once()

    def test_catalog_api_retains_demo_and_validates_pagination(self):
        client = TestClient(app)
        self.assertEqual(client.get("/v2/products?limit=0").status_code, 422)
        self.assertEqual(len(client.get("/v2/products?limit=1").json()), 1)
        self.assertEqual(client.get("/v2/products/lookup?barcode=000000000002").json()["product_id"], "demo-bar")


class UsdaImportTests(unittest.TestCase):
    def test_usda_gram_code_is_normalized(self):
        source = source_record()
        source["servingSizeUnit"] = "GRM"
        p = normalize_usda_food(source)
        self.assertEqual(p.processing_metadata["serving_unit"], "g")
        self.assertEqual(p.nutrition.calories, 180)

    def test_source_is_normalized_without_claiming_allergen_verification(self):
        p = normalize_usda_food(source_record())
        self.assertEqual(p.nutrition.calories, 180)
        self.assertEqual(p.barcode, "001234567890")
        self.assertEqual(p.product_id, "usda-123")
        self.assertFalse(p.allergen_info_complete)
        self.assertFalse(p.provenance.verified)
        self.assertTrue(p.provenance.retrieved_at)
        self.assertEqual(p.diet_flags, [])

    def test_per_100g_values_convert_to_declared_serving(self):
        source = source_record()
        del source["labelNutrients"]["protein"]
        source["foodNutrients"] = [{"nutrient": {"id": 1003, "unitName": "g"}, "amount": 20}]
        self.assertEqual(normalize_usda_food(source).nutrition.protein_g, 8)

    def test_missing_sugar_is_not_invented_as_zero(self):
        source = source_record()
        del source["labelNutrients"]["sugars"]
        with self.assertRaisesRegex(ValueError, "sugar_g"):
            normalize_usda_food(source)

    def test_liquid_requires_per_serving_values(self):
        source = source_record()
        source["servingSizeUnit"] = "ml"
        del source["labelNutrients"]["protein"]
        source["foodNutrients"] = [{"nutrient": {"id": 1003, "unitName": "g"}, "amount": 20}]
        with self.assertRaisesRegex(ValueError, "liquid"):
            normalize_usda_food(source)

    def test_no_key_has_no_network_or_fallback_import(self):
        with patch.dict("os.environ", {"USDA_API_KEY": ""}), patch("app.services.usda_catalog.requests.get") as get:
            with self.assertRaises(SourceUnavailable):
                fetch_usda_food(123)
            get.assert_not_called()

    def test_exact_source_id_is_checked(self):
        response = Mock()
        response.json.return_value = source_record()
        with patch.dict("os.environ", {"USDA_API_KEY": "test"}), patch("app.services.usda_catalog.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "different product"):
                fetch_usda_food(456)
