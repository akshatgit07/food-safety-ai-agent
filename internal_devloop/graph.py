from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .models import DevLoopState, HumanAction, HumanDecisionRequest, RiskLevel, Task, TaskResult, TaskStatus, ValidationResult
from .providers import (ApprovalProvider, CodingProvider, DeploymentProvider, NotificationProvider,
                        PlanningProvider, TestProvider, classify_risk)
from .store import RunStore


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(state: DevLoopState, event: str, detail: str, **data: Any) -> list[dict[str, Any]]:
    return [*state.get("audit_log", []), {"at": timestamp(), "event": event, "detail": detail, **data}]


def risk_max(tasks: list[dict[str, Any]]) -> str:
    rank = {RiskLevel.low.value: 0, RiskLevel.medium.value: 1, RiskLevel.high.value: 2}
    return max((task["risk_level"] for task in tasks), key=rank.get, default=RiskLevel.low.value)


def dependency_error(tasks: list[dict[str, Any]]) -> str:
    """Reject an unresolvable plan before any task executes.

    Task.dependencies was declared on the model but never read anywhere: tasks
    always ran in plain array order regardless of what a planner declared, so a
    dependent task could execute before the work it depends on, and a planner
    typo or circular dependency would go completely unnoticed. Validating the
    graph is a DAG up front - once, at classification time - means select_task
    can safely respect dependency order afterward: a non-empty DAG always has at
    least one task with no unmet dependency, so a validated plan can never
    deadlock while draining tasks in that order.
    """
    ids = {task["id"] for task in tasks}
    unknown = sorted({dep for task in tasks for dep in task.get("dependencies", []) if dep not in ids})
    if unknown:
        return f"Plan references unknown task dependencies: {', '.join(unknown)}"
    remaining = {task["id"]: set(task.get("dependencies", [])) for task in tasks}
    resolved: set[str] = set()
    while remaining:
        ready = [task_id for task_id, deps in remaining.items() if deps <= resolved]
        if not ready:
            return f"Plan has a circular task dependency: {', '.join(sorted(remaining))}"
        for task_id in ready:
            resolved.add(task_id)
            del remaining[task_id]
    return ""


