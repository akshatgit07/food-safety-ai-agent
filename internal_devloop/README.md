# Guiltless internal feature-development loop

This package is a separate internal FastAPI service inside the monorepo. It does
not import or run inside the consumer Guiltless backend. The separation keeps
coding permissions, checkpoints, Slack credentials, and execution failures away
from product traffic and health checks.

This is a **control-plane prototype**. Its coding, test, deployment, and Slack
providers are mocks. It records intended changes but does not edit a repository,
create branches, deploy applications, or contact Slack.

## Graph

```text
START → intake_feature → analyze_requirements → create_plan → classify_tasks
      → select_task → pre_execution_gate → execute_task → validate_task
          success ────────────────────────────────→ next_task
          safe failure → diagnose_failure → retry_task ─┘
          high risk / ambiguous / exhausted → create_human_escalation
                                             → interrupt/checkpoint
                                             → human decision → resume
      → integration_validation → request_final_approval → interrupt → complete
```

High-risk work pauses before execution. Deterministic policy covers ambiguous
requirements, low confidence, auth/security, payments, destructive migrations,
user-data deletion, unexplained tests, exhausted retries, and repeated deployment
failures. Automatic retries are bounded by `max_retries`.

## Persistence and idempotency

`DEVLOOP_DATABASE_PATH` selects a dedicated SQLite database and defaults to
`/tmp/guiltless_devloop.db`. LangGraph's SQLite saver persists graph checkpoints.
Separate tables journal dashboard state, notifications, decisions, and execution
attempts.

- `run_id` is also the LangGraph `thread_id`.
- Coding calls receive `run_id:task_id:attempt` as an idempotency key.
- Human `approval_id` and caller-generated `action_id` are unique.
- A duplicate decision returns current state without executing again.
- A decision persisted immediately before a crash can resume the still-pending
  checkpoint after restart.
- Mock Slack notifications have a stable dedupe key.

SQLite is appropriate for this single-process prototype. A production service
should use a supported Postgres checkpointer and transactional job/outbox tables,
plus a worker lease per run.

## Provider boundaries

Abstract interfaces live in `providers.py`:

- `PlanningProvider`
- `CodingProvider`
- `TestProvider`
- `DeploymentProvider`
- `NotificationProvider`
- `ApprovalProvider`

Future Codex or Claude Code implementations belong behind `CodingProvider`.
Provider-specific prompts, CLIs, credentials, and output parsing must not enter
the graph. Providers should honor idempotency keys and execute in isolated
worktrees/sandboxes.

## Run locally

```bash
backend/.venv/bin/python -m internal_devloop
```

Open `http://127.0.0.1:8090/dashboard` or use:

```bash
curl -X POST http://127.0.0.1:8090/runs \
  -H 'Content-Type: application/json' \
  -d '{"feature_request":"Add an internal dashboard with regression tests"}'

curl http://127.0.0.1:8090/approvals/pending
```

Submit the pending `approval_id` with a unique `action_id`:

```bash
curl -X POST http://127.0.0.1:8090/runs/RUN_ID/decisions \
  -H 'Content-Type: application/json' \
  -d '{"approval_id":"APPROVAL_ID","action_id":"ACTION_ID","action":"approve_recommended_fix","comment":"Reviewed"}'
```

Actions are `approve_recommended_fix`, `ask_agent_to_revise`, `retry`,
`skip_task`, `reject`, and `open_logs`.

## Tests

```bash
backend/.venv/bin/python -m unittest discover -s internal_devloop/tests -v
```

The suite covers the happy path, one safe retry, exhausted retries and Slack
escalation, approval resume, duplicate approval protection, pre-execution risk
gates, rejection, and checkpoint recovery after creating a new service instance.

## Production gaps

Before connecting a real coding backend: add SSO/RBAC, secret isolation, repository
and branch allowlists, sandboxed runners, signed Slack callbacks, CSRF protection,
webhook replay windows, Postgres advisory locks, cancellation/timeouts, artifact
retention, cost limits, provider conformance tests, and an explicit deployment
promotion policy. Keep production deployment and destructive operations behind a
second independent approval boundary.
