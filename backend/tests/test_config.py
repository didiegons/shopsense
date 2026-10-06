import pytest
from fastapi.testclient import TestClient

from app.main import create_app

DEPLOYED_ORIGIN = "https://shopsense-web-123456789.us-central1.run.app"


def preflight(client: TestClient, origin: str):
    return client.options(
        "/api/v1/search",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    return monkeypatch


def test_default_cors_allows_only_local_frontend(clean_env):
    client = TestClient(create_app())

    assert preflight(client, "http://localhost:3000").headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in preflight(client, DEPLOYED_ORIGIN).headers


def test_cors_origins_come_from_environment(clean_env):
    clean_env.setenv("CORS_ALLOW_ORIGINS", f" {DEPLOYED_ORIGIN}/ , http://localhost:3000 ")
    client = TestClient(create_app())

    assert preflight(client, DEPLOYED_ORIGIN).headers.get("access-control-allow-origin") == DEPLOYED_ORIGIN
    assert preflight(client, "http://localhost:3000").headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in preflight(client, "https://evil.example").headers


def test_api_docs_available_outside_production(clean_env):
    client = TestClient(create_app())

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200


def test_api_docs_disabled_in_production(clean_env):
    clean_env.setenv("APP_ENV", "production")
    client = TestClient(create_app())

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.get("/health").status_code == 200
    assert client.post("/api/v1/search", json={"max_budget": 1000}).status_code == 200
