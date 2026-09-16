"""Regression tests for the distributed-workflow review of the dev loop.

Each test class pins one defect that was reproduced against the pre-review
code: an unhandled provider exception stranding a run with no escalation and
no recovery path (scenarios 5/9/10), a conflicting human decision silently
discarded instead of raising (scenarios 2/3), a destructive-operation
classifier bypassable by common phrasing (scenario 7), an unenforced task
dependency graph (scenario 6), and a deployment call with no idempotency key
(scenario 4).
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from internal_devloop.graph import FeatureDevelopmentGraph
from internal_devloop.models import (
    DevLoopState,
    FeatureRunRequest,
    HumanDecisionRequest,
    RiskLevel,
    Task,
    TaskResult,
    ValidationResult,
)
from internal_devloop.providers import (
    ApprovalProvider,
    CodingProvider,
    DeploymentProvider,
    DeterministicApprovalProvider,
    MockCodingProvider,
    MockDeploymentProvider,
    MockPlanningProvider,
    MockTestProvider,
    PlanningProvider,
    TestProvider,
    classify_risk,
)
from internal_devloop.service import DevLoopService
from internal_devloop.store import LocalSlackAdapter, RunStore


def initial_state(run_id: str, feature_request: str = "Add a backend feature with tests",
                  max_retries: int = 2) -> DevLoopState:
    return {
        "run_id": run_id, "feature_request": feature_request,
        "requirements": [], "assumptions": [], "implementation_plan": {}, "tasks": [],
        "current_task": None, "task_results": [], "code_changes": [], "test_results": [],
        "build_results": [], "deployment_preview": {}, "errors": [], "retry_count": 0,
        "risk_level": "low", "approval_required": False, "human_decisions": [],
        "status": "queued", "audit_log": [], "max_retries": max_retries,
        "confidence_threshold": 0.5, "scenario": "normal",
        "failure_diagnosis": {}, "escalation_reason": "", "escalation_outcome": "",
    }


class GraphHarness:
    """Builds a FeatureDevelopmentGraph with swappable providers, bypassing the
    service's hardcoded mocks, for tests that need to inject a failing provider
    or a specific plan."""

    def __init__(self, tmp_dir: str, *, planner: PlanningProvider | None = None,
                coder: CodingProvider | None = None, tester: TestProvider | None = None,
                deployer: DeploymentProvider | None = None,
                approvals: ApprovalProvider | None = None):
        self.db_path = str(Path(tmp_dir) / "loop.db")
        self.store = RunStore(self.db_path)
        self.graph = FeatureDevelopmentGraph(
            db_path=self.db_path, store=self.store,
            planner=planner or MockPlanningProvider(), coder=coder or MockCodingProvider(),
            tester=tester or MockTestProvider(), deployer=deployer or MockDeploymentProvider(),
            notifier=LocalSlackAdapter(self.store), approvals=approvals or DeterministicApprovalProvider(),
        )

    def start(self, feature_request: str = "Add a backend feature with tests", **kwargs) -> dict[str, Any]:
        run_id = f"run-{id(self)}-{feature_request[:8]}"
        state = initial_state(run_id, feature_request, **kwargs)
        self.store.create_run(run_id, feature_request, dict(state))
        return self.graph.start(state)

    def close(self) -> None:
        self.graph.close()
        self.store.close()


class UnavailableCodingProvider(CodingProvider):
    """Simulates a network outage, a crashed sandbox, or a missing secret."""

    def execute(self, task: Task, context: dict[str, Any], idempotency_key: str) -> TaskResult:
        raise ConnectionError("Coding provider unreachable: connection refused")


class AlwaysPassTestProvider(TestProvider):
    """A tester that ignores the actual TaskResult, like a naive test runner that
    only checks 'did something run' rather than 'did the coder actually succeed'."""

    def validate_task(self, task: Task, result: TaskResult, context: dict[str, Any]) -> ValidationResult:
        return ValidationResult(success=True, summary="Naive check passed", confidence=0.99)

    def validate_integration(self, context: dict[str, Any]) -> ValidationResult:
        return ValidationResult(success=True, summary="Integration checks passed", confidence=0.98)


class ProviderFailureTests(unittest.TestCase):
    """Scenarios 5 (agent 'succeeds' when it actually failed), 9 (missing
    secrets), 10 (coding provider unavailable mid-run)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_provider_exception_does_not_crash_the_run(self):
        harness = GraphHarness(self.tmp.name, coder=UnavailableCodingProvider())
        try:
            result = harness.start()  # must not raise
        finally:
            harness.close()
        self.assertEqual(result["status"], "needs_approval")
        self.assertIsNotNone(result["blocker"])

    def test_provider_exception_is_recorded_and_escalated_not_stranded(self):
        harness = GraphHarness(self.tmp.name, coder=UnavailableCodingProvider())
        try:
            result = harness.start()
        finally:
            harness.close()
        task_result = result["state"]["task_results"][-1]
        self.assertFalse(task_result["success"])
        self.assertIn("coding provider unavailable", task_result["error"])
        self.assertTrue(any(e["event"] == "task_executed" for e in result["state"]["audit_log"]))
        self.assertTrue(any(e["event"] == "task_validated" for e in result["state"]["audit_log"]))
        # The dashboard journal must reflect the real state, not the stale
        # "queued" row left behind when sync() never ran after an unhandled crash.
        self.assertNotEqual(result["status"], "queued")

    def test_naive_tester_cannot_launder_a_provider_crash_into_success(self):
        """A tester that only checks task metadata (not the actual TaskResult)
        must not be able to turn a coder-level failure into a pass."""
        harness = GraphHarness(self.tmp.name, coder=UnavailableCodingProvider(), tester=AlwaysPassTestProvider())
        try:
            result = harness.start()
        finally:
            harness.close()
        task = result["state"]["tasks"][0]
        self.assertNotEqual(task["status"], "completed")
        record = result["state"]["test_results"][-1]
        self.assertFalse(record["success"])

    def test_recovering_provider_lets_a_retry_succeed(self):
        """After the provider comes back, the existing bounded-retry path still
        works exactly as it does for an ordinary validation failure."""
        class FlakyOnceProvider(CodingProvider):
            def __init__(self):
                self.calls = 0

            def execute(self, task, context, idempotency_key):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("provider timed out")
                return MockCodingProvider().execute(task, context, idempotency_key)

        harness = GraphHarness(self.tmp.name, coder=FlakyOnceProvider())
        try:
            result = harness.start()
        finally:
            harness.close()
        task = result["state"]["tasks"][0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["attempts"], 2)


