import uuid
import unittest

from fastapi.testclient import TestClient

from app.main import app


class BehaviorGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user_id = f"guide-test-{uuid.uuid4()}"

    def event(self, event_type, screen="product_detail", metadata=None):
        return self.client.post(f"/app/events/{self.user_id}", json={
            "event_type": event_type, "screen": screen, "product_id": "demo-bar",
            "metadata": metadata or {},
        })

    def suggestion(self, screen="product_detail", bag=None):
        return self.client.post(f"/helper/proactive/{self.user_id}", json={
            "screen": screen, "product_id": "demo-bar", "product_name": "Frosted Snack Bar",
            "product_score": 30, "bag_product_ids": bag or [],
        })

    def test_product_context_proposes_score_explanation(self):
        self.assertEqual(self.event("screen_viewed").status_code, 200)
        body = self.suggestion().json()
        self.assertTrue(body["show"])
        self.assertEqual(body["suggestion"]["intent"], "explain_health_score")
        self.assertEqual(body["context_used"]["product_id"], "demo-bar")

    def test_dismissal_suppresses_same_suggestion(self):
        suggestion = self.suggestion().json()["suggestion"]
        self.event("suggestion_dismissed", metadata={"suggestion_id": suggestion["id"]})
        self.assertFalse(self.suggestion().json()["show"])

    def test_bag_context_proposes_optimizer(self):
        body = self.suggestion(screen="bag", bag=["demo-bar", "demo-chickpeas"]).json()
        self.assertEqual(body["suggestion"]["intent"], "optimize_bag")

    def test_event_schema_and_metadata_limit(self):
        self.assertEqual(self.client.post(f"/app/events/{self.user_id}", json={"event_type": "raw_click", "screen": "bag"}).status_code, 422)
        response = self.client.post(f"/app/events/{self.user_id}", json={"event_type": "screen_viewed", "screen": "bag", "metadata": {"value": "x" * 5000}})
        self.assertEqual(response.status_code, 422)

    def test_helper_can_use_saved_profile_memory(self):
        self.client.put(f"/profile/{self.user_id}", json={"goal": "high protein", "allergies": ["milk"]})
        body = self.client.post("/helper/chat", json={"message": "Explain score", "product_id": "demo-yogurt", "user_id": self.user_id}).json()
        self.assertTrue(body["context_used"]["memory_used"])
        self.assertEqual(body["tool_result"]["current_product"]["scoring"]["compatibility"], "incompatible")


if __name__ == "__main__":
    unittest.main()
