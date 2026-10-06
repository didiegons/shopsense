from collections.abc import Callable

from pydantic import ValidationError

from app.models.intent import IntentRequest, ParsedShoppingIntent
from app.services.intent_comparison import values_equivalent
from app.services.intent_parser import OS_PATTERNS, parse_intent
from app.services.vertex_intent import VertexIntentAdapter, VertexIntentError

LOW_CONFIDENCE_THRESHOLD = 0.65


def resolve_intent(
    query: str,
    category: str | None = None,
    ai_parser: Callable[[IntentRequest], ParsedShoppingIntent] | None = None,
) -> ParsedShoppingIntent:
    request = IntentRequest(query=query, category=category)
    deterministic = parse_intent(request.query, request.category)
    parser = ai_parser or _configured_ai_parser()
    if parser is None:
        return deterministic
    try:
        ai_intent = parser(request)
    except (VertexIntentError, ValidationError):
        return deterministic
    ai_intent.category = request.category or ai_intent.category or deterministic.category
    if ai_intent.clarification_needed and _query_has_multiple_os_options(request.query):
        _clear_unresolved_os_intent(ai_intent)
    return _compare_and_apply_clarification(ai_intent, deterministic)


def _configured_ai_parser() -> Callable[[IntentRequest], ParsedShoppingIntent] | None:
    adapter = VertexIntentAdapter.from_environment()
    return adapter.parse if adapter else None


def _query_has_multiple_os_options(query: str) -> bool:
    options: set[tuple[str, str | None]] = set()
    for family, pattern in OS_PATTERNS:
        for match in pattern.finditer(query):
            version = match.group(1) if family == "Windows" else None
            options.add((family.casefold(), version.casefold() if version else None))
    return len(options) > 1


def _clear_unresolved_os_intent(intent: ParsedShoppingIntent) -> None:
    for section in (intent.hard_constraints, intent.preferences):
        section.operating_system = None
        section.operating_system_family = None
        section.operating_system_version = None


def _compare_and_apply_clarification(
    ai_intent: ParsedShoppingIntent,
    deterministic: ParsedShoppingIntent,
) -> ParsedShoppingIntent:
    differing_fields = _differing_fields(ai_intent, deterministic)
    hard_fields_differ = any(
        field == "category"
        or field.startswith("hard_constraints.")
        or _category_hard_constraint_conflicts(field, ai_intent, deterministic)
        for field in differing_fields
    )
    ai_intent.parser_source = "vertex_ai"
    ai_intent.deterministic_agreement = not differing_fields
    ai_intent.differing_fields = differing_fields
    preserve_deterministic_clarification = _deterministic_clarification_is_actionable(
        ai_intent,
        deterministic,
    )
    if (
        ai_intent.confidence < LOW_CONFIDENCE_THRESHOLD
        or hard_fields_differ
        or preserve_deterministic_clarification
    ):
        ai_intent.clarification_needed = True
        if not ai_intent.clarification_question:
            ai_intent.clarification_question = (
                deterministic.clarification_question
                if preserve_deterministic_clarification
                else "Please confirm the requirements before searching; the interpretation is uncertain."
            )
    return ai_intent


def _category_hard_constraint_conflicts(
    field: str,
    ai_intent: ParsedShoppingIntent,
    deterministic: ParsedShoppingIntent,
) -> bool:
    prefix = "category_hard_constraints."
    if not field.startswith(prefix):
        return False
    key = field.removeprefix(prefix)
    if key not in ai_intent.category_hard_constraints or key not in deterministic.category_hard_constraints:
        return False
    return not values_equivalent(
        field,
        ai_intent.category_hard_constraints[key],
        deterministic.category_hard_constraints[key],
        {"category_hard_constraints": ai_intent.category_hard_constraints},
        {"category_hard_constraints": deterministic.category_hard_constraints},
    )


def _deterministic_clarification_is_actionable(
    ai_intent: ParsedShoppingIntent,
    deterministic: ParsedShoppingIntent,
) -> bool:
    if ai_intent.category and ai_intent.category.casefold() != "laptop":
        return False
    if not deterministic.clarification_needed:
        return False

    question = deterministic.clarification_question or ""
    if question.startswith("I found more than one possible value"):
        return True

    has_laptop_hard_constraint = any(
        value is not None
        for value in (
            deterministic.hard_constraints.max_budget,
            deterministic.hard_constraints.min_ram_gb,
            deterministic.hard_constraints.max_weight_kg,
            deterministic.hard_constraints.operating_system,
        )
    )
    return not has_laptop_hard_constraint and not ai_intent.category_hard_constraints


def _differing_fields(
    ai_intent: ParsedShoppingIntent,
    deterministic: ParsedShoppingIntent,
) -> list[str]:
    excluded_fields = {
        "original_query",
        "parser_source",
        "deterministic_agreement",
        "differing_fields",
        "clarification_needed",
        "clarification_question",
        "confidence",
        "evidence",
    }
    ai_payload = ai_intent.model_dump(exclude=excluded_fields)
    deterministic_payload = deterministic.model_dump(exclude=excluded_fields)
    differing: list[str] = []
    if ai_intent.category != deterministic.category:
        differing.append("category")
    for section in ("hard_constraints", "preferences", "category_hard_constraints", "category_preferences"):
        left = ai_payload.get(section) or {}
        right = deterministic_payload.get(section) or {}
        keys = set(left) | set(right) if isinstance(left, dict) and isinstance(right, dict) else set()
        differing.extend(
            f"{section}.{key}"
            for key in sorted(keys)
            if not values_equivalent(
                f"{section}.{key}",
                left.get(key),
                right.get(key),
                ai_payload,
                deterministic_payload,
            )
        )
    return differing