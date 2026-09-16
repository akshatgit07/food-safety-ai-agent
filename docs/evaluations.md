# LangSmith datasets and quality checks

Two reviewed synthetic datasets are versioned in `backend/evals/data/`:

| Dataset | Cases | Coverage |
| --- | ---: | --- |
| helper-v1 | 13 | App guidance, score-source boundaries, logging guidance, review-only actions, missing/invalid inputs |
| personalization-v1 | 14 | Explain/compare/optimize routing, allergy and vegan exclusions, allergy override attempts, exact barcodes, constrained-plan refusal |

These are regression fixtures, not proof of medical safety, complete language
understanding, production performance, or USDA data accuracy. They exercise the
actual FastAPI endpoints in-process. They do not evaluate generative meal plans,
open-ended chat quality, trajectory ordering, live pgvector/USDA retrieval,
authenticated memory, or the mobile app's separate score formula.

## Local quality gate

```bash
cd backend
.venv/bin/python -m evals.run
```

No API key is needed. The runner creates a temporary SQLite database, seeds the
fixed demo catalog, disables application tracing, removes OpenAI credentials from
its process, and never loads production profiles/history. It must run in a fresh
process. Existing local and Render databases remain untouched. A machine-readable
report is written to ignored `evals/reports/latest.json`.

Six blocking metrics must pass for **every case**:

1. `response_contract`: expected HTTP status and structured fields.
2. `intent_match`: correct route for the case.
3. `reference_requirements`: expected score, product, compatibility, refusal, or guidance text.
4. `recommendation_safety`: excluded IDs stay out; required alternatives cannot be gamed with empty results.
5. `grounded_facts`: returned nutrition/base scores match independent golden values; synthetic sources stay unverified.
6. `action_permissions`: only known navigation/review actions; review requests require confirmation.

`latency_budget` reports a 2-second local request budget but is non-blocking to
avoid hardware-dependent CI failures. It is not a Render latency benchmark.
Metrics that do not apply to a particular case are treated as passing; compare
the case-specific references, not just the aggregate percentage.

The existing GitHub Actions backend job now runs the quality gate after unit
tests. It needs no LangSmith secret and performs no uploads. CI is active only
once this workflow change is pushed. Ten evaluator tests prove that malformed
contracts, wrong routes, fabricated facts, unsafe IDs, and invalid actions fail.

## Publish synthetic experiments

```bash
cd backend
.venv/bin/python -m evals.run --publish --env-file ../.env.local
```

Requires `LANGSMITH_API_KEY` and the LangSmith CLI. Optional:
`LANGSMITH_ENDPOINT`, `LANGSMITH_WORKSPACE_ID`, `LANGSMITH_PROJECT`.
Use `--langsmith-cli /path/to/langsmith` if necessary. The runner imports only
these LangSmith settings from the specified env file, not its database or LLM
credentials. CLI and SDK use the same environment connection.

Dataset names include a content hash. Repeating an unchanged upload reuses the
dataset after checking its examples; differing contents are never overwritten.
Each invocation creates a new experiment. Full synthetic inputs/outputs are
uploaded for inspection, without changing production trace redaction settings.
Experiment metadata includes the app commit, fixture hash, evaluation-code hash,
and `environment: isolated-sqlite`.

Evaluators execute locally through `evaluate(evaluators=[...])`; feedback is
uploaded to LangSmith. No online production evaluator or scheduled monitor was
installed. No LLM judge, token spend, or real user conversation export is involved.
Publishing waits for all local experiment results, requires all seven metric keys
on every example, and rejects failed blocking gates. LangSmith's remote feedback
index may lag; inspect per-example feedback before treating its dashboard as a
fully verified release report.

## Initial verified baseline

- 27/27 local cases passed all six release gates.
- 165 backend unit tests passed, including evaluator negative controls.
- Helper dataset: `guiltless-helper-v1-745997a72a` (13 examples).
- Personalization dataset: `guiltless-personalization-v1-94d066967b` (14 examples).

Inspect the failing case IDs in the local report or LangSmith feedback when a
future change fails. Do not automatically rewrite golden expectations to match
new output. Review intended policy changes and add counterexamples first.
