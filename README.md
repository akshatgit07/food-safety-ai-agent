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
- `POST /product/compare` compares two or more products against a nutrition goal.
- `POST /bag/optimize` scores a shopping bag and previews higher-scoring swaps.
- `POST /copilot/chat` uses product, goal, bag, and preference context. It has a deterministic fallback when OpenAI is not configured.

The Next.js frontend includes a Product Intelligence demo for selecting products, comparing results, and reviewing projected bag improvements.

## Local development

Start the API:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
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
- `USDA_API_KEY`: optional; meal enrichment uses the built-in fallback database without it.
- `ALLOWED_ORIGINS`: optional comma-separated CORS origins; defaults to `*`.

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
