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

    def test_database_readiness(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ready": True, "database": "sqlite"})

    def test_readiness_failure_hides_connection_details(self):
        with patch("app.main.database_readiness", side_effect=RuntimeError("private connection details")):
            response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.text)

    def test_demo_profile_get_and_update(self):
        updated = self.client.put(
            "/profile/demo-user",
            json={"goal": "muscle gain", "diet": "high protein", "allergies": ["peanuts"], "disliked_foods": ["olives"], "budget": "120/week", "preferred_store": "Instacart", "training_days": 4, "equipment": ["dumbbells"], "calorie_target": 2400},
        )
        fetched = self.client.get("/profile/demo-user")

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(fetched.json()["goal"], "muscle gain")
        self.assertEqual(fetched.json()["training_days"], 4)
        self.assertEqual(fetched.json()["allergies"], ["peanuts"])

    def test_persistent_bag_add_get_and_clear(self):
        self.client.delete("/bag/demo-user/clear")
        added = self.client.post("/bag/demo-user/add", json={"product": PRODUCT_A, "quantity": 2})
        fetched = self.client.get("/bag/demo-user")
        cleared = self.client.delete("/bag/demo-user/clear")

        self.assertEqual(added.status_code, 200)
        self.assertEqual(fetched.json()["count"], 1)
        self.assertEqual(fetched.json()["items"][0]["quantity"], 2)
        self.assertEqual(cleared.json()["items"], [])

    def test_saved_meal_and_workout_plans(self):
        meal = self.client.post("/plans/demo-user/meal", json={"plan": {"summary": "Saved meal plan", "days": []}})
        workout = self.client.post("/plans/demo-user/workout", json={"plan": {"summary": "Saved workout", "weekly_split": []}})
        plans = self.client.get("/plans/demo-user")

        self.assertEqual(meal.status_code, 200)
        self.assertEqual(workout.status_code, 200)
        self.assertTrue(any(item["plan"]["summary"] == "Saved meal plan" for item in plans.json()["meal_plans"]))
        self.assertTrue(any(item["plan"]["summary"] == "Saved workout" for item in plans.json()["workout_plans"]))

    def test_product_explain(self):
        response = self.client.post(
            "/product/explain",
            json={"product": PRODUCT_A, "goal": "high protein"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"]["name"], PRODUCT_A["name"])
        self.assertIsInstance(response.json()["score"], int)

    def test_product_scan_from_label_text(self):
        response = self.client.post(
            "/product/scan",
            json={
                "label_text": "Protein Oat Bar\nGood Foods\nCalories 190\nProtein 10g\nFiber 6g\nSugar 5g\nSodium 180mg\nIngredients: oats, almonds, dates"
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["product"]["name"], "Protein Oat Bar")
        self.assertEqual(payload["product"]["nutrition"]["fiber_g"], 6)
        self.assertEqual(payload["extraction_mode"], "label_text")

    def test_workout_plan(self):
        response = self.client.post(
            "/workout-plan",
            json={
                "goal": "muscle gain",
                "days_per_week": 4,
                "equipment": ["dumbbells", "gym"],
                "experience_level": "beginner",
                "limitations": [],
                "session_minutes": 60,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["weekly_split"]), 4)
        self.assertIn("progression_notes", response.json())

    def test_coach_client_plan(self):
        response = self.client.post(
            "/coach/client-plan",
            json={
                "client_name": "Demo Client",
                "goal": "fat loss",
                "diet": "high protein",
                "allergies": [],
                "days_per_week": 4,
                "equipment": ["gym"],
                "calorie_target": 2200,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["client_name"], "Demo Client")
        self.assertIn("nutrition_plan", payload)
        self.assertIn("workout_plan", payload)
        self.assertIn("shopping_strategy", payload)
        self.assertIn("profile_id", payload["persistence"])

    def test_coach_profiles_and_plan_history_persist(self):
        created = self.client.post(
            "/coach/client-plan",
            json={"client_name": "Persistent Demo Client", "goal": "muscle gain", "days_per_week": 3, "equipment": ["dumbbells"]},
        ).json()
        client_id = created["persistence"]["profile_id"]

        clients = self.client.get("/coach/clients")
        plans = self.client.get(f"/coach/clients/{client_id}/plans")

        self.assertEqual(clients.status_code, 200)
        self.assertTrue(any(client["id"] == client_id for client in clients.json()["clients"]))
        self.assertEqual(plans.status_code, 200)
        self.assertGreaterEqual(plans.json()["count"], 1)

    def test_checkout_prepare_and_retrieve(self):
        response = self.client.post(
            "/checkout/prepare",
            json={
                "retailer": "Demo Market",
                "shopping_list": {"categories": {"produce": [{"name": "berries", "quantity": "1 box"}], "protein": ["Greek yogurt"]}},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["item_count"], 2)
        self.assertEqual(payload["status"], "prepared")
        retrieved = self.client.get(f"/checkout/{payload['checkout_id']}")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(retrieved.json()["checkout_id"], payload["checkout_id"])

    def test_mock_instacart_checkout_uses_persistent_bag(self):
        self.client.delete("/bag/demo-user/clear")
        self.client.post("/bag/demo-user/add", json={"product": PRODUCT_A, "quantity": 1})
        response = self.client.post("/checkout/instacart", json={"user_id": "demo-user"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checkout_provider"], "instacart")
        self.assertEqual(response.json()["status"], "mock_ready")
        self.assertEqual(response.json()["checkout_url"], "https://www.instacart.com/store/partner_recipe_mock")
        self.assertEqual(len(response.json()["items"]), 1)

    def test_trainer_client_create_and_save_plan(self):
        client = self.client.post("/coach/clients", json={"client_name": "Phase 4 Client", "goal": "strength", "diet": "balanced", "days_per_week": 3, "equipment": ["gym"], "calorie_target": 2300})
        client_id = client.json()["id"]
        saved = self.client.post(f"/coach/clients/{client_id}/plans", json={"plan": {"summary": "Trainer saved plan"}})
        plans = self.client.get(f"/coach/clients/{client_id}/plans")

        self.assertEqual(client.status_code, 200)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(any(item["plan"]["summary"] == "Trainer saved plan" for item in plans.json()["plans"]))

    def test_copilot_can_load_demo_user_memory(self):
        self.client.delete("/bag/demo-user/clear")
        self.client.post("/bag/demo-user/add", json={"product": PRODUCT_B, "quantity": 1})
        response = self.client.post("/copilot/chat", json={"message": "Optimize my bag", "user_id": "demo-user", "load_memory": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "optimize_bag")
        self.assertIn("profile", response.json()["context_used"])
        self.assertEqual(response.json()["context_used"]["bag"][0]["name"], PRODUCT_B["name"])

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
        context = {"goal": "high protein", "product": PRODUCT_B, "bag": [PRODUCT_A, PRODUCT_B]}
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post(
                "/copilot/chat",
                json={"message": "Should I swap this snack?", "context": context},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "optimize_bag")
        self.assertEqual(response.json()["context_used"], context)
        self.assertIn("bag", response.json()["response"].lower())
        self.assertEqual(response.json()["mode"], "tool")
        self.assertIn("suggested_actions", response.json())
        self.assertIn("tool_result", response.json())

    def test_context_copilot_acceptance_routes_return_structured_json(self):
        cases = [
            ("Why is this product score low?", {"product": PRODUCT_B}, "explain_product"),
            ("Compare these two products", {"products": [PRODUCT_A, PRODUCT_B]}, "compare_products"),
            ("Optimize my bag", {"bag": [PRODUCT_A, PRODUCT_B]}, "optimize_bag"),
            ("Build a 4 day workout plan", {"goal": "muscle gain", "equipment": ["gym"]}, "workout_plan"),
            ("Create a trainer client plan", {"client_name": "Demo Client", "goal": "fat loss"}, "client_plan"),
            ("Prepare checkout", {"shopping_list": {"categories": {"produce": ["berries"]}}}, "prepare_checkout"),
        ]
        with patch.dict("os.environ", {}, clear=True):
            for message, context, expected_intent in cases:
                with self.subTest(message=message):
                    response = self.client.post(
                        "/copilot/chat",
                        json={"message": message, "context": context},
                    )
                    payload = response.json()
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(payload["intent"], expected_intent)
                    self.assertIsInstance(payload["response"], str)
                    self.assertIsInstance(payload["suggested_actions"], list)
                    self.assertIsInstance(payload["tool_result"], dict)

    @patch("app.main.run_ai", return_value="Choose the yogurt for more protein and less sugar.")
    def test_context_copilot_falls_back_to_openai_when_tool_context_is_missing(self, mocked_run_ai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            response = self.client.post(
                "/copilot/chat",
                json={"message": "Compare this product", "context": {"product": PRODUCT_A}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "general_chat")
        self.assertEqual(response.json()["mode"], "routing_fallback")
        mocked_run_ai.assert_called_once()

    @patch(
        "app.main.run_ai",
        return_value='{"summary":"Five-day plan","days":[],"notes":[]}',
    )
    def test_context_copilot_routes_meal_plan(self, mocked_run_ai):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            response = self.client.post(
                "/copilot/chat",
                json={"message": "Build me a 5 day meal plan", "context": {"goal": "high protein"}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "meal_plan")
        self.assertEqual(response.json()["tool_result"]["summary"], "Five-day plan")
        mocked_run_ai.assert_called_once()


if __name__ == "__main__":
    unittest.main()
