"""Regression tests for the Phase 4 personalization review.

Each test pins a defect reproduced against the pre-review code.
"""

import threading
import unittest

from app.domain.models import DailyNutritionState, Product, UserProfile
from app.services.g_personal import hard_constraint_failures, score_product
from app.services.product_lookup import (
    MemoryCache,
    MemoryProductRepository,
    ProductLookup,
    demo_catalog,
)
from app.services.product_retriever import LocalCandidateRetriever, find_alternatives, relevance


def product(name="Test Item", ingredients=(), allergens=(), category="Snack", **changes):
    return Product.model_validate({
        "product_id": changes.pop("product_id", "test"),
        "name": name,
        "category": category,
        "nutrition": {"calories": 150, "protein_g": 6, "carbs_g": 20, "fat_g": 5,
                      "fiber_g": 3, "sugar_g": 4, "sodium_mg": 120},
        "ingredients": list(ingredients),
        "allergens": list(allergens),
        "allergen_info_complete": True,
        "provenance": {"source": "test fixture"},
        **changes,
    })


class AllergenDetectionTests(unittest.TestCase):
    """Whole-word matching passed 7 of 9 derived allergen forms as safe."""

    DERIVED = [
        ("milk", ["sodium caseinate", "sugar"]),
        ("milk", ["buttermilk powder"]),
        ("milk", ["lactose", "cocoa"]),
        ("milk", ["ghee", "spices"]),
        ("milk", ["milkfat"]),
        ("milk", ["whey protein concentrate"]),
        ("peanut", ["arachis oil"]),
        ("peanut", ["groundnuts"]),
        ("soy", ["bean curd"]),
        ("gluten", ["seitan"]),
        ("egg", ["ovalbumin"]),
        ("fish", ["surimi"]),
        ("tree nut", ["marzipan"]),
    ]

    def test_derived_allergen_forms_are_blocked(self):
        for allergen, ingredients in self.DERIVED:
            with self.subTest(allergen=allergen, ingredients=ingredients):
                failures = hard_constraint_failures(
                    product(ingredients=ingredients), UserProfile(allergies=[allergen])
                )
                self.assertTrue(failures, f"{ingredients} passed a {allergen} allergy check")

    def test_product_name_is_scanned(self):
        """An incomplete ingredient list must not hide the allergen in the name."""
        failures = hard_constraint_failures(
            product(name="Peanut Butter Cups", ingredients=["sugar", "cocoa", "palm oil"]),
            UserProfile(allergies=["peanut"]),
        )
        self.assertTrue(failures)

    HOMONYMS = [
        ("egg", "Veggie Burger", ["veggie patty", "vegetables"]),
        ("egg", "Eggplant Dip", ["eggplant", "olive oil"]),
        ("milk", "Coconut Curry", ["coconut milk", "spices"]),
        ("milk", "Oat Latte", ["oat milk", "coffee"]),
        ("milk", "Dark Chocolate", ["cocoa butter", "cocoa mass"]),
        ("milk", "Seed Spread", ["sunflower butter", "salt"]),
        ("gluten", "GF Oat Bar", ["certified gluten-free oats", "pea protein"]),
        ("gluten", "Corn Snack", ["maltodextrin", "corn"]),
        ("tree nut", "Coconut Chips", ["coconut", "salt"]),
        ("tree nut", "Spiced Squash", ["butternut squash", "nutmeg"]),
        ("peanut", "Almond Cup", ["almond butter", "cocoa"]),
    ]

    def test_homonyms_do_not_over_block(self):
        """Substring matching must not turn 'veggie' into egg or 'gluten-free' into gluten."""
        for allergen, name, ingredients in self.HOMONYMS:
            with self.subTest(allergen=allergen, name=name):
                failures = hard_constraint_failures(
                    product(name=name, ingredients=ingredients), UserProfile(allergies=[allergen])
                )
                self.assertEqual(failures, [], f"{name} was wrongly blocked for {allergen}")

    def test_demo_catalog_blocks_exactly_the_unsafe_products(self):
        catalog = demo_catalog()
        blocked = lambda allergy: sorted(
            p.product_id for p in catalog
            if hard_constraint_failures(p, UserProfile(allergies=[allergy]))
        )
        self.assertEqual(blocked("milk"), ["demo-bar", "demo-yogurt"])
        # demo-oat-bar lists "certified gluten-free oats" and must stay eligible.
        self.assertEqual(blocked("gluten"), ["demo-bar"])
        self.assertEqual(blocked("peanut"), [])

    def test_incomplete_allergen_data_still_fails_closed(self):
        failures = hard_constraint_failures(
            product(ingredients=["sugar"], allergen_info_complete=False),
            UserProfile(allergies=["milk"]),
        )
        self.assertTrue(failures)

    def test_avoided_ingredients_also_match_derived_forms(self):
        failures = hard_constraint_failures(
            product(ingredients=["sodium caseinate"]),
            UserProfile(ingredients_to_avoid=["casein"]),
        )
        self.assertTrue(failures)


