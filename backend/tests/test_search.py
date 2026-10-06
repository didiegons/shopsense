import pytest

from app.models.product import Product
from app.models.search import SearchRequest
from app.services.search import search_catalog


def product_ids(response):
    return {product["product_id"] for product in response.json()["results"]}


def test_budget_filter(client):
    response = client.post("/api/v1/search", json={"max_budget": 1000})

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert all(product["offer"]["price"] <= 1000 for product in response.json()["results"])
    assert response.json()["applied_filters"]["max_budget"] == 1000


def test_ram_filter(client):
    response = client.post("/api/v1/search", json={"min_ram_gb": 32})

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert all(product["specifications"]["ram_gb"] >= 32 for product in response.json()["results"])


def test_weight_filter(client):
    response = client.post("/api/v1/search", json={"max_weight_kg": 1.4})

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert all(product["specifications"]["weight_kg"] <= 1.4 for product in response.json()["results"])


def test_combined_hard_filters_and_applied_filters(client):
    filters = {
        "max_budget": 1000,
        "min_ram_gb": 16,
        "operating_system": "Windows 11",
        "max_weight_kg": 1.6,
    }
    response = client.post("/api/v1/search", json=filters)

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert response.json()["applied_filters"] == filters
    for product in response.json()["results"]:
        assert product["offer"]["price"] <= filters["max_budget"]
        assert product["specifications"]["ram_gb"] >= filters["min_ram_gb"]
        assert product["specifications"]["operating_system"] == filters["operating_system"]
        assert product["specifications"]["weight_kg"] <= filters["max_weight_kg"]


def test_windows_family_filter_matches_windows_11_products(client):
    response = client.post("/api/v1/search", json={"operating_system": "Windows"})

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert all(
        product["specifications"]["operating_system"].startswith("Windows")
        for product in response.json()["results"]
    )


def test_windows_11_filter_remains_version_specific(client):
    response = client.post("/api/v1/search", json={"operating_system": "Windows 11"})

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert all(
        product["specifications"]["operating_system"] == "Windows 11"
        for product in response.json()["results"]
    )


def test_generic_category_product_needs_no_laptop_specifications():
    camera = Product.model_validate(
        {
            "product_id": "demo-camera-001",
            "brand": "Camera Demo",
            "model_name": "Frame One",
            "category": "camera",
            "category_attributes": {"sensor_format": "full-frame", "megapixels": 24},
            "offer": {
                "price": 899,
                "currency": "USD",
                "availability": "in_stock",
                "source": {
                    "source_name": "ShopSense Demo Catalog",
                    "source_url": "https://example.invalid/demo/camera-001",
                    "source_checked_date": "2026-09-30",
                    "data_status": "demo",
                },
            },
        }
    )

    assert camera.specifications.ram_gb is None
    assert camera.specifications.weight_kg is None
    assert camera.specifications.operating_system is None

    response = search_catalog(
        SearchRequest(category_filters={"sensor_format": "full-frame"}),
        products=[camera],
    )

    assert response.total == 1
    assert response.results[0].category_attributes == {"sensor_format": "full-frame", "megapixels": 24}

    laptop_filter_response = search_catalog(
        SearchRequest(min_ram_gb=16, category_filters={"sensor_format": "full-frame"}),
        products=[camera],
    )
    assert laptop_filter_response.total == 0


def test_category_filter_is_a_hard_exact_match():
    camera = Product.model_validate(
        {
            "product_id": "demo-camera-002",
            "brand": "Camera Demo",
            "model_name": "Crop Two",
            "category": "camera",
            "category_attributes": {"sensor_format": "aps-c"},
            "offer": {
                "price": 599,
                "currency": "USD",
                "availability": "in_stock",
                "source": {
                    "source_name": "ShopSense Demo Catalog",
                    "source_url": "https://example.invalid/demo/camera-002",
                    "source_checked_date": "2026-09-30",
                    "data_status": "demo",
                },
            },
        }
    )

    response = search_catalog(
        SearchRequest(category_filters={"sensor_format": "full-frame"}),
        products=[camera],
    )

    assert response.total == 0


def test_no_match_returns_truthful_empty_result(client):
    response = client.post(
        "/api/v1/search",
        json={"max_budget": 100, "min_ram_gb": 64, "operating_system": "Haiku OS"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["total"] == 0


def test_malformed_search_request_returns_validation_error(client):
    response = client.post("/api/v1/search", json={"min_ram_gb": "sixteen"})

    assert response.status_code == 422


def test_search_rejects_unknown_filter_instead_of_ignoring_it(client):
    response = client.post("/api/v1/search", json={"max_budget": 900, "sort_by": "rating"})

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["max_budget", "min_ram_gb", "max_weight_kg"])
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_search_rejects_non_finite_numbers_with_clean_validation_error(client, field, literal):
    response = client.post(
        "/api/v1/search",
        content=f'{{"{field}": {literal}}}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", field]]


def test_validation_errors_do_not_echo_raw_input(client):
    oversized_query = "x" * 5000
    marker = "<script>unique-echo-marker</script>"
    responses = [
        client.post("/api/v1/intent", json={"query": oversized_query}),
        client.post("/api/v1/search", json={"operating_system": "   ", "min_ram_gb": marker}),
        client.post("/api/v1/search", json={"max_budget": 900, "sort_by": marker}),
    ]

    for response in responses:
        assert response.status_code == 422
        assert response.json()["detail"]
        assert all("input" not in error for error in response.json()["detail"])
        assert oversized_query not in response.text
        assert marker not in response.text


def test_finite_numeric_filters_still_match_after_validation_hardening(client):
    response = client.post(
        "/api/v1/search",
        json={"max_budget": 999.5, "min_ram_gb": 16, "max_weight_kg": 1.5},
    )

    assert response.status_code == 200
    assert product_ids(response) == {"demo-laptop-001", "demo-laptop-005", "demo-laptop-012", "demo-laptop-015"}
    assert response.json()["applied_filters"]["max_budget"] == 999.5
    assert response.json()["applied_filters"]["max_weight_kg"] == 1.5