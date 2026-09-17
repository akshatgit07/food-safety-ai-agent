# Personalized Guiltless Copilot

## What is implemented

The existing Next.js/FastAPI monorepo and legacy endpoints are preserved.
`/v2/copilot/chat` uses canonical catalog records and a separate LangGraph:

`load_context → route_intent → product/planning service → validate_result → compose_response`

Product branches: explain, compare, find swap, and optimize bag. Meal planning,
shopping lists, and workout planning delegate to the existing service router.
General chat currently returns deterministic next-step guidance. Product
explanations are rendered from validated facts, without a model calculating or
rewriting scores. The optional composition interface rejects changes to the
approved response; unrestricted LLM composition is deliberately not enabled.

## Files and responsibilities

- `backend/app/domain/models.py`: canonical products, profiles, daily state,
  provenance, and personalized scoring contracts.
- `backend/app/domain/copilot.py`: v2 request/response validation.
- `backend/app/services/g_personal.py`: base-score reuse, hard constraints,
  and transparent personalized factors.
- `backend/app/services/product_lookup.py`: exact lookup plus repository/cache
  protocols and a four-product development catalog.
- `backend/app/services/product_retriever.py`: candidate retrieval protocol,
  hard filtering, and local lexical relevance.
- `backend/app/services/product_reranker.py`: deterministic ranking.
- `backend/app/services/personalized_tools.py`: explanation/comparison/swaps
  and bag optimization over catalog records.
- `backend/app/services/result_validator.py`: reference, constraint, fact,
  scoring, bag-total, and composition validation.
- `backend/app/agents/guiltless_graph.py`: orchestration and provenance.
- `backend/app/main.py`: v2 routes, retaining existing routes.
- `backend/tests/test_personalization.py`: scoring, retrieval, validation,
  graph, and API regression tests.
- `frontend/app/components/PersonalizedCopilot.tsx`: connected personal-score
  preview; `ProductIntelligence.tsx` applies real swaps to shared demo state.
- `frontend/app/globals.css`: green/white panel styling and yellow actions.
- `frontend/app/components/Phase4ProductLayer.tsx`: product-facing copy.

## APIs

- `GET /v2/products`: development catalog, with provenance on each record.
- `GET /v2/products/lookup?barcode=000000000002`: exact barcode match; leading
  zeroes are significant. Alternatively pass `product_id=demo-bar`. Missing
  records return 404; supplying both identifiers returns 422. No fuzzy fallback.
- `POST /v2/copilot/chat`: structured, grounded workflow; validation failures
  return an empty tool result, errors, and zero confidence.

```bash
curl http://127.0.0.1:8000/v2/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Find a better alternative",
    "product_id": "demo-bar",
    "user_profile": {
      "primary_goal": "muscle gain",
      "protein_target": 120,
      "allergies": ["milk"],
      "dietary_preferences": ["vegan"]
    },
    "daily_nutrition_state": {"protein_consumed": 30}
  }'
```

For comparison/optimization use `bag_product_ids`, e.g.
`["demo-bar", "demo-yogurt", "demo-chickpeas"]`. Optional `load_memory: true`
loads saved profile defaults and catalog-addressable bag products. Explicit
profile fields override saved defaults. Legacy name-only bag records are not
matched heuristically. Shopping-list tools can use the latest saved meal plan;
`planning_context` may supply an explicit meal plan, equipment, or training days.

## Scoring policy

Version: `guiltless-v1/g-personal-v1`. Base quality uses the existing deterministic
rubric with the neutral goal, ignoring caller-supplied scores. Personal score
starts at base quality. Each macro contributes
`weight * min(serving amount, remaining need) / target`, with a bounded penalty
for exceeding the remaining need. Weights: protein 12, carbs 4, fat 4, calories 3.
Micronutrients contribute up to 3 points per target; nutrient keys must include
matching units (e.g. `calcium_mg`). Goal fit, dislikes, and preferred stores add
explicit factors. The final score is clamped to 0–100. Missing targets contribute
no target-specific bonus. The supplied daily date is returned for inspection;
the caller is responsible for supplying the correct day's intake.

Allergies, ingredient exclusions, and hard dietary flags exclude candidates
before ranking. Missing allergen information excludes a candidate when the user
has allergies. Unsupported dietary requirements are treated conservatively as
unconfirmed, not ignored. Common allergen aliases are included, but this is not
a complete food-ontology or cross-contact verification system.

Ranking uses `0.5 * personal_score + 20 * relevance + 0.3 * base_score_delta`
plus a ±2 price-fit adjustment when a `budget_preferences.max_price` is supplied.
Out-of-stock records are excluded. Unknown prices/inventory are labeled rather
than invented. Local relevance is token overlap plus a same-category bonus.
Scores compare one serving on the same declared nutrition basis. Bag scores
are unweighted means over supplied entries; duplicate entries count separately.
They are not a simulation of cumulative daily consumption.

## Local validation

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=sqlite:////tmp/guiltless-personal-tests.db python -m unittest discover -s tests -v
python -m compileall -q app
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
npm run build
```

In the UI, select Frosted Snack Bar, open “Good food. Better for your day.”,
and choose “Why for you?”. Enter a milk allergy, then find personalized swaps.
The current product becomes incompatible; the seed/oat bar and chickpea snack
remain eligible. Apply Swap updates the active product and matching demo bag
entries. It does not mutate the separate persisted bag. Preference changes clear
old results, and late responses cannot restore stale recommendations.

## Environment and remaining work

No new service credentials are required. `NEXT_PUBLIC_API_URL` connects the UI;
`DATABASE_URL` configures existing SQLAlchemy memory (Postgres on Render, SQLite
fallback locally). Render still uses `backend/` as its root. Existing LLM meal
planning needs `OPENAI_API_KEY`; existing USDA enrichment uses `USDA_API_KEY`.

This iteration is a development foundation, not verified nutrition or clinical
advice. Catalog provenance is explicitly unverified; confidence is a conservative
data-source indicator, not a calibrated probability. The catalog, availability,
and prices are fixtures. Redis/Postgres catalog adapters, pgvector/hybrid search,
live inventory, comprehensive allergen ontology, history-based ranking, profile
schema migrations for macro targets, authenticated users, and LLM phrase
selection remain future work. The current in-memory cache is process-local and
has no TTL; replace it before supporting catalog updates across workers.

Constrained meal/shopping recommendations in v2 fail closed until their
ingredients can be checked against a verified catalog. Legacy endpoints retain
their prior behavior and are not covered by the new validator. In particular,
the legacy bag demo still produces synthetic “Healthier…” suggestions; the new
personalized optimizer only uses existing records.

All phases were checked with backend tests/compilation and frontend builds.
Final automated suite: 99 tests. Browser verification covered score rendering,
allergy-result invalidation, safe swaps, shared-product/bag updates, and browser
console errors. No paid model requests or deployment were performed.
