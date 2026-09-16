from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    blocked = "blocked"
    needs_approval = "needs_approval"
    retrying = "retrying"
    completed = "completed"
    failed = "failed"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class HumanAction(str, Enum):
    approve = "approve_recommended_fix"
    revise = "ask_agent_to_revise"
    retry = "retry"
    skip = "skip_task"
    reject = "reject"
    open_logs = "open_logs"


class Task(BaseModel):
    id: str
    title: str
    description: str
    domain: Literal["planning", "backend", "frontend", "data", "security", "payments", "qa", "deployment"]
    status: TaskStatus = TaskStatus.pending
    risk_level: RiskLevel = RiskLevel.low
    approval_required: bool = False
    attempts: int = 0
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    task_id: str
    success: bool
    summary: str
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    recoverable: bool = False
    idempotency_key: str


class ValidationResult(BaseModel):
    success: bool
    summary: str
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None
    explained: bool = True
    confidence: float = Field(default=1.0, ge=0, le=1)


class FeatureRunRequest(BaseModel):
    feature_request: str = Field(min_length=8, max_length=10_000)
    max_retries: int = Field(default=2, ge=0, le=5)
    confidence_threshold: float = Field(default=0.7, ge=0.5, le=1)
    scenario: Literal["normal", "fail_once", "always_fail"] = "normal"


class HumanDecisionRequest(BaseModel):
    approval_id: str = Field(min_length=8, max_length=100)
    action_id: str = Field(min_length=8, max_length=100)
    action: HumanAction
    comment: str = Field(default="", max_length=2000)


class DevLoopState(TypedDict, total=False):
    run_id: str
    feature_request: str
    requirements: list[str]
    assumptions: list[str]
    implementation_plan: dict[str, Any]
    tasks: list[dict[str, Any]]
    current_task: str | None
    task_results: list[dict[str, Any]]
    code_changes: list[str]
    test_results: list[dict[str, Any]]
    build_results: list[dict[str, Any]]
    deployment_preview: dict[str, Any]
    errors: list[dict[str, Any]]
    retry_count: int
    risk_level: str
    approval_required: bool
    human_decisions: list[dict[str, Any]]
    status: str
    audit_log: list[dict[str, Any]]
    max_retries: int
    confidence_threshold: float
    scenario: str
    failure_diagnosis: dict[str, Any]
    escalation_reason: str
    escalation_outcome: str

