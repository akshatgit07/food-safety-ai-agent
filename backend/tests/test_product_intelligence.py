import unittest

from app.db import BagItem, ClientPlanRecord, CoachClient, CopilotMessage, MealPlanRecord, ProductRecord, ScanHistory, User, UserPreference, WorkoutPlanRecord
from app.services.bag_optimizer import optimize_bag
from app.services.copilot_router import detect_intent
from app.services.label_scanner import parse_label_text, scan_label
from app.services.action_recommender import recommend_actions
from app.services.coach_planner import build_client_plan
from app.services.workout_planner import build_workout_plan
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
    def test_phase4_database_models_are_registered(self):
        self.assertEqual(
            {model.__tablename__ for model in [User, UserPreference, ProductRecord, ScanHistory, BagItem, MealPlanRecord, WorkoutPlanRecord, CoachClient, ClientPlanRecord, CopilotMessage]},
            {"users", "user_preferences", "products", "scan_history", "bag_items", "meal_plans", "workout_plans", "coach_clients", "client_plans", "copilot_messages"},
        )

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

    def test_label_text_parser_extracts_product_nutrition(self):
        result = parse_label_text(
            "Protein Oat Bar\nGood Foods\nCalories 190\nProtein 10g\nDietary Fiber 6g\nTotal Sugars 5g\nSodium 180mg\nIngredients: oats, almonds, dates"
        )

        self.assertEqual(result["product"]["name"], "Protein Oat Bar")
        self.assertEqual(result["product"]["nutrition"]["protein_g"], 10)
        self.assertEqual(result["product"]["ingredients"], ["oats", "almonds", "dates"])
        self.assertEqual(result["extraction_mode"], "label_text")

    def test_image_scan_has_deployable_demo_fallback(self):
        result = scan_label(image_data_url="data:image/png;base64,demo")

        self.assertEqual(result["extraction_mode"], "demo_fallback")
        self.assertIn("nutrition", result["product"])
        self.assertTrue(result["warnings"])

    def test_workout_plan_matches_requested_frequency(self):
        result = build_workout_plan({"goal": "muscle gain", "days_per_week": 4, "equipment": ["dumbbells", "gym"]})

        self.assertEqual(len(result["weekly_split"]), 4)
        self.assertTrue(result["weekly_split"][0]["exercises"])

    def test_coach_plan_connects_nutrition_training_and_shopping(self):
        result = build_client_plan({"client_name": "Demo Client", "goal": "fat loss", "days_per_week": 4, "calorie_target": 2200})

        self.assertEqual(result["client_name"], "Demo Client")
        self.assertIn("nutrition_plan", result)
        self.assertIn("workout_plan", result)
        self.assertIn("shopping_strategy", result)

    def test_action_recommender_uses_current_context(self):
        actions = recommend_actions({"product": SUGARY_SNACK, "bag": [SUGARY_SNACK]}, "explain_product")

        self.assertIn("explain_score", actions)
        self.assertIn("compare_alternatives", actions)
        self.assertIn("optimize_bag", actions)


if __name__ == "__main__":
    unittest.main()