class FeatureDevelopmentGraph:
    def __init__(self, *, db_path: str, store: RunStore, planner: PlanningProvider,
                 coder: CodingProvider, tester: TestProvider, deployer: DeploymentProvider,
                 notifier: NotificationProvider, approvals: ApprovalProvider):
        self.store, self.planner, self.coder, self.tester = store, planner, coder, tester
        self.deployer, self.notifier, self.approvals = deployer, notifier, approvals
        self.checkpoint_connection = sqlite3.connect(db_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self.checkpoint_connection)
        graph = StateGraph(DevLoopState)
        for name, node in {
            "intake_feature": self.intake_feature,
            "analyze_requirements": self.analyze_requirements,
            "create_plan": self.create_plan,
            "classify_tasks": self.classify_tasks,
            "select_task": self.select_task,
            "pre_execution_gate": self.pre_execution_gate,
            "execute_task": self.execute_task,
            "validate_task": self.validate_task,
            "diagnose_failure": self.diagnose_failure,
            "retry_task": self.retry_task,
            "create_human_escalation": self.create_human_escalation,
            "next_task": self.next_task,
            "integration_validation": self.integration_validation,
            "request_final_approval": self.request_final_approval,
            "complete": self.complete,
            "terminate_rejected": self.terminate_rejected,
        }.items():
            graph.add_node(name, node)
        graph.add_edge(START, "intake_feature")
        graph.add_edge("intake_feature", "analyze_requirements")
        graph.add_edge("analyze_requirements", "create_plan")
        graph.add_edge("create_plan", "classify_tasks")
        graph.add_edge("classify_tasks", "select_task")
        graph.add_conditional_edges("select_task", self.route_selected, {"task": "pre_execution_gate", "integrate": "integration_validation"})
        graph.add_conditional_edges("pre_execution_gate", lambda s: "approval" if s.get("approval_required") else "execute",
                                    {"approval": "create_human_escalation", "execute": "execute_task"})
        graph.add_edge("execute_task", "validate_task")
        graph.add_conditional_edges("validate_task", self.route_validation,
                                    {"success": "next_task", "retry": "diagnose_failure", "approval": "create_human_escalation"})
        graph.add_edge("diagnose_failure", "retry_task")
        graph.add_edge("retry_task", "execute_task")
        graph.add_conditional_edges("create_human_escalation", self.route_human,
                                    {"execute": "execute_task", "next": "next_task", "integration": "integration_validation",
                                     "final": "request_final_approval", "reject": "terminate_rejected"})
        graph.add_edge("next_task", "select_task")
        graph.add_conditional_edges("integration_validation", self.route_integration,
                                    {"approval": "create_human_escalation", "retry": "integration_validation", "final": "request_final_approval"})
        graph.add_conditional_edges("request_final_approval", self.route_human,
                                    {"execute": "complete", "next": "complete", "reject": "terminate_rejected"})
        graph.add_edge("complete", END)
        graph.add_edge("terminate_rejected", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    @staticmethod
    def config(run_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": run_id}, "metadata": {"run_id": run_id},
                "run_name": "guiltless.internal.feature-development"}

    def start(self, state: DevLoopState) -> dict[str, Any]:
        self.graph.invoke(state, config=self.config(state["run_id"]))
        return self.sync(state["run_id"])

    def resume(self, run_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        self.graph.invoke(Command(resume=decision), config=self.config(run_id))
        return self.sync(run_id)

    def sync(self, run_id: str) -> dict[str, Any]:
        snapshot = self.graph.get_state(self.config(run_id))
        state = dict(snapshot.values)
        interrupts = list(snapshot.interrupts)
        blocker = interrupts[0].value if interrupts else None
        status = "needs_approval" if blocker else state.get("status", "unknown")
        self.store.save_state(run_id, state, status, blocker)
        return self.store.get_run(run_id)

    def intake_feature(self, state: DevLoopState) -> dict[str, Any]:
        return {"status": "analyzing", "audit_log": audit(state, "feature_intake", "Feature request accepted")}

    def analyze_requirements(self, state: DevLoopState) -> dict[str, Any]:
        result = self.planner.analyze(state["feature_request"])
        needs_human = result["ambiguous"] or result["confidence"] < state["confidence_threshold"]
        reason = "requirements_ambiguous" if result["ambiguous"] else "low_agent_confidence" if needs_human else ""
        return {"requirements": result["requirements"], "assumptions": result["assumptions"],
                "approval_required": needs_human, "escalation_reason": reason,
                "implementation_plan": {"analysis_confidence": result["confidence"]},
                "audit_log": audit(state, "requirements_analyzed", "Requirements analyzed", confidence=result["confidence"])}

    def create_plan(self, state: DevLoopState) -> dict[str, Any]:
        analysis = {"requirements": state["requirements"], "assumptions": state["assumptions"],
                    "confidence": state["implementation_plan"]["analysis_confidence"]}
        plan = self.planner.create_plan(state["feature_request"], analysis, state["scenario"])
        return {"implementation_plan": plan, "audit_log": audit(state, "plan_created", plan["summary"])}

    def classify_tasks(self, state: DevLoopState) -> dict[str, Any]:
        tasks = []
        for raw in state["implementation_plan"]["tasks"]:
            task = Task.model_validate(raw)
            task.risk_level = classify_risk(task)
            task.approval_required = self.approvals.requires_approval(task)
            tasks.append(task.model_dump(mode="json"))
        error = dependency_error(tasks)
        approval_required = bool(error) or bool(state.get("approval_required"))
        reason = error or state.get("escalation_reason", "")
        return {"tasks": tasks, "risk_level": risk_max(tasks), "status": "planned",
                "approval_required": approval_required, "escalation_reason": reason,
                "audit_log": audit(state, "tasks_classified", error or f"Classified {len(tasks)} tasks")}

    def select_task(self, state: DevLoopState) -> dict[str, Any]:
        completed = {item["id"] for item in state["tasks"] if item["status"] == TaskStatus.completed.value}
        task = next((item for item in state["tasks"]
                    if item["status"] in {TaskStatus.pending.value, TaskStatus.retrying.value}
                    and set(item.get("dependencies", [])) <= completed), None)
        return {"current_task": task["id"] if task else None, "retry_count": task.get("attempts", 0) - 1 if task else 0,
                "status": "executing" if task else "integrating",
                "audit_log": audit(state, "task_selected" if task else "tasks_exhausted", task["title"] if task else "All tasks processed")}

    @staticmethod
    def route_selected(state: DevLoopState) -> str:
        return "task" if state.get("current_task") else "integrate"

    def _current(self, state: DevLoopState) -> tuple[int, Task]:
        index = next(i for i, task in enumerate(state["tasks"]) if task["id"] == state["current_task"])
        return index, Task.model_validate(state["tasks"][index])

    def pre_execution_gate(self, state: DevLoopState) -> dict[str, Any]:
        index, task = self._current(state)
        global_gate = bool(state.get("approval_required"))
        requires = global_gate or task.approval_required
        task.status = TaskStatus.needs_approval if requires else TaskStatus.running
        tasks = list(state["tasks"]); tasks[index] = task.model_dump(mode="json")
        reason = state.get("escalation_reason") if global_gate else "high_risk_task" if requires else ""
        return {"tasks": tasks, "approval_required": requires, "escalation_reason": reason,
                "status": "needs_approval" if requires else "executing",
                "audit_log": audit(state, "approval_gate", reason or "Task cleared for execution", task_id=task.id)}

    def execute_task(self, state: DevLoopState) -> dict[str, Any]:
        index, task = self._current(state)
        task.attempts += 1; task.status = TaskStatus.running
        key = f"{state['run_id']}:{task.id}:attempt:{task.attempts}"
        saved = self.store.get_execution(key)
        if saved is None:
            try:
                result = self.coder.execute(task, {"run_id": state["run_id"], "plan": state["implementation_plan"]}, key)
                saved = result.model_dump(mode="json")
            except Exception as exc:
                # Provider boundary: a network outage, a missing secret, or a crashed
                # sandbox must not crash the whole run. An uncaught exception here
                # previously escaped graph.invoke() entirely - the checkpoint from
                # pre_execution_gate survived, but RunStore's dashboard row was never
                # synced past "queued", no escalation fired, and the public service API
                # had no path back in (decide() requires a blocker that was never set).
                # Route the failure through the same bounded retry/escalation path as
                # an ordinary validation failure instead.
                # confidence sits exactly at the configured threshold rather than
                # 0.0: a hard-coded 0.0 would force every crash - even a one-off
                # network blip - straight to escalation, bypassing max_retries and
                # defeating the bounded "safe retry" path a transient outage
                # (scenario 10) should get, same as any other recoverable failure.
                saved = TaskResult(task_id=task.id, success=False,
                                   summary="Coding provider call failed before producing a result",
                                   error=f"{type(exc).__name__}: coding provider unavailable",
                                   recoverable=True, confidence=state["confidence_threshold"],
                                   idempotency_key=key).model_dump(mode="json")
            self.store.save_execution(key, state["run_id"], task.id, saved)
        tasks = list(state["tasks"]); tasks[index] = task.model_dump(mode="json")
        changes = [*state.get("code_changes", []), *saved.get("artifacts", [])]
        return {"tasks": tasks, "task_results": [*state.get("task_results", []), saved], "code_changes": changes,
                "audit_log": audit(state, "task_executed", saved["summary"], task_id=task.id, idempotency_key=key)}

    def validate_task(self, state: DevLoopState) -> dict[str, Any]:
        index, task = self._current(state)
        result = TaskResult.model_validate(state["task_results"][-1])
        if not result.success:
            # The coding provider itself failed before producing a change (see
            # execute_task). There is nothing for an independent tester to validate,
            # and a tester that only inspects task metadata - not the actual result -
            # must never be allowed to launder a provider failure into a false pass.
            # The provider's own failure is authoritative here.
            validation = ValidationResult(success=False, summary=result.summary, error=result.error,
                                          explained=True, confidence=result.confidence)
        else:
            validation = self.tester.validate_task(task, result, {"run_id": state["run_id"]})
            if result.confidence < state["confidence_threshold"]:
                validation = validation.model_copy(update={"success": False, "summary": "Coding result confidence is below the approval threshold",
                                                           "error": "Low coding-agent confidence", "explained": True,
                                                           "confidence": result.confidence})
        record = {"task_id": task.id, **validation.model_dump(mode="json")}
        if validation.success:
            task.status = TaskStatus.completed
            error_list, approval, reason = state.get("errors", []), False, ""
        else:
            task.status = TaskStatus.failed
            error_list = [*state.get("errors", []), {"task_id": task.id, "error": validation.error,
                          "attempt": task.attempts, "evidence": validation.evidence}]
            exhausted = task.attempts > state["max_retries"]
            approval = exhausted or not validation.explained or validation.confidence < state["confidence_threshold"]
            reason = "retry_limit_reached" if exhausted else "unexplained_test_failure" if not validation.explained else "low_agent_confidence" if approval else ""
        tasks = list(state["tasks"]); tasks[index] = task.model_dump(mode="json")
        return {"tasks": tasks, "test_results": [*state.get("test_results", []), record], "errors": error_list,
                "approval_required": approval, "escalation_reason": reason,
                "audit_log": audit(state, "task_validated", validation.summary, task_id=task.id, success=validation.success)}

    def route_validation(self, state: DevLoopState) -> str:
        _, task = self._current(state)
        if task.status == TaskStatus.completed:
            return "success"
        return "approval" if state.get("approval_required") else "retry"

    def diagnose_failure(self, state: DevLoopState) -> dict[str, Any]:
        _, task = self._current(state)
        diagnosis = {"classification": "recoverable", "summary": "Validation failure is deterministic and bounded",
                     "recommended_action": "Retry with the recorded failure evidence", "confidence": 0.9}
        return {"failure_diagnosis": diagnosis, "audit_log": audit(state, "failure_diagnosed", diagnosis["summary"], task_id=task.id)}

    def retry_task(self, state: DevLoopState) -> dict[str, Any]:
        index, task = self._current(state); task.status = TaskStatus.retrying
        tasks = list(state["tasks"]); tasks[index] = task.model_dump(mode="json")
        return {"tasks": tasks, "retry_count": task.attempts, "status": "retrying",
                "audit_log": audit(state, "task_retry", "Safe retry scheduled", task_id=task.id, retry=task.attempts)}

    def _approval_payload(self, state: DevLoopState, reason: str, final: bool = False) -> dict[str, Any]:
        task = None if final or not state.get("current_task") else self._current(state)[1]
        suffix = f"{task.id}:{task.attempts}" if task else "final" if final else f"integration:{len(state.get('build_results', []))}"
        approval_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{state['run_id']}:{reason}:{suffix}"))
        latest_error = state.get("errors", [])[-1] if state.get("errors") else None
        diagnosis = state.get("failure_diagnosis", {})
        latest_test = state.get("test_results", [])[-1] if state.get("test_results") else None
        # diagnose_failure's confidence is a hardcoded mock constant, and the overall
        # plan confidence describes the whole feature, not this failure. A human
        # deciding on a specific task escalation - including a coding-provider
        # crash, which reports confidence=0.0 - must see that task's real number,
        # not an unrelated headline figure that can read as reassuring when it isn't.
        task_confidence = latest_test["confidence"] if task and latest_test and latest_test.get("task_id") == task.id else None
        confidence = task_confidence if task_confidence is not None else diagnosis.get("confidence", state["implementation_plan"].get("confidence", 0.9))
        return {"approval_id": approval_id, "feature": state["feature_request"],
                "current_task": task.model_dump(mode="json") if task else None,
                "failure": latest_error, "agent_diagnosis": diagnosis or {"summary": reason},
                "evidence_log_summary": (latest_error or {}).get("evidence", state.get("test_results", [])[-3:]),
                "recommended_next_action": "Approve the bounded action" if not final else "Approve completion of this prototype run",
                "confidence": confidence,
                "risk": task.risk_level.value if task else state.get("risk_level", "low"), "reason": reason,
                "available_actions": [{"id": action.value, "label": action.value.replace("_", " ").title()} for action in HumanAction]}

    def _interrupt_for_decision(self, state: DevLoopState, reason: str, final: bool = False) -> dict[str, Any]:
        payload = self._approval_payload(state, reason, final)
        self.notifier.send_escalation(payload, f"{state['run_id']}:{payload['approval_id']}")
        decision = interrupt(payload)
        while decision.get("action") == HumanAction.open_logs.value:
            payload = {**payload,
                       "approval_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{payload['approval_id']}:logs")),
                       "logs": state.get("audit_log", [])[-20:], "message": "Logs attached; choose a terminal action."}
            self.notifier.send_escalation(payload, f"{state['run_id']}:{payload['approval_id']}")
            decision = interrupt(payload)
        return decision

    def _apply_decision(self, state: DevLoopState, decision: dict[str, Any], final: bool = False) -> dict[str, Any]:
        action = HumanAction(decision["action"])
        history = [*state.get("human_decisions", []), {**decision, "at": timestamp()}]
        if final:
            outcome = "reject" if action == HumanAction.reject else "next"
            return {"human_decisions": history, "escalation_outcome": outcome, "approval_required": False,
                    "audit_log": audit(state, "final_decision", action.value)}
        if not state.get("current_task"):
            outcome = "reject" if action == HumanAction.reject else "final" if action == HumanAction.skip else "integration"
            return {"human_decisions": history, "escalation_outcome": outcome, "approval_required": False,
                    "escalation_reason": "", "status": "failed" if outcome == "reject" else "integrating",
                    "audit_log": audit(state, "human_decision", action.value, stage="integration")}
        index, task = self._current(state)
        if action == HumanAction.reject:
            task.status, outcome = TaskStatus.failed, "reject"
        elif action == HumanAction.skip:
            task.status, outcome = TaskStatus.completed, "next"
        else:
            task.status, outcome = TaskStatus.running, "execute"
            if action in {HumanAction.approve, HumanAction.revise}:
                task.metadata["scenario"] = "normal"
            if action == HumanAction.revise and decision.get("comment"):
                task.description += f"\nHuman revision: {decision['comment']}"
        tasks = list(state["tasks"]); tasks[index] = task.model_dump(mode="json")
        return {"tasks": tasks, "human_decisions": history, "escalation_outcome": outcome,
                "approval_required": False, "escalation_reason": "", "status": "executing" if outcome == "execute" else "failed" if outcome == "reject" else "executing",
                "audit_log": audit(state, "human_decision", action.value, task_id=task.id)}

    def create_human_escalation(self, state: DevLoopState) -> dict[str, Any]:
        reason = state.get("escalation_reason") or "human_review_required"
        decision = self._interrupt_for_decision(state, reason)
        return self._apply_decision(state, decision)

    @staticmethod
    def route_human(state: DevLoopState) -> str:
        return state.get("escalation_outcome", "reject")

    def next_task(self, state: DevLoopState) -> dict[str, Any]:
        return {"current_task": None, "approval_required": False, "escalation_reason": "",
                "audit_log": audit(state, "task_closed", "Moving to next task")}

    def integration_validation(self, state: DevLoopState) -> dict[str, Any]:
        if state.get("approval_required") and not state.get("task_results"):
            # select_task found no task it could select at all (every remaining task
            # sits behind an unresolvable dependency - the classify_tasks-time DAG
            # check should already have caught this, but a plan with zero valid
            # starting tasks skips pre_execution_gate entirely and lands directly
            # here). Nothing has run. Escalate as-is instead of letting the
            # integration checks below silently overwrite that with a false pass.
            return {"audit_log": audit(state, "integration_skipped",
                                       state.get("escalation_reason") or "No task could be selected before integration")}
        validation = self.tester.validate_integration(dict(state))
        preview, deployment_error = {}, None
        if validation.success:
            # Unlike CodingProvider.execute, create_preview previously took no
            # idempotency key: a webhook confirmation timing out on our side (the
            # deploy may have already succeeded upstream) gave a real provider no
            # way to recognize a retry as "the same attempt" and avoid deploying
            # twice. attempt is derived from prior FAILED build_results, so a
            # crash-and-resume between a provider call and this node returning
            # replays with the same attempt number and the same key; a genuine
            # new attempt (this node ran and recorded a failure) always advances it.
            attempt = sum(1 for item in state.get("build_results", []) if not item.get("success")) + 1
            deployment_key = f"{state['run_id']}:deploy:attempt:{attempt}"
            try:
                preview = self.deployer.create_preview({"run_id": state["run_id"], "state": dict(state)}, deployment_key)
                if preview.get("status") not in {"mock_ready", "ready", "success"}:
                    deployment_error = f"Preview status: {preview.get('status', 'unknown')}"
            except Exception as exc:  # Provider boundary: report without exposing credentials.
                deployment_error = f"{type(exc).__name__}: deployment provider failed"
        success = validation.success and deployment_error is None
        build = {"phase": "deployment" if validation.success else "integration", "success": success,
                 "summary": deployment_error or validation.summary, "evidence": validation.evidence}
        failures = sum(1 for item in state.get("build_results", []) if not item.get("success")) + (0 if success else 1)
        approval = not success and failures > state["max_retries"]
        retrying = not success and not approval
        return {"build_results": [*state.get("build_results", []), build], "deployment_preview": preview,
                "approval_required": approval, "escalation_reason": "deployment_failed_repeatedly" if approval else "",
                "status": "retrying" if retrying else "final_approval" if success else "needs_approval",
                "audit_log": audit(state, "integration_validated", build["summary"], success=success, attempt=failures)}

    @staticmethod
    def route_integration(state: DevLoopState) -> str:
        if state.get("approval_required"):
            return "approval"
        return "retry" if state.get("status") == "retrying" else "final"

    def request_final_approval(self, state: DevLoopState) -> dict[str, Any]:
        decision = self._interrupt_for_decision(state, "final_approval", final=True)
        return self._apply_decision(state, decision, final=True)

    def complete(self, state: DevLoopState) -> dict[str, Any]:
        return {"status": "completed", "audit_log": audit(state, "run_completed", "Final approval received")}

    def terminate_rejected(self, state: DevLoopState) -> dict[str, Any]:
        return {"status": "failed", "audit_log": audit(state, "run_rejected", "Human rejected the run")}

    def close(self) -> None:
        self.checkpoint_connection.close()
