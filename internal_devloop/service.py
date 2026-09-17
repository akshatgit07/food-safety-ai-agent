from __future__ import annotations

import os
from pathlib import Path
import threading
import uuid
from typing import Any

from .graph import FeatureDevelopmentGraph
from .models import DevLoopState, FeatureRunRequest, HumanDecisionRequest
from .providers import (DeterministicApprovalProvider, MockCodingProvider, MockDeploymentProvider,
                        MockPlanningProvider, MockTestProvider)
from .store import LocalSlackAdapter, RunStore


class DevLoopService:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.store = RunStore(db_path)
        self.notifications = LocalSlackAdapter(self.store)
        self.graph = FeatureDevelopmentGraph(db_path=db_path, store=self.store,
                                             planner=MockPlanningProvider(), coder=MockCodingProvider(),
                                             tester=MockTestProvider(), deployer=MockDeploymentProvider(),
                                             notifier=self.notifications, approvals=DeterministicApprovalProvider())
        self.lock = threading.RLock()

    def create_run(self, request: FeatureRunRequest) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        state: DevLoopState = {
            "run_id": run_id, "feature_request": request.feature_request,
            "requirements": [], "assumptions": [], "implementation_plan": {}, "tasks": [],
            "current_task": None, "task_results": [], "code_changes": [], "test_results": [],
            "build_results": [], "deployment_preview": {}, "errors": [], "retry_count": 0,
            "risk_level": "low", "approval_required": False, "human_decisions": [],
            "status": "queued", "audit_log": [], "max_retries": request.max_retries,
            "confidence_threshold": request.confidence_threshold, "scenario": request.scenario,
            "failure_diagnosis": {}, "escalation_reason": "", "escalation_outcome": "",
        }
        with self.lock:
            self.store.create_run(run_id, request.feature_request, dict(state))
            return self.graph.start(state)

    @staticmethod
    def _assert_same_action(existing: dict[str, Any], request: HumanDecisionRequest) -> None:
        # A second delivery of the SAME click (a Slack webhook retry, a double
        # click) must resume idempotently. A DIFFERENT action submitted against an
        # already-decided approval_id - e.g. two reviewers disagreeing, or a
        # decision arriving after the run already moved on - is not a duplicate;
        # every prior version of this check matched on approval_id OR action_id
        # alone and silently returned the FIRST decision as if the second had been
        # applied, with no error and no persisted record that it was ever
        # submitted. For a gate whose entire purpose is a human override on risky
        # work, a discarded "reject" is the one failure mode that cannot be silent.
        applied = existing["decision"]["action"]
        if applied != request.action.value:
            raise ValueError(
                f"Approval {request.approval_id} was already decided as '{applied}'; "
                f"the conflicting action '{request.action.value}' was not applied"
            )

    def decide(self, run_id: str, request: HumanDecisionRequest) -> tuple[dict[str, Any], bool]:
        with self.lock:
            run = self.store.get_run(run_id)
            if not run:
                raise KeyError("Run not found")
            blocker = run.get("blocker")
            if not blocker or blocker.get("approval_id") != request.approval_id:
                # If this exact approval was already applied, return current state idempotently.
                existing = self.store.get_decision(request.approval_id, request.action_id)
                if existing and existing["run_id"] == run_id and existing["approval_id"] == request.approval_id:
                    self._assert_same_action(existing, request)
                    return run, True
                raise ValueError("Approval is not pending for this run")
            existing = self.store.get_decision(request.approval_id, request.action_id)
            if existing and (existing["run_id"] != run_id or existing["approval_id"] != request.approval_id):
                raise ValueError("Action ID was already used for another approval")
            if existing:
                self._assert_same_action(existing, request)
                created, saved = False, existing["decision"]
            else:
                created, saved = self.store.register_decision(request.approval_id, request.action_id, run_id, request.model_dump(mode="json"))
            # A duplicate still resumes if a prior process persisted the decision but
            # crashed before advancing the checkpoint. The current blocker proves that.
            result = self.graph.resume(run_id, saved)
            return result, not created

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get_run(run_id)

    def list_runs(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_runs(status)

    def close(self) -> None:
        self.graph.close(); self.store.close()


def default_db_path() -> str:
    return os.getenv("DEVLOOP_DATABASE_PATH", "/tmp/guiltless_devloop.db")