class ConflictingDecisionTests(unittest.TestCase):
    """Scenario 2 (duplicate Slack delivery, must resume idempotently) and
    scenario 3 (two humans decide differently, or a decision arrives after the
    run already moved on - must never be silently swallowed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = DevLoopService(str(Path(self.tmp.name) / "loop.db"))

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def test_duplicate_delivery_of_the_same_action_resumes_idempotently(self):
        run = self.service.create_run(FeatureRunRequest(
            feature_request="Change authentication security checks for account sessions"))
        blocker = run["blocker"]
        first, dup1 = self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=blocker["approval_id"], action_id="webhook-delivery-1", action="approve_recommended_fix"))
        second, dup2 = self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=blocker["approval_id"], action_id="webhook-delivery-2-retry", action="approve_recommended_fix"))
        self.assertFalse(dup1)
        self.assertTrue(dup2)
        self.assertEqual(len(first["state"]["task_results"]), len(second["state"]["task_results"]))

    def test_conflicting_action_on_a_decided_approval_raises_instead_of_silently_dropping(self):
        run = self.service.create_run(FeatureRunRequest(
            feature_request="Change authentication security checks for account sessions"))
        blocker = run["blocker"]
        self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=blocker["approval_id"], action_id="human-A-approve", action="approve_recommended_fix"))
        with self.assertRaises(ValueError):
            self.service.decide(run["run_id"], HumanDecisionRequest(
                approval_id=blocker["approval_id"], action_id="human-B-reject-too-late",
                action="reject", comment="Unsafe"))
        # And the conflicting reject must not be silently recorded as if applied.
        row = self.service.store.conn.execute(
            "SELECT decision_json FROM human_decisions WHERE approval_id=?", (blocker["approval_id"],)
        ).fetchall()
        self.assertEqual(len(row), 1)
        import json
        self.assertEqual(json.loads(row[0]["decision_json"])["action"], "approve_recommended_fix")

    def test_late_decision_against_a_superseded_approval_is_rejected(self):
        run = self.service.create_run(FeatureRunRequest(
            feature_request="Change authentication security checks for account sessions"))
        stale_blocker = run["blocker"]
        self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=stale_blocker["approval_id"], action_id="advance-1", action="approve_recommended_fix"))
        with self.assertRaises(ValueError):
            self.service.decide(run["run_id"], HumanDecisionRequest(
                approval_id=stale_blocker["approval_id"], action_id="late-arrival-never-seen", action="reject"))

    def test_run_not_found_still_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.service.decide("no-such-run", HumanDecisionRequest(
                approval_id="x" * 8, action_id="y" * 8, action="reject"))


class DestructiveOperationClassificationTests(unittest.TestCase):
    """Scenario 7 combined with deployment safety: a destructive migration must
    be gated regardless of exact phrasing."""

    def _task(self, description: str, domain: str = "data") -> Task:
        task = Task(id="t", title="Implement feature", description=description, domain=domain)
        task.risk_level = classify_risk(task)
        return task

    def test_common_destructive_phrasings_are_all_high_risk(self):
        cases = [
            "Run a destructive migration that drops the legacy_users table",
            "Run a migration that drops the legacy_users table",
            "Write a migration to purge inactive customer records",
            "Add a migration step that truncates the orders table",
            "Erase all analytics events older than 90 days via a migration",
            "Wipe the staging database as part of this migration",
        ]
        for description in cases:
            with self.subTest(description=description):
                task = self._task(description)
                self.assertEqual(task.risk_level, RiskLevel.high)
                self.assertTrue(DeterministicApprovalProvider().requires_approval(task))

    def test_non_destructive_data_task_stays_medium_and_ungated(self):
        task = self._task("Add a database index for faster search")
        self.assertEqual(task.risk_level, RiskLevel.medium)
        self.assertFalse(DeterministicApprovalProvider().requires_approval(task))

    def test_destructive_verb_outside_data_deployment_domain_is_not_escalated(self):
        """The verb-based rule is scoped to data/deployment domains so it does not
        over-trigger on unrelated backend work that happens to mention 'remove'."""
        task = self._task("Remove the unused CSS class from the button component", domain="frontend")
        self.assertEqual(task.risk_level, RiskLevel.low)


class TaskDependencyTests(unittest.TestCase):
    """Scenario 6 and 'bad planner assumptions': dependencies were declared on
    the Task model but never read anywhere before task selection."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    class _FixedPlanProvider(PlanningProvider):
        def __init__(self, tasks: list[dict[str, Any]]):
            self.tasks = tasks

        def analyze(self, feature_request: str) -> dict[str, Any]:
            return {"requirements": [feature_request], "assumptions": [], "ambiguous": False, "confidence": 0.95}

        def create_plan(self, feature_request: str, analysis: dict[str, Any], scenario: str) -> dict[str, Any]:
            return {"summary": "fixed plan", "tasks": self.tasks, "confidence": 0.95}

    def test_dependency_order_overrides_array_order(self):
        planner = self._FixedPlanProvider([
            {"id": "task-2", "title": "Frontend depends on backend", "description": "frontend",
             "domain": "frontend", "dependencies": ["task-1"], "metadata": {}},
            {"id": "task-1", "title": "Backend endpoint", "description": "backend", "domain": "backend", "metadata": {}},
        ])
        harness = GraphHarness(self.tmp.name, planner=planner)
        try:
            result = harness.start("Add a fully specified feature")
        finally:
            harness.close()
        order = [e["detail"] for e in result["state"]["audit_log"] if e["event"] == "task_selected"]
        self.assertEqual(order, ["Backend endpoint", "Frontend depends on backend"])

    def test_unknown_dependency_is_caught_before_any_task_runs(self):
        planner = self._FixedPlanProvider([
            {"id": "task-1", "title": "Do work", "description": "x", "domain": "backend",
             "dependencies": ["ghost-task"], "metadata": {}},
        ])
        harness = GraphHarness(self.tmp.name, planner=planner)
        try:
            result = harness.start("Add a widget with a bad dependency")
        finally:
            harness.close()
        self.assertEqual(result["status"], "needs_approval")
        self.assertIn("unknown task dependencies", result["blocker"]["reason"])
        self.assertEqual(result["state"]["task_results"], [])

    def test_circular_dependency_escalates_instead_of_silently_succeeding(self):
        planner = self._FixedPlanProvider([
            {"id": "task-1", "title": "A", "description": "x", "domain": "backend", "dependencies": ["task-2"], "metadata": {}},
            {"id": "task-2", "title": "B", "description": "y", "domain": "backend", "dependencies": ["task-1"], "metadata": {}},
        ])
        harness = GraphHarness(self.tmp.name, planner=planner)
        try:
            result = harness.start("Add a widget with a circular dependency")
        finally:
            harness.close()
        self.assertEqual(result["status"], "needs_approval")
        self.assertIn("circular task dependency", result["blocker"]["reason"])
        # Nothing ran, and integration must not have silently reported success.
        self.assertEqual(result["state"]["task_results"], [])
        self.assertEqual(result["state"]["build_results"], [])


