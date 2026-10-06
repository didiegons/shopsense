import json
from pathlib import Path

from app.models.product import Product
from app.models.search import SearchRequest, SearchResponse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "catalog.json"


def load_catalog() -> list[Product]:
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        records = json.load(catalog_file)
    return [Product.model_validate(record) for record in records]


def search_catalog(
    filters: SearchRequest,
    products: list[Product] | None = None,
) -> SearchResponse:
    candidates = products if products is not None else load_catalog()
    results = [product for product in candidates if _matches(product, filters)]
    results.sort(key=lambda product: (product.offer.price, product.product_id))

    return SearchResponse(
        results=results,
        total=len(results),
        applied_filters=filters,
    )


def _matches(product: Product, filters: SearchRequest) -> bool:
    if filters.max_budget is not None:
        if product.offer.currency != "USD" or product.offer.price > filters.max_budget:
            return False

    if filters.min_ram_gb is not None:
        if product.specifications.ram_gb is None or product.specifications.ram_gb < filters.min_ram_gb:
            return False

    if filters.operating_system is not None:
        actual_os = product.specifications.operating_system
        if actual_os is None or not _operating_system_matches(actual_os, filters.operating_system):
            return False

    if filters.max_weight_kg is not None:
        if product.specifications.weight_kg is None or product.specifications.weight_kg > filters.max_weight_kg:
            return False

    if filters.category_filters:
        attributes = product.category_attributes or {}
        if any(attributes.get(key) != value for key, value in filters.category_filters.items()):
            return False

    return True


def _operating_system_matches(product_os: str, requested_os: str) -> bool:
    actual = product_os.casefold().strip()
    requested = requested_os.casefold().strip()
    if requested == "windows":
        return actual == "windows" or actual.startswith("windows ")
    return actual == requested