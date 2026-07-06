# Food Safety AI Agent

Production-grade Nutrition Intelligence Platform.

## Features
- FastAPI backend
- LangGraph multi-agent workflow
- USDA FoodData Central ingestion
- RAG retrieval pipeline
- Ingredient risk scoring
- Explainable product comparison and bag optimization
- LLM reasoning + critic agent
- Next.js frontend
- PostgreSQL support
- Docker deployment

## Architecture
Ingestion Agent -> Retrieval Agent -> Reasoning Agent -> Critic Agent -> Finalizer

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

## Planned Stack
FastAPI, LangGraph, OpenAI, ChromaDB, PostgreSQL, Next.js, Docker.
