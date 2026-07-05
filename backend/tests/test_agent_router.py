import unittest

from app.agent import CopilotRouter


YOGURT = {
    "name": "Plain Greek Yogurt",
    "nutrition": {"calories": 120, "protein_g": 17, "fiber_g": 0, "sugar_g": 5, "sodium_mg": 65},
    "ingredients": ["cultured milk"],
}

SNACK_BAR = {
    "name": "Frosted Snack Bar",
    "nutrition": {"calories": 260, "protein_g": 3, "fiber_g": 1, "sugar_g": 24, "sodium_mg": 310},
    "ingredients": ["oats", "corn syrup"],
}


class CopilotRouterTests(unittest.TestCase):
    def setUp(self):
        self.meal_requests = []
        self.router = CopilotRouter(
            ai_runner=lambda instructions, prompt: "General nutrition guidance.",
            meal_plan_tool=self.build_meal_plan,
            shopping_list_tool=lambda meal_plan, servings: {
                "servings": servings,
                "categories": {"produce": ["berries"]},
            },
        )

    def build_meal_plan(self, request):
        self.meal_requests.append(request)
        return {"summary": "Five-day high-protein plan", "days": [{"day": 1, "meals": []}]}

    def test_routes_product_explanation(self):
        result = self.router.route("Why is this product score low?", {"product": SNACK_BAR})

        self.assertEqual(result["intent"], "explain_product")
        self.assertEqual(result["tool_result"]["product"]["name"], "Frosted Snack Bar")
        self.assertTrue(result["suggested_actions"])

    def test_routes_product_comparison(self):
        result = self.router.route("Compare these two products", {"products": [YOGURT, SNACK_BAR]})

        self.assertEqual(result["intent"], "compare_products")
        self.assertEqual(result["tool_result"]["winner"]["name"], "Plain Greek Yogurt")

    def test_routes_bag_optimization(self):
        result = self.router.route("Optimize my bag", {"bag": [YOGURT, SNACK_BAR]})

        self.assertEqual(result["intent"], "optimize_bag")
        self.assertGreaterEqual(result["tool_result"]["projected_score"], result["tool_result"]["current_score"])

    def test_routes_five_day_meal_plan(self):
        result = self.router.route("Build me a 5 day meal plan", {"goal": "high protein"})

        self.assertEqual(result["intent"], "meal_plan")
        self.assertEqual(self.meal_requests[0]["days"], 5)
        self.assertEqual(result["tool_result"]["summary"], "Five-day high-protein plan")

    def test_routes_shopping_list(self):
        result = self.router.route(
            "Make a shopping list",
            {"meal_plan": {"days": []}, "servings": 2},
        )

        self.assertEqual(result["intent"], "shopping_list")
        self.assertEqual(result["tool_result"]["servings"], 2)

    def test_routing_failure_falls_back_to_general_chat(self):
        result = self.router.route("Compare these two products", {"product": YOGURT})

        self.assertEqual(result["intent"], "general_chat")
        self.assertEqual(result["mode"], "routing_fallback")
        self.assertEqual(result["response"], "General nutrition guidance.")

    def test_failed_chat_falls_back_deterministically(self):
        router = CopilotRouter(ai_runner=lambda instructions, prompt: (_ for _ in ()).throw(RuntimeError("offline")))

        result = router.route("Tell me something useful", {"goal": "balanced nutrition"})

        self.assertEqual(result["intent"], "general_chat")
        self.assertEqual(result["mode"], "routing_fallback")
        self.assertIn("product scores", result["response"])


if __name__ == "__main__":
    unittest.main()