class DeploymentIdempotencyTests(unittest.TestCase):
    """Scenario 4: a deployment succeeds but the confirmation webhook times out.
    create_preview previously had no idempotency key at all, unlike
    CodingProvider.execute."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    class RecordingDeploymentProvider(DeploymentProvider):
        def __init__(self):
            self.calls: list[str] = []

        def create_preview(self, context: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
            self.calls.append(idempotency_key)
            return {"status": "mock_ready", "url": "https://preview.invalid/x", "production_changed": False}

    def test_create_preview_receives_a_stable_per_attempt_key(self):
        deployer = self.RecordingDeploymentProvider()
        harness = GraphHarness(self.tmp.name, deployer=deployer)
        try:
            result = harness.start()
        finally:
            harness.close()
        self.assertEqual(result["status"], "needs_approval")
        self.assertEqual(result["blocker"]["reason"], "final_approval")
        self.assertEqual(len(deployer.calls), 1)
        self.assertIn(":deploy:attempt:1", deployer.calls[0])

    def test_repeated_deployment_failures_advance_the_attempt_key_and_still_bound_retries(self):
        class AlwaysFailingDeployer(DeploymentProvider):
            def __init__(self):
                self.calls: list[str] = []

            def create_preview(self, context, idempotency_key):
                self.calls.append(idempotency_key)
                raise TimeoutError("webhook confirmation timed out")

        deployer = AlwaysFailingDeployer()
        harness = GraphHarness(self.tmp.name, deployer=deployer)
        try:
            result = harness.start(max_retries=1)
        finally:
            harness.close()
        self.assertEqual(result["status"], "needs_approval")
        self.assertEqual(result["blocker"]["reason"], "deployment_failed_repeatedly")
        self.assertEqual(deployer.calls, [key for key in deployer.calls])
        self.assertEqual(len(set(deployer.calls)), len(deployer.calls), "each attempt must get a distinct key")
        self.assertGreaterEqual(len(deployer.calls), 2)


if __name__ == "__main__":
    unittest.main()
