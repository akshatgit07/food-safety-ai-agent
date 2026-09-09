# Food Safety AI Agent

Agentic nutrition intelligence layer for Guiltless.

## Built today
- FastAPI backend (`backend/`) deployed to Render
- Next.js frontend (`frontend/`) deployed to Vercel
- Deterministic product scoring, comparison, and bag optimization (no LLM required)
- Label scanning from pasted text; OpenAI vision when `OPENAI_API_KEY` is set
- Keyword intent router (`backend/app/agent/`) calling internal tools directly
- Deterministic workout and trainer client planning
- OpenAI-backed nutrition chat, meal plans, and shopping lists
- USDA FoodData Central lookups with a local fallback table
- SQLAlchemy persistence: profile, bag, plans, trainer clients, checkout sessions
- Mock retailer/Instacart checkout handoff

## Not built yet
These are on the roadmap and are **not** in the codebase today. Do not read them as
shipped capability:
- LangGraph multi-agent workflow (the router is keyword-based, not agentic planning)
- RAG retrieval pipeline / ChromaDB vector store
- Critic-agent review loop
- Real retailer checkout (the Instacart handoff returns a mock URL)
- Authentication (every endpoint is unauthenticated and shares one demo user)

## Architecture
Request -> intent router -> deterministic tool or OpenAI call -> SQLAlchemy persistence

## Product intelligence

The FastAPI backend exposes deterministic product-scoring workflows that do not require an OpenAI API call:

- `POST /product/explain` explains one product's nutrition score.
- `POST /product/scan` extracts a product from pasted label text or an uploaded label image.
- `POST /product/compare` compares two or more products against a nutrition goal.
- `POST /bag/optimize` scores a shopping bag and previews higher-scoring swaps.
- `POST /workout-plan` builds a structured weekly workout split.
- `POST /coach/client-plan` creates a connected nutrition, workout, and shopping foundation for a trainer's client.
- `GET /coach/clients` and `GET /coach/clients/{id}/plans` expose persistent trainer client history.
- `POST /checkout/prepare` normalizes a shopping list into a persistent retailer handoff session.
- `POST /copilot/chat` uses product, goal, bag, and preference context. It has a deterministic fallback when OpenAI is not configured.

The Next.js frontend includes a Product Intelligence demo for selecting products, comparing results, and reviewing projected bag improvements.

## Scan-to-decision

The connected workflow begins with a deployable label scanner. Pasted nutrition text is parsed deterministically, while uploaded images use OpenAI vision when `OPENAI_API_KEY` is configured. Without that key, image uploads return a clearly marked demo fallback so the founder demo remains usable. A successful scan becomes the active product context for explainability, comparison, bag optimization, and Copilot routing.

## Agentic Copilot routing

`POST /copilot/chat` uses the lightweight router in `backend/app/agent/` to select one of these workflows:

- product explanation
- product comparison
- bag optimization
- meal planning
- shopping-list generation
- recipes
- general nutrition chat

Every response includes `intent`, `response`, `suggested_actions`, and `tool_result`. Deterministic product tools run without OpenAI. Generative tools use `OPENAI_API_KEY`, and routing failures fall back to normal chat.

## Agentic actions and trainer mode

The Copilot action recommender can suggest product explanation, comparison, bag optimization, meal planning, workout planning, trainer client planning, shopping-list creation, and checkout preparation. Workout and coach plans are deterministic and deployable without an OpenAI key. The frontend keeps the consumer Product Intelligence workflow intact and adds a separate Consumer / Coach planning workspace below it.

## Persistent product layer

SQLAlchemy models in `backend/app/db.py` store demo-user preferences, products, scan history, bag items, meal and workout plans, trainer clients and plans, Copilot messages, and checkout sessions. The Phase 4 frontend workspace exposes profile memory, the persistent bag, saved plans, trainer client history, and a mock Instacart handoff.

- `GET|PUT /profile/demo-user`
- `GET /bag/demo-user`, `POST /bag/demo-user/add`, `DELETE /bag/demo-user/clear`
- `GET /plans/demo-user`, `POST /plans/demo-user/meal`, `POST /plans/demo-user/workout`
- `POST /coach/clients`, `GET /coach/clients/{client_id}/plans`, `POST /coach/clients/{client_id}/plans`
- `POST /checkout/instacart`

