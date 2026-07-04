import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


PRODUCT_A = {
    "name": "Plain Greek Yogurt",
    "brand": "Daily Cultures",
    "category": "Yogurt",
    "nutrition": {
        "calories": 120,
        "protein_g": 17,
        "fiber_g": 0,
        "sugar_g": 5,
        "sodium_mg": 65,
    },
    "ingredients": ["cultured milk"],
}

PRODUCT_B = {
    "name": "Frosted Snack Bar",
    "brand": "Quick Bite",
    "category": "Snack bar",
    "nutrition": {
        "calories": 260,
        "protein_g": 3,
        "fiber_g": 1,
        "sugar_g": 24,
        "sodium_mg": 310,
    },
    "ingredients": ["oats", "corn syrup", "artificial flavor"],
}


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"healthy": True})

    def test_product_explain(self):
        response = self.client.post(
            "/product/explain",
            json={"product": PRODUCT_A, "goal": "high protein"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"]["name"], PRODUCT_A["name"])
        self.assertIsInstance(response.json()["score"], int)

    def test_product_compare(self):
        response = self.client.post(
            "/product/compare",
            json={"products": [PRODUCT_A, PRODUCT_B], "goal": "balanced nutrition"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["winner"]["name"], PRODUCT_A["name"])

    def test_bag_optimize(self):
        response = self.client.post(
            "/bag/optimize",
            json={"items": [PRODUCT_A, PRODUCT_B], "goal": "balanced nutrition"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["projected_score"], response.json()["current_score"])
        self.assertIsInstance(response.json()["swaps"], list)

    @patch("app.main.run_ai", return_value="Greek yogurt is a practical high-protein option.")
    def test_existing_chat_endpoint(self, mocked_run_ai):
        response = self.client.post("/chat", json={"message": "Is Greek yogurt useful after training?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("high-protein", response.json()["response"])
        mocked_run_ai.assert_called_once()

    @patch(
        "app.main.run_ai",
        return_value='{"summary":"Simple plan","days":[{"day":1,"meals":[{"name":"Yogurt bowl","ingredients":["greek yogurt","berries"],"estimated_calories":200,"estimated_protein_g":18}]}],"notes":[]}',
    )
    def test_existing_meal_plan_endpoint(self, mocked_run_ai):
        response = self.client.post("/meal-plan", json={"days": 1, "meals_per_day": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "Simple plan")
        self.assertIn("nutrition_grounding", response.json())
        mocked_run_ai.assert_called_once()

    @patch(
        "app.main.run_ai",
        return_value='{"servings":1,"categories":{"produce":[{"name":"berries","quantity":"1 cup"}]},"notes":[]}',
    )
    def test_existing_shopping_list_endpoint(self, mocked_run_ai):
        response = self.client.post(
            "/shopping-list",
            json={"meal_plan": {"days": []}, "servings": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["categories"]["produce"][0]["name"], "berries")
        mocked_run_ai.assert_called_once()

    def test_context_copilot_has_deterministic_fallback(self):
        context = {"goal": "high protein", "product": PRODUCT_A, "bag": [PRODUCT_B]}
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post(
                "/copilot/chat",
                json={"message": "Should I swap this snack?", "context": context},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "optimize_bag")
        self.assertEqual(response.json()["context_used"], context)
        self.assertIn("yogurt", response.json()["response"].lower())
        self.assertEqual(response.json()["mode"], "deterministic_fallback")

    @patch("app.main.run_ai", return_value="Choose the yogurt for more protein and less sugar.")
    def test_context_copilot_uses_openai_when_configured(self, mocked_run_ai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            response = self.client.post(
                "/copilot/chat",
                json={"message": "Compare this product", "context": {"product": PRODUCT_A}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "openai")
        mocked_run_ai.assert_called_once()


if __name__ == "__main__":
    unittest.main()
