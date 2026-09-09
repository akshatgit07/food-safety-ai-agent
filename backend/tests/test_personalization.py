import unittest
from unittest.mock import Mock, patch

from app.domain.models import DailyNutritionState, Product, UserProfile
from app.services.g_personal import score_product
from app.services.product_lookup import MemoryCache, MemoryProductRepository, ProductLookup
from app.services.product_retriever import LocalCandidateRetriever, find_alternatives
from app.services.product_lookup import demo_catalog
from app.agent import CopilotRouter
from app.agents.guiltless_graph import GuiltlessGraph
from fastapi.testclient import TestClient
from app.main import app
from app.services.result_validator import validate_result, validate_composition
from app.services.personalized_tools import scored


def product(**changes):
    return Product.model_validate({"product_id": "test", "name": "Protein snack", "nutrition": {"calories": 180, "protein_g": 16, "fiber_g": 4, "sugar_g": 8, "sodium_mg": 280, "micronutrients": {"calcium_mg": 200}}, "ingredients": ["oats"], "allergen_info_complete": True, "diet_flags": ["vegan"], "provenance": {"source": "test fixture"}, **changes})


class ScoringTests(unittest.TestCase):
    def test_allergy_is_rejection_not_score_penalty(self):
        result = score_product(product(ingredients=["whey"]), UserProfile(allergies=["milk"]), DailyNutritionState())
        self.assertEqual(result.compatibility, "incompatible")
        self.assertIsNone(result.personal_score)

    def test_protein_need_decreases_as_target_is_met(self):
        profile = UserProfile(primary_goal="muscle gain", protein_target=120)
        hungry = score_product(product(), profile, DailyNutritionState())
        full = score_product(product(), profile, DailyNutritionState(protein_consumed=119))
        neutral = score_product(product(), UserProfile(), DailyNutritionState())
        self.assertGreater(hungry.personal_score, full.personal_score)
        self.assertGreater(hungry.personal_score, neutral.personal_score)

    def test_micronutrient_gap_and_reproducibility(self):
        profile = UserProfile(micronutrient_targets={"calcium_mg": 1000})
        result = score_product(product(), profile, DailyNutritionState())
        self.assertEqual(result, score_product(product(), profile, DailyNutritionState()))
        self.assertGreater(result.personal_score, score_product(product(), profile, DailyNutritionState(micronutrients_consumed={"calcium_mg": 1000})).personal_score)

    def test_vegan_claim_cannot_override_milk_ingredient(self):
        self.assertEqual(score_product(product(ingredients=["milk"]), UserProfile(dietary_preferences=["vegan"]), DailyNutritionState()).compatibility, "incompatible")

    def test_unknown_allergen_information_is_excluded(self):
        self.assertEqual(score_product(product(allergen_info_complete=False), UserProfile(allergies=["peanuts"]), DailyNutritionState()).compatibility, "incompatible")


class RetrievalTests(unittest.TestCase):
    def test_barcode_is_exact_cached_and_never_uses_semantics(self):
        repo = Mock(wraps=MemoryProductRepository([product(barcode="00123")]))
        lookup = ProductLookup(repo, MemoryCache())
        with patch.object(LocalCandidateRetriever, "retrieve", side_effect=AssertionError("No semantic lookup")):
            self.assertEqual(lookup.find(barcode="00123").product_id, "test")
            lookup.find(barcode="00123")
            repo.by_barcode.assert_called_once_with("00123")
            self.assertIsNone(lookup.find(barcode="123"))

    def test_unsafe_candidates_never_reach_reranker(self):
        bad = product(product_id="bad", ingredients=["peanuts"], allergens=["peanuts"])
        nonvegan = product(product_id="milk", ingredients=["milk"], diet_flags=[])
        safe = product(product_id="safe")
        retriever = LocalCandidateRetriever([bad, nonvegan, safe])
        with patch("app.services.product_retriever.rerank", return_value=[]) as rank:
            find_alternatives(product(), UserProfile(allergies=["peanuts"], dietary_preferences=["vegan"]), DailyNutritionState(), retriever)
            self.assertEqual([p.product_id for p, s in rank.call_args.args[1]], ["safe"])


class GraphTests(unittest.TestCase):
    def test_bag_routes_to_real_catalog_swaps(self):
        catalog = demo_catalog()
        graph = GuiltlessGraph(ProductLookup(MemoryProductRepository(catalog)), LocalCandidateRetriever(catalog), CopilotRouter(), Mock())
        result = graph.run({"message": "Optimize my bag", "bag_product_ids": ["demo-bar"]})
        self.assertEqual(result["intent"], "optimize_bag")
        self.assertTrue(result["tool_result"]["swaps"])
        self.assertEqual(result["tool_result"]["swaps"][0]["alternative"]["product"]["product_id"], "demo-oat-bar")
        self.assertIn("guiltless_demo_catalog", result["grounding"]["data_sources"])


