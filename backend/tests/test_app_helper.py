import unittest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import app
from app.services.app_helper import HelperRequest, helper_reply, GUIDES


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_each_screen_has_guidance_without_ai(self):
        graph = Mock()
        for screen in GUIDES:
            reply = helper_reply(HelperRequest(message="How do I use this screen?", screen=screen), graph)
            self.assertEqual(reply["intent"], "app_guidance")
            self.assertTrue(reply["steps"])
        graph.run.assert_not_called()

    def test_mobile_score_cannot_be_explained_using_catalog_algorithm(self):
        graph = Mock()
        reply = helper_reply(HelperRequest(message="Explain this score", score_source="mobile_app", product_id="demo-bar"), graph)
        self.assertEqual(reply["intent"], "score_source_unavailable")
        graph.run.assert_not_called()

    def test_real_score_is_grounded(self):
        response = self.client.post('/helper/chat', json={"message": "Explain this score", "product_id": "demo-bar"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["tool_result"]["current_product"]["product"]["product_id"], "demo-bar")
        self.assertEqual(result["tool_result"]["base_explanation"]["score"], result["tool_result"]["current_product"]["scoring"]["base_score"])
        self.assertTrue(any("sugar" in reason.lower() for reason in result["tool_result"]["base_explanation"]["cautions"]))

    def test_unknown_product_does_not_invent_score(self):
        result = self.client.post('/helper/chat', json={"message": "Explain this score", "product_id": "unknown-helper-product"}).json()
        self.assertTrue(result["errors"])
        self.assertEqual(result["tool_result"], {})
        self.assertEqual(result["actions"], [])

    def test_missing_product_and_bag(self):
        for message, intent in [("Explain score", "needs_product"), ("Optimize bag", "needs_bag")]:
            result = self.client.post('/helper/chat', json={"message": message}).json()
            self.assertEqual(result["intent"], intent)

    def test_mutating_request_is_only_a_review(self):
        graph = Mock()
        for message in ["Apply the swap", "Log this food", "Purchase everything", "Checkout now"]:
            result = helper_reply(HelperRequest(message=message), graph)
            self.assertEqual(result["intent"], "action_preview")
            self.assertTrue(result["actions"][0]["requires_confirmation"])
        graph.run.assert_not_called()

    def test_logging_guidance_routes_from_product_screen(self):
        result = self.client.post('/helper/chat', json={"message": "How do I log food?", "screen": "product_detail"}).json()
        self.assertEqual(result["response"], "Review, then log")

    def test_invalid_inputs(self):
        for data in [{"message": " "}, {"message": "Help", "screen": "execute_code"}, {"message": "a" * 2001}]:
            self.assertEqual(self.client.post('/helper/chat', json=data).status_code, 422)

    def test_entered_allergy_reaches_score_validation(self):
        result = self.client.post('/helper/chat', json={"message": "Explain score", "product_id": "demo-yogurt", "allergies": ["milk"]}).json()
        self.assertEqual(result["tool_result"]["current_product"]["scoring"]["compatibility"], "incompatible")
