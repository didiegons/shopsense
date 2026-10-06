import os

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, intent, search

DEFAULT_CORS_ALLOW_ORIGINS = "http://localhost:3000"


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ALLOW_ORIGINS)
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Omit the echoed input: it can be oversized, and NaN/Infinity cannot be JSON-serialized.
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


def create_app() -> FastAPI:
    is_production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    application = FastAPI(
        title="ShopSense API",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.add_exception_handler(RequestValidationError, validation_error_handler)

    application.include_router(health.router)
    application.include_router(intent.router)
    application.include_router(search.router)
    return application


app = create_app()
