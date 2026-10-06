from fastapi import APIRouter

from app.models.search import SearchRequest, SearchResponse
from app.services.search import search_catalog

router = APIRouter(prefix="/api/v1")


@router.post("/search", response_model=SearchResponse)
def search_products(request: SearchRequest) -> SearchResponse:
    return search_catalog(request)