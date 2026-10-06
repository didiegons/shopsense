from enum import StrEnum

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


class PortabilityPreference(StrEnum):
    LIGHTWEIGHT = "lightweight"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


class OperatingSystemIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str = Field(min_length=1)
    version: str | None = None


class IntentConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_budget: float | None = Field(default=None, gt=0)
    min_ram_gb: int | None = Field(default=None, gt=0)
    max_weight_kg: float | None = Field(default=None, gt=0)
    operating_system: str | None = None
    operating_system_family: str | None = None
    operating_system_version: str | None = None

    @model_validator(mode="after")
    def validate_operating_system_metadata(self) -> "IntentConstraints":
        _validate_operating_system_metadata(
            self.operating_system,
            self.operating_system_family,
            self.operating_system_version,
        )
        return self


class IntentPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_system: str | None = None
    operating_system_family: str | None = None
    operating_system_version: str | None = None
    use_case: str | None = None
    portability_preference: PortabilityPreference | None = None
    storage_preference_gb: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_operating_system_metadata(self) -> "IntentPreferences":
        _validate_operating_system_metadata(
            self.operating_system,
            self.operating_system_family,
            self.operating_system_version,
        )
        return self


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class ParsedShoppingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: str
    category: str | None = None
    hard_constraints: IntentConstraints = Field(default_factory=IntentConstraints)
    preferences: IntentPreferences = Field(default_factory=IntentPreferences)
    category_hard_constraints: dict[str, JsonValue] = Field(default_factory=dict)
    category_preferences: dict[str, JsonValue] = Field(default_factory=dict)
    parser_source: Literal["deterministic", "vertex_ai"] = "deterministic"
    deterministic_agreement: bool | None = None
    differing_fields: list[str] = Field(default_factory=list)
    clarification_needed: bool
    clarification_question: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_clarification(self) -> "ParsedShoppingIntent":
        if self.clarification_needed and not self.clarification_question:
            raise ValueError("clarification_question is required when clarification is needed")
        if not self.clarification_needed and self.clarification_question is not None:
            raise ValueError("clarification_question must be empty when no clarification is needed")
        self._normalize_and_validate_constraints()
        return self

    def _normalize_and_validate_constraints(self) -> None:
        hard_values = self.hard_constraints.model_dump()
        preference_values = self.preferences.model_dump()
        operating_system_fields = {
            "operating_system",
            "operating_system_family",
            "operating_system_version",
        }

        for field in hard_values.keys() & preference_values.keys() - operating_system_fields:
            hard_value = hard_values[field]
            preference_value = preference_values[field]
            if hard_value is None or preference_value is None:
                continue
            if hard_value != preference_value:
                raise ValueError(f"preference '{field}' contradicts its hard constraint")
            setattr(self.preferences, field, None)

        self._validate_operating_system_overlap()
        self._normalize_category_maps()

    def _validate_operating_system_overlap(self) -> None:
        hard = self.hard_constraints
        preference = self.preferences
        if not (hard.operating_system or hard.operating_system_family) or not (
            preference.operating_system or preference.operating_system_family
        ):
            return

        hard_family, hard_version = _operating_system_parts(
            hard.operating_system,
            hard.operating_system_family,
            hard.operating_system_version,
        )
        preference_family, preference_version = _operating_system_parts(
            preference.operating_system,
            preference.operating_system_family,
            preference.operating_system_version,
        )
        if hard_family != preference_family:
            raise ValueError("operating system preference contradicts its hard constraint")
        if hard_version and preference_version and hard_version != preference_version:
            raise ValueError("operating system version preference contradicts its hard constraint")

        if hard_version == preference_version:
            preference.operating_system = None
            preference.operating_system_family = None
            preference.operating_system_version = None

    def _normalize_category_maps(self) -> None:
        shared_keys = self.category_hard_constraints.keys() & self.category_preferences.keys()
        for key in shared_keys:
            hard_value = self.category_hard_constraints[key]
            preference_value = self.category_preferences[key]
            if hard_value != preference_value:
                raise ValueError(f"category preference '{key}' contradicts its hard constraint")
            del self.category_preferences[key]


class CategoryAttributeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute: str
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None

    @field_validator("attribute")
    @classmethod
    def normalize_attribute_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("attribute must be non-empty")
        return normalized


class VertexIntentOutput(BaseModel):
    """Vertex-only wire shape; generic category maps are represented by explicit entries."""

    model_config = ConfigDict(extra="forbid")

    original_query: str
    category: str | None = None
    hard_constraints: IntentConstraints = Field(default_factory=IntentConstraints)
    preferences: IntentPreferences = Field(default_factory=IntentPreferences)
    category_hard_constraint_entries: list[CategoryAttributeEntry]
    category_preference_entries: list[CategoryAttributeEntry]
    clarification_needed: bool
    clarification_question: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_category_attributes(self) -> "VertexIntentOutput":
        _validate_unique_attribute_entries(
            self.category_hard_constraint_entries,
            "category_hard_constraint_entries",
        )
        _validate_unique_attribute_entries(
            self.category_preference_entries,
            "category_preference_entries",
        )
        return self


def _validate_unique_attribute_entries(
    entries: list[CategoryAttributeEntry],
    field_name: str,
) -> None:
    attributes = [entry.attribute.casefold() for entry in entries]
    if len(attributes) != len(set(attributes)):
        raise ValueError(f"{field_name} must not contain duplicate attribute names")


def _validate_operating_system_metadata(
    operating_system: str | None,
    family: str | None,
    version: str | None,
) -> None:
    if version is not None and family is None:
        raise ValueError("operating_system_version requires operating_system_family")
    if operating_system is None or family is None:
        return
    expected = " ".join(part for part in (family, version) if part).casefold().split()
    actual = operating_system.casefold().split()
    if actual != expected:
        raise ValueError("operating_system must match its family and version metadata")


def _operating_system_parts(
    operating_system: str | None,
    family: str | None,
    version: str | None,
) -> tuple[str, str | None]:
    if family is not None:
        return family.casefold(), version.casefold() if version is not None else None
    assert operating_system is not None
    normalized = operating_system.casefold().split()
    if normalized[0] == "windows" and len(normalized) > 1:
        return "windows", " ".join(normalized[1:])
    return " ".join(normalized), None