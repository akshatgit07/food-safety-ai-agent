# LangSmith tracing

The backend uses the installed `langsmith-trace` skill's two patterns: automatic
LangGraph node tracing, plus `traceable` spans and `wrap_openai` for ordinary
Python services and OpenAI Responses calls. No frontend key is needed.

## Configuration

Set these variables in the backend environment:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<set privately>
LANGSMITH_PROJECT=food-safety-ai-agent
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

The supplied key is saved only in the git-ignored root `.env.local`. To run the
backend with that file, from `backend/`:

```bash
.venv/bin/python -m uvicorn app.main:app --env-file ../.env.local --reload
```

For Render, set `LANGSMITH_API_KEY` privately in the dashboard and change
`LANGSMITH_TRACING` to `true`. The blueprint defaults tracing to off. Optional
`LANGSMITH_WORKSPACE_ID` supports organization-scoped keys;
`LANGSMITH_ENDPOINT` selects a regional or self-hosted endpoint. Never set these
credentials as `NEXT_PUBLIC_*` variables. Restart the backend after changes:
the SDK client is reused for the process lifetime.

Inputs and outputs are hidden by default because graph state can contain
profiles, allergies, bag contents, and message history. Names, timings, errors,
token usage, and outcome metadata remain available. Exceptions may contain
application error text. Set the hide flags to `false` only in an environment
where recording request/response content is appropriate.

## Trace hierarchy

- `guiltless.copilot.v1` / `guiltless.copilot.v2`: API workflow roots.
- `guiltless.graph.v1` / `guiltless.graph.v2`: graph and named node spans.
- `guiltless.product.exact_lookup`: deterministic cache/repository lookup.
- `guiltless.alternatives.retrieve` and `.rerank`: filtered candidate pipeline.
- `guiltless.score.personal` and `guiltless.result.validate`: scoring/validation.
- `guiltless.memory.load`: persistent context loading.
- `guiltless.chat`, `guiltless.ai.generate`, and wrapped OpenAI spans: LLM work.
- `guiltless.meal_plan`, `guiltless.shopping_list`, and product endpoint spans.

API response contracts do not change. Structured failures are marked with
`outcome=fallback` and `validation_error_count`; they may be HTTP 200 responses
and should be inspected through metadata rather than HTTP errors alone.
Exceptions propagate as before and are not retried by instrumentation.
Missing credentials or disabled tracing leave the app usable. The SDK performs
background uploads; the FastAPI lifespan flushes its queue on graceful shutdown.
Abrupt process termination can lose queued spans. For short-lived deployments,
also set `LANGCHAIN_CALLBACKS_BACKGROUND=false` so graph callbacks finish before
request teardown.

## Verification

Run the normal regression suite with tracing disabled:

```bash
cd backend
LANGSMITH_TRACING=false DATABASE_URL=sqlite:////tmp/guiltless-trace-tests.db \
  .venv/bin/python -m unittest discover -s tests -v
```

With a configured backend running, send synthetic demo data:

```bash
curl http://localhost:8000/v2/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Find a better alternative","product_id":"demo-bar"}'
```

Then use the installed CLI with `LANGSMITH_API_KEY` in its environment:

```bash
langsmith trace list --project food-safety-ai-agent \
  --limit 1 --show-hierarchy --include-metadata
```

CLI v0.2.54's `--name` filter returned a server-side filter parsing error during
verification; omit it and select the desired root from the returned traces.
A synthetic v2 swap request was verified with 28 linked spans in the configured
project. The current regression suite passes 118 tests; frontend build passes.

The installed skills are `langsmith-trace`, `langsmith-dataset`, and
`langsmith-evaluator` under the user's Codex skills directory. Dataset creation
and evaluation execution are separate workflows and are not run automatically.
