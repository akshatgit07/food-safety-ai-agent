from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any

from .models import RiskLevel, Task, TaskResult, ValidationResult


class PlanningProvider(ABC):
    @abstractmethod
    def analyze(self, feature_request: str) -> dict[str, Any]: ...

    @abstractmethod
    def create_plan(self, feature_request: str, analysis: dict[str, Any], scenario: str) -> dict[str, Any]: ...


class CodingProvider(ABC):
    @abstractmethod
    def execute(self, task: Task, context: dict[str, Any], idempotency_key: str) -> TaskResult: ...


class TestProvider(ABC):
    @abstractmethod
    def validate_task(self, task: Task, result: TaskResult, context: dict[str, Any]) -> ValidationResult: ...

    @abstractmethod
    def validate_integration(self, context: dict[str, Any]) -> ValidationResult: ...


class DeploymentProvider(ABC):
    @abstractmethod
    def create_preview(self, context: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...


class NotificationProvider(ABC):
    @abstractmethod
    def send_escalation(self, payload: dict[str, Any], dedupe_key: str) -> dict[str, Any]: ...


class ApprovalProvider(ABC):
    @abstractmethod
    def requires_approval(self, task: Task) -> bool: ...


class MockPlanningProvider(PlanningProvider):
    HIGH_RISK = re.compile(r"\b(auth|oauth|security|payment|billing|checkout|delete user|user data deletion|drop table|destructive migration)\b", re.I)

    def analyze(self, feature_request: str) -> dict[str, Any]:
        ambiguous = len(feature_request.split()) < 5 or bool(re.search(r"\b(something|somehow|whatever)\b", feature_request, re.I))
        requirements = [part.strip() for part in re.split(r"[.;\n]", feature_request) if part.strip()]
        return {"requirements": requirements or [feature_request],
                "assumptions": ["Work happens in an isolated branch/worktree", "No production mutation is permitted by mock providers"],
                "ambiguous": ambiguous, "confidence": 0.45 if ambiguous else 0.92}

    def create_plan(self, feature_request: str, analysis: dict[str, Any], scenario: str) -> dict[str, Any]:
        lowered = feature_request.lower()
        domain = ("security" if any(x in lowered for x in ("auth", "security")) else
                  "payments" if any(x in lowered for x in ("payment", "billing")) else
                  "data" if any(x in lowered for x in ("schema", "migration", "database")) else
                  "deployment" if any(x in lowered for x in ("deploy", "infrastructure")) else "backend")
        tasks = [{"id": "task-1", "title": "Implement feature", "description": feature_request,
                  "domain": domain,
                  "metadata": {"scenario": scenario}}]
        if any(x in lowered for x in ("ui", "frontend", "dashboard", "screen")):
            tasks.append({"id": f"task-{len(tasks)+1}", "title": "Implement user interface", "description": "Build the requested interface", "domain": "frontend", "metadata": {}})
        tasks.append({"id": f"task-{len(tasks)+1}", "title": "Run regression checks", "description": "Run relevant tests and builds", "domain": "qa", "metadata": {}})
        return {"summary": f"Deliver {len(tasks)} bounded tasks with validation after each task", "tasks": tasks,
                "confidence": analysis["confidence"]}


class MockCodingProvider(CodingProvider):
    def execute(self, task: Task, context: dict[str, Any], idempotency_key: str) -> TaskResult:
        return TaskResult(task_id=task.id, success=True, summary=f"Mock implementation completed for {task.title}",
                          artifacts=[f"mock://changes/{task.id}"], logs=["Provider executed in dry-run mode"],
                          confidence=0.9, idempotency_key=idempotency_key)


class MockTestProvider(TestProvider):
    def validate_task(self, task: Task, result: TaskResult, context: dict[str, Any]) -> ValidationResult:
        scenario = task.metadata.get("scenario", "normal")
        if scenario == "always_fail" or (scenario == "fail_once" and task.attempts == 1):
            return ValidationResult(success=False, summary="Mock validation failed", error="Deterministic test failure",
                                    evidence=[f"attempt={task.attempts}"], explained=True, confidence=0.95)
        return ValidationResult(success=True, summary="Task checks passed", evidence=["mock tests passed", "mock build passed"], confidence=0.98)

    def validate_integration(self, context: dict[str, Any]) -> ValidationResult:
        return ValidationResult(success=True, summary="Integration checks passed", evidence=["all completed tasks integrated"], confidence=0.98)


class MockDeploymentProvider(DeploymentProvider):
    def create_preview(self, context: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        return {"status": "mock_ready", "url": f"https://preview.invalid/{context['run_id']}",
                "production_changed": False, "idempotency_key": idempotency_key}


class DeterministicApprovalProvider(ApprovalProvider):
    def requires_approval(self, task: Task) -> bool:
        return task.risk_level == RiskLevel.high or task.domain in {"security", "payments"}


# Exact-phrase matching ("drop table", "destructive migration") missed common,
# equally destructive phrasings - "drops the legacy_users table", "purge inactive
# customer records", "truncate the orders table" all classified as merely medium
# risk and ran without a human approval gate. Any destructive verb is now treated
# as high risk when the task is already in a data/deployment context, rather than
# requiring one of a few exact phrases.
DESTRUCTIVE_PHRASES = ("delete user", "user data deletion", "drop table", "destructive migration")
DESTRUCTIVE_VERBS = re.compile(r"\b(drop\w*|delet\w*|truncat\w*|purg\w*|eras\w*|wip\w*|destroy\w*)\b", re.I)


def classify_risk(task: Task) -> RiskLevel:
    text = f"{task.title} {task.description}".lower()
    destructive = (any(term in text for term in DESTRUCTIVE_PHRASES)
                   or (task.domain in {"data", "deployment"} and DESTRUCTIVE_VERBS.search(text)))
    if task.domain in {"security", "payments"} or destructive:
        return RiskLevel.high
    if task.domain in {"data", "deployment"} or "migration" in text:
        return RiskLevel.medium
    return RiskLevel.low