## Local development

Start the API:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 --env-file ../.env.local
```

Start the frontend in another terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend reads the backend base URL from `NEXT_PUBLIC_API_URL`.

## Environment variables

- `NEXT_PUBLIC_API_URL`: required by the frontend; use `http://localhost:8000` locally and the public API URL in Vercel.
- `OPENAI_API_KEY`: required for nutrition chat, meal plans, shopping lists, and enhanced Copilot responses. Product scoring and the Copilot fallback work without it.
- `OPENAI_MODEL`: optional; defaults to `gpt-4o-mini`.
- `OPENAI_VISION_MODEL`: optional model for food-label image extraction; defaults to `OPENAI_MODEL`.
- `USDA_API_KEY`: optional; meal enrichment uses the built-in fallback database without it.
- `ALLOWED_ORIGINS`: optional comma-separated CORS origins; defaults to `*`.
- `DATABASE_URL`: optional persistent PostgreSQL database URL. Local development falls back to `/tmp/guiltless_ai_phase4.db`.
- `COMMERCE_CHECKOUT_URL_TEMPLATE`: optional retailer handoff URL containing `{checkout_id}` and optionally `{retailer}`.

## Tests

Run backend service tests from the backend directory so Python resolves the backend `app` package:

```bash
cd backend
python3 -m unittest discover -s tests -v
```

Build the production frontend with:

```bash
cd frontend
npm run build
```

## Deployment

The backend must be deployed with **`backend/` as the service root** (see `render.yaml`).
The repository also contains a legacy top-level `app/main.py` stub that exposes only
`/` and `/health`; a service rooted at the repository root will boot and pass its
health check while serving none of the real API.

- Render: root directory `backend`, start command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`.
- Vercel: root directory `frontend`, with `NEXT_PUBLIC_API_URL` set to the Render URL.
- Without `DATABASE_URL` the backend falls back to SQLite under `/tmp`, which Render
  wipes on every deploy. Set a Postgres URL for anything that must survive a redeploy.

## Copilot orchestration

The personalized `/v2/copilot/chat` workflow adds canonical products, deterministic
G-Personal scoring, hard constraints, catalog swaps, and provenance. See the
[personalized copilot guide](docs/personalized-copilot.md) for APIs, scoring policy,
local testing, implementation files, and limitations. Legacy routes remain intact.

`POST /copilot/chat` now runs a LangGraph workflow:
`load_context → detect_intent → tool/chat → respond`, with a chat fallback for
missing tool context. Existing product, bag, meal, workout, client, and checkout
services remain the tools; product scoring does not require an LLM call.
The graph follows the [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).

Send `load_memory: true` to load saved preferences, bag contents, the latest meal
plan, recent scans, and the last six messages. Explicit request context overrides
saved defaults, including empty lists. Memory remains in SQLAlchemy, using the
existing `DATABASE_URL` (Postgres on Render, SQLite for local demos).
No Redis, graph server, or new API key is required.

```bash
curl http://localhost:8000/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Build me a 5 day meal plan","user_id":"demo-user","load_memory":true}'
```

The response retains `intent`, `response`, `suggested_actions`, `tool_result`,
`mode`, `routing_error`, and `context_used`. Shopping-list requests can now use
the latest saved meal plan without resending it. General chat receives saved
restrictions and recent conversation history. Provider HTTP failures continue
to surface as errors; tools are not automatically retried because some write data.

Run graph and API regression tests against a disposable database:

```bash
cd backend
DATABASE_URL=sqlite:////tmp/guiltless-graph-tests.db python -m unittest discover -s tests -v
```

This is a bounded, one-tool-per-request workflow, not a multi-step autonomous
planner. There is no graph checkpoint replay. User IDs remain demo identifiers,
not authenticated identities; add authentication before exposing private user
memory publicly. USDA lookup exists separately; hybrid retrieval, pgvector,
Redis caching, and reranking remain future work. `OPENAI_API_KEY` enables the
existing AI chat/planning path; deterministic product tools work without it.
