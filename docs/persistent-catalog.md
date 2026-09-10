# Persistent catalog and USDA sourcing

The canonical catalog now lives in the `catalog_products` SQLAlchemy table.
This is an additive table, separate from legacy `products`/scan history, so
existing bag and scan IDs remain untouched. The same `DATABASE_URL` powers both;
use Postgres on Render for persistence across restarts. SQLite remains supported
for local development. Existing installations create the new table on first use.

## Product flow

Exact identifier → process-local cache (60-second TTL) → SQL catalog record.
Neither a missing barcode nor an unknown ID invokes fuzzy search. Barcodes are
strings; leading zeroes are preserved. A unique database constraint prevents
two records sharing a barcode. Conflicts abort the import instead of silently
reassigning product identity. CLI imports do not notify running workers; cached
records expire within 60 seconds or are refreshed on backend restart.

Alternative retrieval scans the catalog in keyset batches, applies safety rules
before shortlisting, and combines text relevance with stored product embeddings
when available. The first-50-record cutoff is removed. See
[hybrid retrieval](hybrid-retrieval.md) for indexing and optional pgvector setup.

`GET /v2/products?limit=100&offset=0` is paginated (limit 1–100). Existing clients
still receive a list. `GET /v2/products/lookup?barcode=...` retains its contract.
The UI exposes exact barcode lookup, source and serving information, and uses
stable IDs when selecting products or applying swaps. A barcode lookup changes
the active product without changing the bag. Unknown scans are not matched to
catalog items solely because their names happen to agree.

## Import a USDA branded food

Supply an explicit FoodData Central ID chosen from the USDA site. This operation
runs locally as a trusted operator; there is no public catalog-write endpoint.

```bash
cd backend
python -m app.catalog_cli 123456 --env-file ../.env.local
```

Replace `123456` with a real branded-food FDC ID and configure `USDA_API_KEY`
privately. `DATABASE_URL` must point to the database used by the app. The command
fetches that exact ID, validates it, and commits the canonical record and original
source JSON together. Product IDs are stable (`usda-<fdcId>`). Reimporting the same
ID updates it; it does not create another product.

The USDA key is configured in the ignored local environment file. Live access
and import were verified with FDC ID `2607273` (Esti Foods plain Greek yogurt),
stored locally as `usda-2607273`, barcode `0855616007802`. The importer supports
USDA's `GRM` gram code as well as `g`. The key still needs separate configuration
in Render; it is never included in the repository.

## Source quality and units

The importer uses USDA's [Food Details API](https://fdc.nal.usda.gov/api-guide/).
It prefers declared label values per serving. For gram-based servings only,
missing label values can be converted from the nutrient table's standardized
100-gram values. USDA describes that basis in its
[Branded Foods documentation](https://fdc.nal.usda.gov/GBFPD_Documentation/).
Liquid servings require per-serving label values; density is never invented.
Energy must be kcal, not kJ. Missing/invalid scoring nutrients, ambiguous nutrient
rows, unsupported serving units, wrong IDs, and malformed barcodes stop imports.
Missing values are not silently replaced with zeros.

Provenance retains the FDC reference URL and retrieval timestamp. “USDA sourced”
does not mean independently verified or allergen-safe: `verified` remains false,
allergen completeness remains false, and diet flags remain empty. Therefore
imported products are excluded when user hard constraints cannot be confirmed.
Manufacturer labels can be rounded or stale; confidence is a source indicator,
not a medical assurance. Serving-size metadata is preserved separately.

## Demo seeding and operations

`CATALOG_SEED_DEMO=true` (default) inserts the four existing demo records on first
use without overwriting stored records. Set it to `false` for a fresh real-only
database. Turning it off does not delete demo records already present. No Redis
credentials or schema-altering migration of old tables are required.

Files added: `catalog_repository.py`, `usda_catalog.py`, `catalog_cli.py`, and
`test_catalog.py`. Modified: DB models, provenance model, exact cache, API catalog
wiring, and the two connected product UI components. Existing uncommitted tracing
and personalization-hardening work is preserved.

```bash
cd backend
LANGSMITH_TRACING=false DATABASE_URL=sqlite:////tmp/guiltless-catalog-tests.db \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app
cd ../frontend
npm run build
```

Remaining work: reviewed
allergen metadata, indexed retrieval for large catalogs, Redis invalidation,
production migration management, and authenticated catalog administration.
