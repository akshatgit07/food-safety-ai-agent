import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from langsmith import Client

from app.main import app
from app.observability import observed, get_trace_client


class ObservabilityTests(unittest.TestCase):
    def test_disabled_tracing_never_initializes_client(self):
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": "test"}), patch("app.observability.get_trace_client") as client:
            response = TestClient(app).post("/v2/copilot/chat", json={"message": "Explain score", "product_id": "demo-bar"})
        self.assertEqual(response.status_code, 200)
        client.assert_not_called()

    def test_missing_key_does_not_break_api(self):
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": ""}), patch("app.observability.get_trace_client") as client:
            response = TestClient(app).post("/v2/copilot/chat", json={"message": "Optimize my bag", "bag_product_ids": ["demo-bar"]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["errors"])
        client.assert_not_called()

    def test_client_failure_runs_business_function_once(self):
        function = Mock(return_value="result")

        @observed("test.failure")
        def task():
            return function()

        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test"}), patch("app.observability.get_trace_client", side_effect=ValueError("bad configuration")):
            self.assertEqual(task(), "result")
        function.assert_called_once()

    def test_payloads_hidden_by_default(self):
        get_trace_client.cache_clear()
        with patch.dict(os.environ, {}, clear=True), patch("app.observability.Client") as client:
            get_trace_client()
            client.assert_called_once_with(hide_inputs=True, hide_outputs=True)
        get_trace_client.cache_clear()

    def test_nested_runs_share_trace_and_fallback_metadata(self):
        client = Mock(spec=Client)

        @observed("test.child", "tool")
        def child():
            return 3

        @observed("test.parent")
        def parent():
            child()
            return {"intent": "find_swap", "errors": ["validation failed"]}

        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "test"}), patch("app.observability.get_trace_client", return_value=client):
            parent()
        runs = [call.kwargs for call in client.create_run.call_args_list]
        self.assertEqual({r["name"] for r in runs}, {"test.parent", "test.child"})
        root = next(r for r in runs if r["name"] == "test.parent")
        nested = next(r for r in runs if r["name"] == "test.child")
        self.assertEqual(root["trace_id"], nested["trace_id"])
        self.assertEqual(nested["parent_run_id"], root["id"])
        updates = [call.kwargs for call in client.update_run.call_args_list]
        self.assertTrue(any(u.get("extra", {}).get("metadata", {}).get("outcome") == "fallback" for u in updates))
