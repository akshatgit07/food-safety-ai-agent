import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.agent import CopilotRouter
from app.agent.graph import CopilotGraph
from tests.test_agent_router import SNACK_BAR, YOGURT


class CopilotGraphTests(unittest.TestCase):
    def setUp(self):
        self.memory = Mock(return_value={
            "profile": {"goal": "muscle gain", "diet": "vegetarian", "allergies": ["peanuts"],
                        "training_days": 4, "equipment": ["gym"], "calorie_target": 2400},
            "bag": [SNACK_BAR, YOGURT],
            "recent_plans": {"meal_plans": [{"plan": {"days": []}}]},
            "recent_scans": [{"scan": {"product": SNACK_BAR}}],
            "recent_messages": [{"role": "user", "content": "I prefer quick meals"}],
        })
        self.meal = Mock(return_value={"summary": "Meal plan", "days": []})
        self.shopping = Mock(return_value={"categories": {"produce": ["berries"]}})
        self.ai = Mock(return_value="Helpful response")
        self.graph = CopilotGraph(CopilotRouter(self.ai, self.meal, self.shopping), self.memory)

    def test_saved_memory_drives_each_product_tool_without_llm(self):
        for message, intent in [("Why is this score low?", "explain_product"),
                                ("Compare these two products", "compare_products"),
                                ("Optimize my bag", "optimize_bag")]:
            with self.subTest(intent=intent):
                result = self.graph.route(message, user_id="alice", load_memory=True)
                self.assertEqual(result["intent"], intent)
                self.assertIsInstance(result["tool_result"], dict)
        self.ai.assert_not_called()
        self.memory.assert_called_with("alice")

    def test_meal_plan_uses_saved_restrictions_and_requested_duration(self):
        self.graph.route("Build me a 5 day meal plan", load_memory=True)
        request = self.meal.call_args.args[0]
        self.assertEqual(request["days"], 5)
        self.assertEqual(request["allergies"], ["peanuts"])
        self.assertEqual(request["diet"], "vegetarian")
        self.assertEqual(request["calorie_target"], 2400)

    def test_shopping_list_uses_latest_saved_meal_plan(self):
        result = self.graph.route("Make a shopping list", load_memory=True)
        self.assertEqual(result["intent"], "shopping_list")
        self.shopping.assert_called_once_with({"days": []}, 1)

    def test_current_context_wins_and_is_not_mutated(self):
        context = {"bag": [], "goal": "balanced nutrition"}
        result = self.graph.route("Optimize my bag", context, load_memory=True)
        self.assertEqual(result["mode"], "routing_fallback")
        self.assertEqual(result["context_used"]["bag"], [])
        self.assertEqual(result["context_used"]["goal"], "balanced nutrition")
        self.assertEqual(context, {"bag": [], "goal": "balanced nutrition"})

    def test_memory_opt_in_and_no_state_leaks_between_requests(self):
        self.graph.route("hello", user_id="alice", load_memory=True)
        self.memory.reset_mock()
        result = self.graph.route("hello", user_id="bob")
        self.memory.assert_not_called()
        self.assertEqual(result["context_used"], {})
        self.assertNotIn("peanuts", self.ai.call_args.args[1])

    def test_chat_prompt_receives_restrictions_and_recent_history(self):
        self.graph.route("hello", load_memory=True)
        prompt = self.ai.call_args.args[1]
        self.assertIn("peanuts", prompt)
        self.assertIn("I prefer quick meals", prompt)

    def test_provider_errors_are_not_hidden_or_retried(self):
        self.meal.side_effect = HTTPException(status_code=503, detail="Provider unavailable")
        with self.assertRaises(HTTPException):
            self.graph.route("Build me a meal plan")
        self.meal.assert_called_once()
        self.ai.assert_not_called()

    def test_context_failure_and_offline_chat_have_bounded_fallback(self):
        self.ai.side_effect = RuntimeError("offline")
        result = self.graph.route("Compare these products")
        self.assertEqual(result["mode"], "routing_fallback")
        self.assertIsNone(result["tool_result"])
        self.assertIn("compare_products", result["routing_error"])
        self.ai.assert_called_once()
