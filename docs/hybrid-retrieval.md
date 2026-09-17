# Hybrid alternative discovery

The v2 copilot searches the entire persistent catalog in batches, filters allergy,
diet, stock and nutrition-basis incompatibilities, then selects up to 50 relevant
candidates for deterministic nutrition reranking. At most five are returned.
Unsafe first-page records cannot hide safe products later in the catalog.

Text relevance includes the current product, category and request text. Optional
semantic similarity uses the **current product's stored embedding**, not a live
embedding of the user's question. Similarity does not override hard constraints,
source provenance or final factual validation. Product scores remain deterministic.

## Offline indexing

`catalog_embeddings` is an additive SQLAlchemy table, created alongside existing
tables. Embeddings use `text-embedding-3-small` with 256 dimensions. Only product
name, category and ingredients are sent to OpenAI. No profile or chat data is sent.
An input fingerprint invalidates embeddings when semantic source content changes.
Invalid, stale or missing vectors fall back to text matching per product.

```bash
cd backend
.venv/bin/python -m app.catalog_index_cli --env-file ../.env.local --limit 100
```

Requires the existing private `OPENAI_API_KEY` and the same `DATABASE_URL` as the
backend. With no database URL, the existing local SQLite fallback is used. The
command indexes at most 100 changed/missing records by default; repeat it for a
larger catalog. Unchanged records are skipped. Provider errors do not write the
failed batch; earlier completed batches remain saved. Index after USDA imports.
Requests do not make live embedding calls and need no OpenAI key for retrieval.

## SQLite and optional Postgres vector distance

`CATALOG_VECTOR_BACKEND=local` (default) calculates exact cosine distance locally
using persisted vectors. It works with SQLite and Postgres.

For optional database-side vector distance, a Postgres administrator must enable
the extension once on the target database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then set `CATALOG_VECTOR_BACKEND=pgvector` on the backend. Safe, fingerprint-checked
vectors are passed as bound parameters in batches. Missing extension/unsupported
database falls back to local cosine; the returned `retrieval.vector_backend`
reports the backend actually used. No extension or index is created automatically.

This version performs **exact batched search, not HNSW/ANN indexed search**. It
still scans all products and has linear cost. For large production catalogs,
materialize typed vectors and use a carefully evaluated filtered index. Live
Postgres integration must be validated in the deployment environment; SQLite
does not prove the extension or managed-host permissions are configured.

Each alternative includes retrieval method, lexical score, semantic score when
available, and fallback reason. The UI describes whether catalog text or both
text and product meaning supplied the match. Legacy `semantic_similarity` is
retained for compatibility and represents combined retrieval relevance; use
`retrieval.semantic_score` for pure cosine similarity.

## Validation

```bash
cd backend
LANGSMITH_TRACING=false DATABASE_URL=sqlite:////tmp/guiltless-hybrid-tests.db \
  .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall -q app
cd ../frontend
npm run build
```

References: [OpenAI embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small),
[pgvector cosine distance](https://github.com/pgvector/pgvector).
