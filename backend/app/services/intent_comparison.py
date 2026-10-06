import re
from typing import Any


def values_equivalent(
    field_path: str,
    left_value: Any,
    right_value: Any,
    left_intent: dict[str, Any],
    right_intent: dict[str, Any],
) -> bool:
    if field_path.endswith(".operating_system"):
        return _normalize_operating_system(left_value, left_intent, field_path) == _normalize_operating_system(
            right_value,
            right_intent,
            field_path,
        )
    if field_path.endswith(".use_case"):
        return _normalize_use_cases(left_value) == _normalize_use_cases(right_value)
    return left_value == right_value


def _normalize_operating_system(
    value: Any,
    intent: dict[str, Any],
    field_path: str,
) -> tuple[str, str | None] | None:
    section_name = field_path.split(".", maxsplit=1)[0]
    section = intent.get(section_name)
    if not isinstance(section, dict):
        section = {}

    family = section.get("operating_system_family")
    version = section.get("operating_system_version")
    if family is not None:
        normalized_version = str(version).strip().casefold() if version is not None else None
        return str(family).strip().casefold(), normalized_version

    if value is None:
        return None
    parts = str(value).strip().casefold().split()
    if not parts:
        return None
    if parts[0] == "windows":
        return "windows", " ".join(parts[1:]) or None
    return " ".join(parts), None


def _normalize_use_cases(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return (str(value).strip().casefold(),)
    normalized_value = value.strip().casefold()
    normalized_value = re.sub(r"\bcybersecurity\s+(?=school\b)", "cybersecurity, ", normalized_value)
    phrases = re.split(r"\s*(?:,|;|\band\b)\s*", normalized_value)
    normalized = tuple(sorted(" ".join(phrase.split()) for phrase in phrases if phrase.strip()))
    return normalized or None