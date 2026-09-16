import tempfile
import unittest
from pathlib import Path

from internal_devloop.models import FeatureRunRequest, HumanDecisionRequest
from internal_devloop.service import DevLoopService


class FeatureLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "loop.db")
        self.service = DevLoopService(self.path)

    def tearDown(self):
        if self.service:
            self.service.close()
        self.tmp.cleanup()

    def approve(self, run, suffix="approve"):
        blocker = run["blocker"]
        result, duplicate = self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=blocker["approval_id"], action_id=f"action-{suffix}-{blocker['approval_id']}",
            action="approve_recommended_fix"))
        self.assertFalse(duplicate)
        return result

    def test_happy_path_feature(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Add a backend feature with regression tests"))
        self.assertEqual(run["status"], "needs_approval")
        self.assertEqual(run["blocker"]["reason"], "final_approval")
        completed = self.approve(run)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(all(task["status"] == "completed" for task in completed["state"]["tasks"]))

    def test_task_fails_once_and_succeeds_on_retry(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Add a backend feature with tests", scenario="fail_once"))
        first = run["state"]["tasks"][0]
        self.assertEqual(first["attempts"], 2)
        self.assertEqual(first["status"], "completed")
        self.assertTrue(any(entry["event"] == "task_retry" for entry in run["state"]["audit_log"]))

    def test_retry_limit_triggers_slack_escalation(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Add a backend feature with tests", scenario="always_fail", max_retries=1))
        self.assertEqual(run["status"], "needs_approval")
        self.assertEqual(run["blocker"]["reason"], "retry_limit_reached")
        self.assertEqual(run["state"]["tasks"][0]["attempts"], 2)
        row = self.service.store.conn.execute("SELECT transport FROM notifications").fetchone()
        self.assertEqual(row["transport"], "mock_slack")
        duplicate = self.service.notifications.send_escalation(run["blocker"], f"{run['run_id']}:{run['blocker']['approval_id']}")
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(self.service.store.conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 1)

    def test_human_approval_resumes_run(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Change authentication security checks for account sessions"))
        self.assertEqual(run["blocker"]["reason"], "high_risk_task")
        resumed = self.approve(run, "risk")
        self.assertEqual(resumed["blocker"]["reason"], "final_approval")
        self.assertTrue(resumed["state"]["task_results"])

    def test_duplicate_approval_does_not_execute_twice(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Add a backend feature with regression tests"))
        blocker = run["blocker"]
        decision = HumanDecisionRequest(approval_id=blocker["approval_id"], action_id="action-duplicate-123",
                                        action="approve_recommended_fix")
        completed, duplicate = self.service.decide(run["run_id"], decision)
        count = len(completed["state"]["task_results"])
        repeated, duplicate = self.service.decide(run["run_id"], decision)
        self.assertTrue(duplicate)
        self.assertEqual(len(repeated["state"]["task_results"]), count)

    def test_high_risk_task_pauses_before_execution(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Modify payment checkout authorization"))
        self.assertEqual(run["status"], "needs_approval")
        self.assertEqual(run["state"]["tasks"][0]["status"], "needs_approval")
        self.assertEqual(run["state"]["task_results"], [])

    def test_rejection_marks_task_failed(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Delete user data from authentication records"))
        blocker = run["blocker"]
        rejected, _ = self.service.decide(run["run_id"], HumanDecisionRequest(
            approval_id=blocker["approval_id"], action_id="action-reject-123", action="reject", comment="Unsafe"))
        self.assertEqual(rejected["status"], "failed")
        self.assertEqual(rejected["state"]["tasks"][0]["status"], "failed")

    def test_state_survives_process_restart_checkpoint_reload(self):
        run = self.service.create_run(FeatureRunRequest(feature_request="Change authentication security checks for account sessions"))
        self.service.close(); self.service = DevLoopService(self.path)
        loaded = self.service.get_run(run["run_id"])
        self.assertEqual(loaded["blocker"]["approval_id"], run["blocker"]["approval_id"])
        resumed = self.approve(loaded, "restart")
        self.assertEqual(resumed["blocker"]["reason"], "final_approval")
        self.assertTrue(resumed["state"]["task_results"])


if __name__ == "__main__":
    unittest.main()
