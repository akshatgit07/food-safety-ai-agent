"""Build embeddings explicitly, never as part of an end-user request."""
import argparse
import os

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from app.services.catalog_embeddings import DIMENSIONS, MODEL, EmbeddingStore, product_text, valid_vector
from app.services.catalog_repository import SqlProductRepository


def index_catalog(repository, client, limit: int = 100) -> dict:
    store = EmbeddingStore()
    pending = []
    skipped = 0
    for product in repository.iter_products():
        if store.load_many([product]):
            skipped += 1
            continue
        pending.append(product)
        if len(pending) >= limit:
            break
    indexed = 0
    for start in range(0, len(pending), 32):
        batch = pending[start:start + 32]
        response = client.embeddings.create(model=MODEL, dimensions=DIMENSIONS,
                                            input=[product_text(p) for p in batch])
        by_index = {item.index: item.embedding for item in response.data}
        if (len(response.data) != len(batch) or set(by_index) != set(range(len(batch)))
                or any(not valid_vector(v) for v in by_index.values())):
            raise ValueError("Embedding provider returned incomplete or invalid vectors")
        for index, product in enumerate(batch):
            store.save(product, by_index[index])
            indexed += 1
    return {"indexed": indexed, "unchanged": skipped, "model": MODEL, "dimensions": DIMENSIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be between 1 and 1000")
    if not os.getenv("OPENAI_API_KEY"):
        parser.exit(1, "OPENAI_API_KEY is required for offline catalog indexing.\n")
    try:
        # Intentionally not auto-traced: catalog indexing contains no user flow,
        # and no provider payload needs to leave through the tracing integration.
        with OpenAI(timeout=30, max_retries=1) as client:
            print(index_catalog(SqlProductRepository(), client, args.limit))
    except (OpenAIError, ValueError):
        parser.exit(1, "Catalog indexing failed; check provider access and catalog input. No credentials logged.\n")


if __name__ == "__main__":
    main()
