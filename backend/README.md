# ShopSense Backend

Local FastAPI service for the deterministic product-search milestone. The catalog in `app/data/catalog.json` contains demo data only; its prices and availability are not live retailer offers.

## Run locally

From the `backend/` directory:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Interactive API documentation is at `http://localhost:8000/docs`.

## Test

```powershell
python -m pytest
```

`GET /health` checks the service. `POST /api/v1/search` accepts optional `max_budget`, `min_ram_gb`, `operating_system`, and `max_weight_kg` filters. All supplied filters are hard constraints; no-match searches return an empty result list and the response echoes `applied_filters`.

`POST /api/v1/intent` uses deterministic parsing unless Vertex AI is configured. To enable the optional structured-JSON intent adapter, set `VERTEX_AI_PROJECT`, `VERTEX_AI_REGION`, and `SHOPSENSE_INTENT_MODEL`, and authenticate with Application Default Credentials (for local development, `gcloud auth application-default login`). AI output is validated against the Pydantic intent contract; unavailable, malformed, or invalid output falls back to deterministic parsing. AI parsing does not search products, and product search continues to use explicit request filters.

Category-specific intent and product maps currently accept arbitrary JSON keys and values; category registry validation for attribute names, types, and units is deferred.