class V2ContractTests(unittest.TestCase):
    def test_response_grounding_and_exact_lookup(self):
        client = TestClient(app)
        lookup = client.get("/v2/products/lookup", params={"barcode": "000000000002"})
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["product_id"], "demo-bar")
        response = client.post("/v2/copilot/chat", json={"message": "Explain score", "product_id": "demo-bar"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["grounding"]["product_ids"], ["demo-bar"])
        self.assertLessEqual(body["confidence"], 0.3)
        self.assertEqual(body["tool_result"]["current_product"]["scoring"]["compatibility"], "compatible")

    def test_ambiguous_identifier_is_rejected(self):
        response = TestClient(app).post("/v2/copilot/chat", json={"message": "Explain", "product_id": "demo-bar", "barcode": "1"})
        self.assertEqual(response.status_code, 422)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.lookup = ProductLookup(MemoryProductRepository(demo_catalog()))
        self.daily = DailyNutritionState()

    def test_unsafe_model_recommendation_is_rejected(self):
        profile = UserProfile(allergies=["milk"])
        result = {"items": [scored(self.lookup.find(product_id="demo-yogurt"), profile, self.daily)], "recommended_product_ids": ["demo-yogurt"]}
        self.assertTrue(any("Incompatible" in error for error in validate_result(result, profile, self.daily, self.lookup)))

    def test_altered_scores_and_hallucinated_ids_are_rejected(self):
        item = scored(self.lookup.find(product_id="demo-bar"), UserProfile(), self.daily)
        item["scoring"]["personal_score"] = 100
        errors = validate_result({"items": [item], "recommended_product_ids": ["imaginary"]}, UserProfile(), self.daily, self.lookup)
        self.assertTrue(any("Scoring mismatch" in e for e in errors))
        self.assertTrue(any("imaginary" in e for e in errors))

    def test_free_text_score_changes_are_rejected(self):
        self.assertTrue(validate_composition({"response": "Score 100"}, {"response": "Score 50"}))

    def test_graph_never_returns_unvalidated_composer_output(self):
        graph = GuiltlessGraph(self.lookup, LocalCandidateRetriever(demo_catalog()), CopilotRouter(), Mock(), composer=lambda approved: {**approved, "response": "Eat peanuts; your score is 100"})
        result = graph.run({"message": "Explain score", "product_id": "demo-chickpeas"})
        self.assertTrue(result["errors"])
        self.assertEqual(result["tool_result"], {})
        self.assertNotIn("peanuts", result["response"])

    def test_malformed_result_fails_closed(self):
        self.assertTrue(validate_result({"recommended_product_ids": [[]]}, UserProfile(), self.daily, self.lookup))


class EndToEndPersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_vegan_swap_is_compatible_and_contains_grounding(self):
        result = self.client.post("/v2/copilot/chat", json={"message": "Find a swap", "product_id": "demo-bar", "user_profile": {"dietary_preferences": ["vegan"], "allergies": ["milk"]}}).json()
        self.assertFalse(result["errors"])
        self.assertEqual(result["tool_result"]["current_product"]["scoring"]["compatibility"], "incompatible")
        for alternative in result["tool_result"]["ranked_alternatives"]:
            self.assertEqual(alternative["scoring"]["compatibility"], "compatible")
            self.assertIn("vegan", alternative["product"]["diet_flags"])
            self.assertIn(alternative["product"]["product_id"], result["grounding"]["product_ids"])

    def test_missing_barcode_has_no_fuzzy_fallback(self):
        with patch.object(LocalCandidateRetriever, "retrieve", side_effect=AssertionError("Exact miss must not retrieve")):
            result = self.client.post("/v2/copilot/chat", json={"message": "Find a swap", "barcode": "missing"}).json()
        self.assertTrue(result["errors"])
        self.assertEqual(result["confidence"], 0)
        self.assertEqual(result["tool_result"], {})

    def test_saved_allergies_are_loaded(self):
        self.client.put("/profile/personalization-test", json={"allergies": ["milk"]})
        result = self.client.post("/v2/copilot/chat", json={"message": "Explain score", "product_id": "demo-yogurt", "user_id": "personalization-test", "load_memory": True}).json()
        self.assertEqual(result["tool_result"]["current_product"]["scoring"]["compatibility"], "incompatible")

    def test_duplicate_bag_products_validate(self):
        result = self.client.post("/v2/copilot/chat", json={"message": "Optimize my bag", "bag_product_ids": ["demo-bar", "demo-bar"]}).json()
        self.assertFalse(result["errors"])
        self.assertEqual(len(result["tool_result"]["swaps"]), 2)

    def test_bad_nutrition_input_is_rejected(self):
        response = self.client.post("/v2/copilot/chat", json={"message": "Explain", "daily_nutrition_state": {"protein_consumed": -1}})
        self.assertEqual(response.status_code, 422)

    def test_no_safe_alternatives_is_honest_empty_result(self):
        result = self.client.post("/v2/copilot/chat", json={"message": "Find alternative", "product_id": "demo-bar", "user_profile": {"dietary_preferences": ["unverified-diet"]}}).json()
        self.assertFalse(result["errors"])
        self.assertEqual(result["tool_result"]["ranked_alternatives"], [])
