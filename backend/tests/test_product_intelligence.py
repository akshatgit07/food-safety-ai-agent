import unittest

from app.services.bag_optimizer import optimize_bag
from app.services.copilot_router import detect_intent
from app.services.product_intelligence import compare_products, explain_product


HIGH_PROTEIN_YOGURT = {
    "name": "Plain Greek Yogurt",
    "nutrition": {
        "calories": 120,
        "protein_g": 17,
        "fiber_g": 0,
        "sugar_g": 5,
        "sodium_mg": 65,
    },
    "ingredients": ["cultured milk"],
}

SUGARY_SNACK = {
    "name": "Frosted Snack Bar",
    "nutrition": {
        "calories": 260,
        "protein_g": 3,
        "fiber_g": 1,
        "sugar_g": 24,
        "sodium_mg": 310,
    },
    "ingredients": ["corn syrup", "artificial flavor"],
}


class ProductIntelligenceTests(unittest.TestCase):
    def test_explanation_rewards_goal_aligned_product(self):
        result = explain_product(HIGH_PROTEIN_YOGURT, "high protein")

        self.assertGreaterEqual(result["score"], 80)
        self.assertIn("Fits a high-protein goal", result["goal_fit"])

    def test_comparison_selects_higher_scoring_product(self):
        result = compare_products([SUGARY_SNACK, HIGH_PROTEIN_YOGURT], "balanced nutrition")

        self.assertEqual(result["winner"]["name"], "Plain Greek Yogurt")
        self.assertEqual(len(result["products"]), 2)

    def test_bag_optimizer_suggests_improvements(self):
        result = optimize_bag([SUGARY_SNACK, HIGH_PROTEIN_YOGURT])

        self.assertEqual(len(result["swaps"]), 1)
        self.assertGreater(result["projected_score"], result["current_score"])

    def test_bag_optimizer_tolerates_non_numeric_nutrition(self):
        malformed = {
            "name": "Incomplete label",
            "nutrition": {"sugar_g": "unknown", "fiber_g": None},
        }

        result = optimize_bag([malformed])

        self.assertEqual(len(result["items"]), 1)
        self.assertGreaterEqual(result["projected_score"], result["current_score"])

    def test_copilot_routes_product_workflows(self):
        self.assertEqual(detect_intent("Compare these two yogurts"), "compare_products")
        self.assertEqual(detect_intent("Optimize my cart"), "optimize_bag")


if __name__ == "__main__":
    unittest.main()
