"""Exact identifiers only. Redis and Postgres adapters can implement protocols."""
import threading
import time
from collections import OrderedDict
from app.observability import observed
from typing import Protocol

from app.domain.models import Product
from app.services.g_personal import base_score


class ProductRepository(Protocol):
    def by_id(self, product_id: str) -> Product | None: ...
    def by_barcode(self, barcode: str) -> Product | None: ...


class ProductCache(Protocol):
    def get(self, key: str) -> Product | None: ...
    def put(self, key: str, product: Product) -> None: ...


class MemoryCache:
    """Process-local LRU. The instance is shared across requests, and FastAPI runs
    sync endpoints on a threadpool, so every mutation is guarded."""

    def __init__(self, capacity: int = 256, ttl_seconds: float = 60):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._expires: dict[str, float] = {}
        self.items: OrderedDict[str, Product] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Product | None:
        with self._lock:
            if self._expires.get(key, 0) <= time.monotonic():
                self.items.pop(key, None)
                self._expires.pop(key, None)
                return None
            product = self.items.get(key)
            if product is not None:
                self.items.move_to_end(key)
        return product.model_copy(deep=True) if product else None

    def put(self, key: str, product: Product) -> None:
        copy = product.model_copy(deep=True)
        with self._lock:
            self.items[key] = copy
            self._expires[key] = time.monotonic() + self.ttl_seconds
            self.items.move_to_end(key)
            while len(self.items) > self.capacity:
                expired_key, _ = self.items.popitem(last=False)
                self._expires.pop(expired_key, None)


class MemoryProductRepository:
    def __init__(self, products: list[Product]):
        self.products = {p.product_id: p.model_copy(deep=True) for p in products}
        self.barcodes = {p.barcode: p.product_id for p in products if p.barcode}
        if len(self.products) != len(products) or len(self.barcodes) != len([p for p in products if p.barcode]):
            raise ValueError("Duplicate product identifier")

    def by_id(self, product_id: str) -> Product | None:
        p = self.products.get(product_id)
        return p.model_copy(deep=True) if p else None

    def by_barcode(self, barcode: str) -> Product | None:
        return self.by_id(self.barcodes.get(barcode, ""))


class ProductLookup:
    def __init__(self, repository: ProductRepository, cache: ProductCache | None = None):
        self.repository, self.cache = repository, cache

    @observed("guiltless.product.exact_lookup", "tool")
    def find(self, *, barcode: str | None = None, product_id: str | None = None) -> Product | None:
        if (barcode is None) == (product_id is None):
            raise ValueError("Supply exactly one barcode or product_id")
        # Preserve leading zeroes and never use fuzzy matching for identifiers.
        key = f"barcode:{barcode}" if barcode is not None else f"id:{product_id}"
        cached = self.cache.get(key) if self.cache else None
        if cached is not None:
            return cached
        product = self.repository.by_barcode(barcode) if barcode is not None else self.repository.by_id(product_id)
        if product:
            product.base_score = base_score(product)
            if self.cache:
                self.cache.put(key, product)
        return product


def demo_catalog() -> list[Product]:
    rows = [
        ("demo-yogurt", "000000000001", "Plain Greek Yogurt", "Daily Cultures", "Yogurt", 120, 17, 5, 0, 0, 5, 65, ["cultured milk"], ["milk"], ["vegetarian", "gluten-free"], 1.8),
        ("demo-bar", "000000000002", "Frosted Snack Bar", "Quick Bite", "Snack bar", 260, 3, 44, 8, 1, 24, 310, ["oats", "corn syrup", "artificial flavor", "milk"], ["milk", "gluten"], ["vegetarian"], 1.4),
        ("demo-chickpeas", "000000000003", "Roasted Chickpea Bites", "Good Crunch", "Snack", 180, 9, 24, 6, 6, 2, 220, ["chickpeas", "olive oil", "spices"], [], ["vegan", "vegetarian", "gluten-free", "dairy-free"], 1.6),
        ("demo-oat-bar", "000000000004", "Seed & Oat Protein Bar", "Good Crunch", "Snack bar", 190, 14, 22, 6, 5, 5, 180, ["certified gluten-free oats", "pumpkin seeds", "pea protein"], [], ["vegan", "vegetarian", "gluten-free", "dairy-free"], 2.1),
    ]
    products = []
    for pid, barcode, name, brand, category, calories, protein, carbs, fat, fiber, sugar, sodium, ingredients, allergens, flags, price in rows:
        p = Product(product_id=pid, barcode=barcode, name=name, brand=brand, category=category,
                    nutrition={"calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "fiber_g": fiber, "sugar_g": sugar, "sodium_mg": sodium},
                    ingredients=ingredients, allergens=allergens, allergen_info_complete=True, diet_flags=flags,
                    provenance={"source": "guiltless_demo_catalog", "verified": False, "confidence": 0.3, "reference": pid},
                    price=price, in_stock=True, stores=["Demo store"])
        p.base_score = base_score(p)
        products.append(p)
    return products
