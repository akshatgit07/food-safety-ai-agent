"""Trusted operator ingestion, not an unauthenticated catalog-write endpoint."""
import argparse
import os

from dotenv import load_dotenv

from app.services.catalog_repository import SqlProductRepository
from app.services.usda_catalog import fetch_usda_food


def main():
    parser = argparse.ArgumentParser(description="Import a branded USDA food into the canonical catalog")
    parser.add_argument("fdc_id", type=int)
    parser.add_argument("--env-file", help="Optional ignored environment file")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    try:
        product, source = fetch_usda_food(args.fdc_id)
        saved = SqlProductRepository(seed_demo=os.getenv("CATALOG_SEED_DEMO", "true").lower() == "true").upsert(product, source)
    except ValueError as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Saved {saved.product_id}: {saved.name}. Allergen and diet compatibility remain unverified.")


if __name__ == "__main__":
    main()