class CrossCategoryRetrievalTests(unittest.TestCase):
    """Token overlap alone returned zero alternatives across categories."""

    def setUp(self):
        self.catalog = demo_catalog()
        self.retriever = LocalCandidateRetriever(self.catalog)
        self.daily = DailyNutritionState()

    def test_safe_alternatives_surface_across_categories(self):
        yogurt = next(p for p in self.catalog if p.product_id == "demo-yogurt")
        alternatives = find_alternatives(
            yogurt, UserProfile(allergies=["milk"]), self.daily, self.retriever, "find me a swap"
        )
        returned = {a["product"]["product_id"] for a in alternatives}
        self.assertEqual(returned, {"demo-chickpeas", "demo-oat-bar"})

    def test_same_category_still_ranks_first(self):
        bar = next(p for p in self.catalog if p.product_id == "demo-bar")
        alternatives = find_alternatives(bar, UserProfile(), self.daily, self.retriever, "swap")
        self.assertEqual(alternatives[0]["product"]["product_id"], "demo-oat-bar")
        self.assertGreater(alternatives[0]["semantic_similarity"], 0.5)

    def test_weak_matches_are_reported_as_weak(self):
        yogurt = next(p for p in self.catalog if p.product_id == "demo-yogurt")
        chickpeas = next(p for p in self.catalog if p.product_id == "demo-chickpeas")
        self.assertLess(relevance(yogurt, chickpeas, ""), 0.2)
        self.assertGreater(relevance(yogurt, chickpeas, ""), 0)

    def test_hard_constraints_still_remove_unsafe_candidates(self):
        """The floor must not let an incompatible product become an alternative."""
        yogurt = next(p for p in self.catalog if p.product_id == "demo-yogurt")
        alternatives = find_alternatives(
            yogurt, UserProfile(allergies=["milk", "gluten"]), self.daily, self.retriever, "swap"
        )
        returned = {a["product"]["product_id"] for a in alternatives}
        self.assertNotIn("demo-bar", returned)
        for alternative in alternatives:
            self.assertEqual(alternative["scoring"]["compatibility"], "compatible")


class ScoreExplanationTests(unittest.TestCase):
    def test_reason_accounts_for_the_over_target_penalty(self):
        """The impact folded in an excess penalty the reason never mentioned."""
        bar = product()
        bar.nutrition.protein_g = 14
        result = score_product(
            bar, UserProfile(protein_target=150), DailyNutritionState(protein_consumed=145)
        )
        factor = next(f for f in result.drivers + result.penalties if f.factor == "remaining_protein")
        self.assertLess(factor.impact, 0)
        self.assertIn("over the remaining need", factor.reason)
        # 12 * 5/150 - min(6, 12*9/150) == 0.4 - 0.72
        self.assertAlmostEqual(factor.impact, -0.32, places=3)

    def test_scoring_is_reproducible(self):
        profile = UserProfile(protein_target=150, micronutrient_targets={"calcium_mg": 1000, "iron_mg": 18})
        item = product()
        item.nutrition.micronutrients = {"calcium_mg": 200, "iron_mg": 4}
        scores = {score_product(item, profile, DailyNutritionState()).personal_score for _ in range(50)}
        self.assertEqual(len(scores), 1)


class CacheConcurrencyTests(unittest.TestCase):
    def test_shared_cache_survives_concurrent_use(self):
        """The cache is a module-level singleton and FastAPI runs sync endpoints
        on a threadpool, so unguarded OrderedDict mutation was a live race."""
        lookup = ProductLookup(MemoryProductRepository(demo_catalog()), MemoryCache(capacity=8))
        failures: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait()
                for index in range(200):
                    lookup.find(product_id="demo-yogurt")
                    lookup.find(barcode="000000000002")
                    lookup.cache.put(f"id:filler{index}", lookup.find(product_id="demo-bar"))
            except BaseException as exc:  # noqa: BLE001 - asserted below
                failures.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [])
        self.assertLessEqual(len(lookup.cache.items), lookup.cache.capacity)


class IntentGroundingTests(unittest.TestCase):
    """A resolved identifier is a stronger intent signal than the phrasing."""

    NATURAL_PHRASINGS = ["explain", "is this good for me?", "what do you think",
                         "Explain score", "why is this low"]

    def test_exact_identifier_always_grounds_the_answer(self):
        from fastapi.testclient import TestClient
        import app.main as main

        client = TestClient(main.app)
        for message in self.NATURAL_PHRASINGS:
            with self.subTest(message=message):
                body = client.post(
                    "/v2/copilot/chat", json={"message": message, "product_id": "demo-bar"}
                ).json()
                self.assertEqual(body["intent"], "explain_product")
                self.assertEqual(body["grounding"]["product_ids"], ["demo-bar"])

    def test_other_intents_are_not_hijacked_by_a_product_id(self):
        from fastapi.testclient import TestClient
        import app.main as main

        body = TestClient(main.app).post(
            "/v2/copilot/chat", json={"message": "find me a swap", "product_id": "demo-bar"}
        ).json()
        self.assertEqual(body["intent"], "find_swap")

    def test_missing_product_still_reports_the_lookup_failure(self):
        from fastapi.testclient import TestClient
        import app.main as main

        body = TestClient(main.app).post(
            "/v2/copilot/chat", json={"message": "explain", "product_id": "not-real"}
        ).json()
        self.assertTrue(body["errors"])
        self.assertEqual(body["tool_result"], {})


class GraphReuseTests(unittest.TestCase):
    def test_v2_graph_is_compiled_once(self):
        """StateGraph.compile() ran on every request."""
        from app.agents.guiltless_graph import GuiltlessGraph
        import app.main as main

        self.assertIsInstance(main._guiltless_graph, GuiltlessGraph)
        builds = []
        original = GuiltlessGraph.__init__

        def counted(self, *args, **kwargs):
            builds.append(1)
            return original(self, *args, **kwargs)

        GuiltlessGraph.__init__ = counted
        try:
            from fastapi.testclient import TestClient

            client = TestClient(main.app)
            for _ in range(5):
                client.post("/v2/copilot/chat", json={"message": "Explain score", "product_id": "demo-bar"})
        finally:
            GuiltlessGraph.__init__ = original
        self.assertEqual(builds, [])


if __name__ == "__main__":
    unittest.main()
