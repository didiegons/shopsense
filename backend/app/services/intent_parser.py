import re

from app.models.intent import (
    IntentConstraints,
    IntentPreferences,
    OperatingSystemIntent,
    ParsedShoppingIntent,
    PortabilityPreference,
)

BUDGET_PATTERN = re.compile(
    r"\b(?:under|below|less than|no more than|up to|maximum(?: budget)?(?: of)?)\s*"
    r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
RAM_PATTERN = re.compile(
    r"\b(?:at least|minimum(?: of)?|no less than|with)\s*(\d{1,3})\s*"
    r"(?:gb|gigabytes?)\s*(?:of\s*)?(?:ram|memory)\b"
    r"|\b(\d{1,3})\s*(?:gb|gigabytes?)\s*(?:of\s*)?(?:ram|memory)\b",
    re.IGNORECASE,
)
WEIGHT_PATTERN = re.compile(
    r"\b(?:under|below|less than|no more than|up to|maximum(?: weight)?(?: of)?)\s*"
    r"(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams?)\b",
    re.IGNORECASE,
)
OS_PATTERNS = (
    ("Windows", re.compile(r"\bwindows(?:\s*(\d+(?:\.\d+)?))?\b", re.IGNORECASE)),
    ("Ubuntu Linux", re.compile(r"\b(?:ubuntu|linux)\b", re.IGNORECASE)),
    ("ChromeOS", re.compile(r"\bchrome\s*os\b", re.IGNORECASE)),
)
MANDATORY_OS_PATTERN = re.compile(
    r"\b(?:must\s+(?:use|have|run)|only|require[sd]?)\s+(?:use\s+)?"
    r"(?:an?\s+)?(?:windows(?:\s*\d+(?:\.\d+)?)?|ubuntu|linux|chrome\s*os)\b"
    r"|\b(?:windows(?:\s*\d+(?:\.\d+)?)?|ubuntu|linux|chrome\s*os)\s+only\b",
    re.IGNORECASE,
)
PREFERRED_OS_PATTERN = re.compile(
    r"\b(?:prefer|preferred|ideally|would like|want)\s+(?:to\s+use\s+)?"
    r"(?:an?\s+)?(?:windows(?:\s*\d+(?:\.\d+)?)?|ubuntu|linux|chrome\s*os)\b",
    re.IGNORECASE,
)


def parse_intent(query: str, category: str | None = None) -> ParsedShoppingIntent:
    normalized_query = query.strip()
    normalized_category = category.strip() if category else None
    if normalized_category is None and re.search(r"\blaptops?\b", normalized_query, re.IGNORECASE):
        normalized_category = "laptop"
    hard_values: dict[str, object | None] = {
        "max_budget": None,
        "min_ram_gb": None,
        "max_weight_kg": None,
        "operating_system": None,
        "operating_system_family": None,
        "operating_system_version": None,
    }
    preference_values: dict[str, object | None] = {
        "operating_system": None,
        "operating_system_family": None,
        "operating_system_version": None,
        "use_case": _extract_use_case(normalized_query),
        "portability_preference": _extract_portability(normalized_query),
        "storage_preference_gb": _extract_storage(normalized_query),
    }
    evidence: list[str] = []
    ambiguities: list[str] = []
    evidence.extend(_extract_preference_evidence(normalized_query))

    _extract_numeric_constraint(
        BUDGET_PATTERN,
        normalized_query,
        "max_budget",
        hard_values,
        evidence,
        ambiguities,
        lambda match: float(match.group(1).replace(",", "")),
    )
    _extract_numeric_constraint(
        RAM_PATTERN,
        normalized_query,
        "min_ram_gb",
        hard_values,
        evidence,
        ambiguities,
        lambda match: int(match.group(1) or match.group(2)),
    )
    _extract_numeric_constraint(
        WEIGHT_PATTERN,
        normalized_query,
        "max_weight_kg",
        hard_values,
        evidence,
        ambiguities,
        lambda match: _weight_in_kg(match.group(1), match.group(2)),
    )

    operating_system, os_evidence, os_ambiguous = _extract_operating_system(normalized_query)
    if os_ambiguous:
        ambiguities.append("operating_system")
    elif operating_system:
        evidence.append(os_evidence)
        os_label = " ".join(
            part for part in (operating_system.family, operating_system.version) if part
        )
        if MANDATORY_OS_PATTERN.search(normalized_query):
            hard_values["operating_system"] = os_label
            hard_values["operating_system_family"] = operating_system.family
            hard_values["operating_system_version"] = operating_system.version
        else:
            preference_values["operating_system"] = os_label
            preference_values["operating_system_family"] = operating_system.family
            preference_values["operating_system_version"] = operating_system.version
            if PREFERRED_OS_PATTERN.search(normalized_query):
                evidence.append("OS preference stated explicitly")
            else:
                evidence.append("OS mentioned without mandatory language; treated as a preference")

    hard_constraints = IntentConstraints.model_validate(hard_values)
    preferences = IntentPreferences.model_validate(preference_values)
    has_hard_constraint = any(value is not None for value in hard_values.values())
    clarification_needed = bool(ambiguities) or not has_hard_constraint

    if ambiguities:
        clarification_question = "I found more than one possible value. Which requirement should I use?"
        confidence = 0.35
    elif not has_hard_constraint:
        clarification_question = _clarification_for(preferences)
        confidence = 0.45 if evidence else 0.2
    else:
        clarification_question = None
        confidence = 0.92

    return ParsedShoppingIntent(
        original_query=normalized_query,
        category=normalized_category,
        hard_constraints=hard_constraints,
        preferences=preferences,
        clarification_needed=clarification_needed,
        clarification_question=clarification_question,
        confidence=confidence,
        evidence=evidence,
    )


def _extract_numeric_constraint(
    pattern: re.Pattern[str],
    query: str,
    field: str,
    values: dict[str, object | None],
    evidence: list[str],
    ambiguities: list[str],
    convert,
) -> None:
    matches = list(pattern.finditer(query))
    if not matches:
        return
    parsed_values = [convert(match) for match in matches]
    if len(set(parsed_values)) > 1:
        ambiguities.append(field)
        evidence.extend(match.group(0) for match in matches)
        return
    values[field] = parsed_values[0]
    evidence.append(matches[0].group(0))


def _weight_in_kg(value: str, unit: str) -> float:
    weight = float(value)
    return weight / 1000 if unit.casefold().startswith("g") else weight


def _extract_operating_system(
    query: str,
) -> tuple[OperatingSystemIntent | None, str, bool]:
    matches = [
        (canonical, pattern.search(query))
        for canonical, pattern in OS_PATTERNS
        if pattern.search(query)
    ]
    if len(matches) > 1:
        return None, "", True
    if not matches:
        return None, "", False
    family, match = matches[0]
    assert match is not None
    version = match.group(1) if family == "Windows" else None
    return OperatingSystemIntent(family=family, version=version), match.group(0), False


def _extract_use_case(query: str) -> str | None:
    use_cases = (
        ("cybersecurity", re.compile(r"\bcybersecurity\b", re.IGNORECASE)),
        ("school", re.compile(r"\b(?:school|student|college|university|campus)\b", re.IGNORECASE)),
        ("virtual machines", re.compile(r"\b(?:virtual machines?|vms?)\b", re.IGNORECASE)),
        ("gaming", re.compile(r"\bgaming\b", re.IGNORECASE)),
        ("programming", re.compile(r"\b(?:programming|coding|software development)\b", re.IGNORECASE)),
    )
    found = [label for label, pattern in use_cases if pattern.search(query)]
    return ", ".join(found) if found else None


def _extract_preference_evidence(query: str) -> list[str]:
    patterns = (
        r"\bcybersecurity\b",
        r"\b(?:school|student|college|university|campus)\b",
        r"\b(?:virtual machines?|vms?)\b",
        r"\bgaming\b",
        r"\b(?:programming|coding|software development)\b",
        r"\b(?:lightweight|very light|ultralight|easy to carry|portable)\b",
        r"\b(?:powerful|high performance|workstation)\b",
        r"\b(?:prefer(?:ably)?\s+)?\d{1,5}\s*(?:gb|tb|terabytes?)\s*(?:of\s*)?storage\b",
    )
    snippets = []
    for expression in patterns:
        match = re.search(expression, query, re.IGNORECASE)
        if match:
            snippets.append(match.group(0))
    return snippets


def _extract_portability(query: str) -> PortabilityPreference | None:
    if re.search(r"\b(?:lightweight|very light|ultralight|easy to carry|portable)\b", query, re.IGNORECASE):
        return PortabilityPreference.LIGHTWEIGHT
    if re.search(r"\b(?:powerful|high performance|workstation)\b", query, re.IGNORECASE):
        return PortabilityPreference.PERFORMANCE
    return None


def _extract_storage(query: str) -> int | None:
    match = re.search(
        r"\b(?:prefer(?:ably)?\s+)?(\d{1,5})\s*(gb|tb|terabytes?)\s*(?:of\s*)?storage\b",
        query,
        re.IGNORECASE,
    )
    if not match:
        return None
    amount = int(match.group(1))
    return amount * 1024 if match.group(2).casefold().startswith("t") else amount


def _clarification_for(preferences: IntentPreferences) -> str:
    if preferences.portability_preference == PortabilityPreference.LIGHTWEIGHT:
        return "What is your maximum budget or preferred weight limit?"
    if preferences.operating_system:
        return "Is that operating system a requirement, and what is your maximum budget?"
    return "What is your maximum budget, minimum RAM, or maximum weight requirement?"