from fastapi import APIRouter

from app.models.intent import IntentRequest, ParsedShoppingIntent
from app.services.intent_service import resolve_intent

router = APIRouter(prefix="/api/v1")


@router.post("/intent", response_model=ParsedShoppingIntent)
def extract_intent(request: IntentRequest) -> ParsedShoppingIntent:
    return resolve_intent(request.query, request.category)