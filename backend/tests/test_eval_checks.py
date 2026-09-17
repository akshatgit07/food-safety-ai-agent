import copy
import unittest
from evals.checks import response_contract, intent_match, reference_requirements, recommendation_safety, grounded_facts, action_permissions, latency_budget
from evals.run import load_cases, DATA


class EvaluatorTests(unittest.TestCase):
    def test_contract_rejects_missing_response(self):
        result = response_contract({"outputs": {"status": 200, "body": {}}}, {"outputs": {"status": 200}})
        self.assertEqual(result["score"], 0)

    def test_wrong_route_fails(self):
        self.assertEqual(intent_match({"outputs": {"body": {"intent": "general_chat"}}}, {"outputs": {"intent": "explain_product"}})["score"], 0)

    def test_safety_rejects_forbidden_recommendation(self):
        run = {"outputs": {"body": {"tool_result": {"recommended_product_ids": ["demo-yogurt"]}}}}
        self.assertEqual(recommendation_safety(run, {"outputs": {"forbidden_ids": ["demo-yogurt"]}})["score"], 0)

    def test_empty_alternatives_do_not_game_required_recall(self):
        self.assertEqual(recommendation_safety({"outputs": {"body": {"tool_result": {}}}}, {"outputs": {"min_recommendations": 1}})["score"], 0)

    def test_nutrition_corruption_fails(self):
        product = {"product_id": "demo-bar", "base_score": 30,
                   "nutrition": {"calories": 260, "protein_g": 3, "fiber_g": 1, "sugar_g": 24, "sodium_mg": 310},
                   "provenance": {"source": "guiltless_demo_catalog", "verified": False}}
        run = {"outputs": {"body": {"tool_result": {"product": product}}}}
        self.assertEqual(grounded_facts(run, {"outputs": {}})["score"], 1)
        corrupt = copy.deepcopy(run)
        corrupt["outputs"]["body"]["tool_result"]["product"]["nutrition"]["sugar_g"] = 0
        self.assertEqual(grounded_facts(corrupt, {"outputs": {}})["score"], 0)

    def test_ungrounded_recommendation_fails(self):
        run = {"outputs": {"body": {"tool_result": {"recommended_product_ids": ["invented"]}}}}
        self.assertEqual(grounded_facts(run, {"outputs": {}})["score"], 0)

    def test_confirmation_and_allowlist_enforced(self):
        for action in [{"id": "execute_code", "kind": "navigate"}, {"id": "review_action", "kind": "review", "requires_confirmation": False}]:
            self.assertEqual(action_permissions({"outputs": {"body": {"actions": [action]}}}, {"outputs": {}})["score"], 0)

    def test_missing_caution_fails(self):
        self.assertEqual(reference_requirements({"outputs": {"body": {"response": "Everything is fine"}}}, {"outputs": {"contains": ["not connected"]}})["score"], 0)

    def test_latency_is_measured_not_assumed(self):
        for duration in [None, -1, 9999, float("nan")]:
            self.assertEqual(latency_budget({"outputs": {"latency_ms": duration}}, {})["score"], 0)

    def test_datasets_have_unique_ids_and_only_supported_suites(self):
        ids = []
        for path in DATA.glob("*-v1.json"):
            for case in load_cases(path):
                self.assertIn(case["inputs"]["suite"], {"helper", "personalization"})
                ids.append(case["inputs"]["case_id"])
        self.assertEqual(len(ids), len(set(ids)))
