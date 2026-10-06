import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.intent import IntentRequest, ParsedShoppingIntent, VertexIntentOutput
from app.services.intent_comparison import values_equivalent
from app.services.intent_parser import parse_intent
from app.services.intent_service import resolve_intent
from app.services.vertex_intent import VertexIntentAdapter, VertexIntentError


def make_ai_intent(
    query: str,
    *,
    category: str | None = None,
    max_budget: float | None = None,
    confidence: float = 0.9,
    category_hard_constraints: dict | None = None,
    category_preferences: dict | None = None,
    preferences: dict | None = None,
    operating_system: dict | None = None,
) -> ParsedShoppingIntent:
    return ParsedShoppingIntent.model_validate(
        {
            "original_query": query,
            "category": category,
            "hard_constraints": {"max_budget": max_budget, **(operating_system or {})},
            "preferences": preferences or {},
            "category_hard_constraints": category_hard_constraints or {},
            "category_preferences": category_preferences or {},
            "clarification_needed": False,
            "confidence": confidence,
        }
    )


def make_vertex_output_json(intent: ParsedShoppingIntent) -> str:
    payload = {
        "original_query": intent.original_query,
        "category": intent.category,
        "hard_constraints": intent.hard_constraints.model_dump(mode="json"),
        "preferences": intent.preferences.model_dump(mode="json"),
        "category_hard_constraint_entries": [
            {"attribute": key, "value": value}
            for key, value in intent.category_hard_constraints.items()
        ],
        "category_preference_entries": [
            {"attribute": key, "value": value}
            for key, value in intent.category_preferences.items()
        ],
        "clarification_needed": intent.clarification_needed,
        "clarification_question": intent.clarification_question,
        "confidence": intent.confidence,
        "evidence": intent.evidence,
    }
    return json.dumps(payload)


def fake_vertex_adapter(response_text: str, captured: dict[str, object] | None = None):
    call_data = captured if captured is not None else {}

    class FakeModels:
        def generate_content(self, **kwargs):
            call_data.update(kwargs)
            return type("FakeResponse", (), {"text": response_text})()

    class FakeClient:
        models = FakeModels()

    class FakeGenAI:
        @staticmethod
        def Client(**kwargs):
            assert kwargs == {"vertexai": True, "project": "project", "location": "location"}
            return FakeClient()

    class FakeConfig:
        def __init__(self, response_mime_type, response_schema):
            self.response_mime_type = response_mime_type
            self.response_schema = response_schema

    fake_types = SimpleNamespace(GenerateContentConfig=FakeConfig)
    fake_errors = SimpleNamespace(APIError=type("APIError", (Exception,), {}))
    fake_auth_errors = SimpleNamespace(GoogleAuthError=type("GoogleAuthError", (Exception,), {}))
    adapter = VertexIntentAdapter("project", "location", "model")
    adapter._sdk = (FakeGenAI, fake_types, fake_errors, fake_auth_errors)
    return adapter, call_data


def test_valid_ai_intent_is_selected_and_compared():
    query = "laptop under $1000"

    intent = resolve_intent(query, ai_parser=lambda request: make_ai_intent(request.query, max_budget=1000))

    assert intent.parser_source == "vertex_ai"
    assert intent.deterministic_agreement is True
    assert intent.differing_fields == []
    assert intent.hard_constraints.max_budget == 1000


def test_ai_hard_constraint_disagreement_requires_clarification():
    query = "laptop under $1000"

    intent = resolve_intent(query, ai_parser=lambda request: make_ai_intent(request.query, max_budget=900))

    assert intent.parser_source == "vertex_ai"
    assert intent.deterministic_agreement is False
    assert "hard_constraints.max_budget" in intent.differing_fields
    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_low_confidence_ai_output_requires_clarification():
    intent = resolve_intent(
        "laptop under $1000",
        ai_parser=lambda request: make_ai_intent(request.query, max_budget=1000, confidence=0.4),
    )

    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_ai_exception_falls_back_to_deterministic_parser():
    query = "laptop under $1000"

    def fail(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        raise VertexIntentError("model unavailable")

    intent = resolve_intent(query, ai_parser=fail)

    assert intent == parse_intent(query)
    assert intent.parser_source == "deterministic"


def test_invalid_ai_contract_falls_back_to_deterministic_parser():
    query = "laptop under $1000"

    def invalid(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        return ParsedShoppingIntent.model_validate({"original_query": query})

    intent = resolve_intent(query, ai_parser=invalid)

    assert intent == parse_intent(query)


def test_category_specific_ai_constraints_are_compared():
    query = "camera with a full-frame sensor"
    ai = make_ai_intent(
        query,
        category="camera",
        category_hard_constraints={"sensor_format": "full-frame"},
    )
    def parse_camera(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.category == "camera"
        return ai

    intent = resolve_intent(query, "camera", ai_parser=parse_camera)

    assert intent.category == "camera"
    assert intent.category_hard_constraints == {"sensor_format": "full-frame"}
    assert intent.deterministic_agreement is False
    assert "category_hard_constraints.sensor_format" in intent.differing_fields
    assert intent.clarification_needed is False


def test_vertex_adapter_requests_schema_constrained_json():
    captured: dict[str, object] = {}
    body = make_vertex_output_json(make_ai_intent(
        "camera with full-frame sensor",
        category="camera",
        category_hard_constraints={"sensor_format": "full-frame"},
        category_preferences={"body_style": "mirrorless"},
    ))
    adapter, _ = fake_vertex_adapter(body, captured)

    result = adapter.parse(IntentRequest(query="camera with full-frame sensor", category="camera"))

    assert captured["model"] == "model"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].response_schema["title"] == "VertexIntentOutput"
    assert "$defs" not in captured["config"].response_schema
    properties = captured["config"].response_schema["properties"]
    assert "category_hard_constraints" not in properties
    assert "category_preferences" not in properties
    assert "category_hard_constraint_entries" in captured["config"].response_schema["required"]
    assert "category_preference_entries" in captured["config"].response_schema["required"]
    assert properties["category_hard_constraint_entries"]["type"] == "array"
    assert properties["category_preference_entries"]["type"] == "array"
    hard_entry = properties["category_hard_constraint_entries"]["items"]
    assert set(hard_entry["properties"]) == {"attribute", "value"}
    assert hard_entry["required"] == ["attribute", "value"]
    assert "Category: camera" in captured["contents"]
    assert "category_hard_constraints.sensor_format='full-frame'" in captured["contents"]
    assert "category_preferences.body_style='mirrorless'" in captured["contents"]
    assert "Do not leave these maps empty" in captured["contents"]
    assert "not a closed list of categories or keys" in captured["contents"]
    assert result.category == "camera"
    assert result.category_hard_constraints == {"sensor_format": "full-frame"}
    assert result.category_preferences == {"body_style": "mirrorless"}


def test_invalid_vertex_json_falls_back_to_deterministic():
    captured: dict[str, object] = {}
    adapter, _ = fake_vertex_adapter("not valid JSON", captured)
    query = "laptop under $1000"

    intent = resolve_intent(query, ai_parser=adapter.parse)

    assert captured["model"] == "model"
    assert intent == parse_intent(query)


def test_valid_json_with_invalid_pydantic_schema_falls_back():
    intent = make_ai_intent("laptop under $1000", max_budget=1000)
    body = json.loads(make_vertex_output_json(intent))
    body["confidence"] = 1.5
    adapter, _ = fake_vertex_adapter(json.dumps(body))

    intent = resolve_intent("laptop under $1000", ai_parser=adapter.parse)

    assert intent == parse_intent("laptop under $1000")


@pytest.mark.parametrize("value", [["full-frame"], {"format": "full-frame"}])
def test_vertex_category_entry_rejects_non_scalar_values(value):
    body = json.loads(
        make_vertex_output_json(
            make_ai_intent(
                "camera with full-frame sensor",
                category="camera",
                category_hard_constraints={"sensor_format": "full-frame"},
            )
        )
    )
    body["category_hard_constraint_entries"][0]["value"] = value

    with pytest.raises(ValidationError):
        VertexIntentOutput.model_validate(body)


def test_vertex_category_entry_rejects_duplicate_attributes():
    body = json.loads(
        make_vertex_output_json(
            make_ai_intent(
                "camera with full-frame sensor",
                category="camera",
                category_hard_constraints={"sensor_format": "full-frame"},
            )
        )
    )
    body["category_hard_constraint_entries"].append(
        {"attribute": "Sensor_Format", "value": "aps-c"}
    )

    with pytest.raises(ValidationError, match="duplicate attribute names"):
        VertexIntentOutput.model_validate(body)


def test_conflicting_vertex_hard_and_preference_entries_fall_back():
    body = json.loads(
        make_vertex_output_json(
            make_ai_intent(
                "camera must have full-frame sensor, prefer aps-c",
                category="camera",
                category_hard_constraints={"sensor_format": "full-frame"},
            )
        )
    )
    body["category_preference_entries"] = [
        {"attribute": "sensor_format", "value": "aps-c"}
    ]
    adapter, _ = fake_vertex_adapter(json.dumps(body))
    query = "camera under $1000"

    intent = resolve_intent(query, "camera", ai_parser=adapter.parse)

    assert intent.parser_source == "deterministic"
    assert intent == parse_intent(query, "camera")


@pytest.mark.parametrize(
    ("query", "category", "expected"),
    [
        ("Laptop under $1000 with at least 16 GB RAM", "laptop", {"max_budget": 1000, "min_ram_gb": 16}),
        ("Camera with a full-frame sensor under $1500", "camera", {"max_budget": 1500}),
    ],
)
def test_deterministic_baseline_queries(query, category, expected):
    intent = parse_intent(query, category)

    assert intent.category == category
    for field, value in expected.items():
        assert getattr(intent.hard_constraints, field) == value


@pytest.mark.parametrize(
    ("query", "ai_budget", "expected_agreement", "expected_clarification"),
    [
        ("Laptop under $1000", 1000, True, False),
        ("Laptop under $1000", 1200, False, True),
        ("Camera under $1500", 1500, False, True),
    ],
)
def test_deterministic_and_ai_comparison_matrix(
    query,
    ai_budget,
    expected_agreement,
    expected_clarification,
):
    intent = resolve_intent(
        query,
        ai_parser=lambda request: make_ai_intent(
            request.query,
            max_budget=ai_budget,
            category=request.category or ("camera" if "Camera" in query else None),
        ),
    )

    assert intent.deterministic_agreement is expected_agreement
    assert intent.clarification_needed is expected_clarification


def test_os_legacy_string_compares_equal_to_matching_family_version():
    query = "Windows only laptop under $900"
    intent = resolve_intent(
        query,
        ai_parser=lambda request: make_ai_intent(
            request.query,
            max_budget=900,
            operating_system={
                "operating_system": None,
                "operating_system_family": "Windows",
                "operating_system_version": None,
            },
        ),
    )

    assert intent.hard_constraints.operating_system is None
    assert intent.hard_constraints.operating_system_family == "Windows"
    assert intent.deterministic_agreement is True
    assert intent.differing_fields == []
    assert intent.clarification_needed is False


def test_ambiguous_multiple_os_options_are_not_returned_as_actionable_constraints():
    query = "Windows or Ubuntu laptop under $1000"
    ai_intent = make_ai_intent(
        query,
        max_budget=1000,
        confidence=0.9,
        operating_system={
            "operating_system": "Windows or Ubuntu",
        },
    )
    ai_intent.clarification_needed = True
    ai_intent.clarification_question = "Which operating system do you require?"

    def parse_ambiguous_os(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        assert request.category == "laptop"
        return ai_intent

    intent = resolve_intent(query, "laptop", ai_parser=parse_ambiguous_os)

    assert intent.clarification_needed is True
    assert intent.clarification_question == "Which operating system do you require?"
    assert intent.hard_constraints.max_budget == 1000
    assert intent.hard_constraints.operating_system is None
    assert intent.hard_constraints.operating_system_family is None
    assert intent.hard_constraints.operating_system_version is None
    assert intent.preferences.operating_system is None
    assert intent.deterministic_agreement is True


@pytest.mark.parametrize(
    ("query", "os_string", "version"),
    [
        ("Windows laptop under $1000", "Windows", None),
        ("Windows 11 laptop under $1000", "Windows 11", "11"),
    ],
)
def test_single_os_constraint_is_preserved(query, os_string, version):
    ai_intent = make_ai_intent(
        query,
        max_budget=1000,
        operating_system={
            "operating_system": os_string,
            "operating_system_family": "Windows",
            "operating_system_version": version,
        },
    )

    def parse_single_os(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        assert request.category == "laptop"
        return ai_intent

    intent = resolve_intent(query, "laptop", ai_parser=parse_single_os)

    assert intent.hard_constraints.operating_system == os_string
    assert intent.hard_constraints.operating_system_family == "Windows"
    assert intent.hard_constraints.operating_system_version == version


def test_use_case_comparison_ignores_case_separators_and_order_only():
    query = "Laptop under $1200 for cybersecurity school and virtual machines"
    intent = resolve_intent(
        query,
        ai_parser=lambda request: make_ai_intent(
            request.query,
            max_budget=1200,
            preferences={"use_case": " Virtual Machines ; CYBERSECURITY and School "},
        ),
    )

    assert intent.deterministic_agreement is True
    assert intent.differing_fields == []
    assert intent.clarification_needed is False


def test_use_case_comparison_splits_observed_adjacent_recognized_labels():
    expected = {"preferences": {"use_case": "cybersecurity, school, virtual machines"}}
    actual = {"preferences": {"use_case": "cybersecurity school and virtual machines"}}

    assert values_equivalent(
        "preferences.use_case",
        expected["preferences"]["use_case"],
        actual["preferences"]["use_case"],
        expected,
        actual,
    ) is True


@pytest.mark.parametrize(
    ("query", "category", "ai_result"),
    [
        (
            "I want a lightweight laptop for school",
            "laptop",
            {"preferences": {"use_case": "school", "portability_preference": "lightweight"}},
        ),
        (
            "Windows or Ubuntu laptop under $1000",
            "laptop",
            {"hard_constraints": {"max_budget": 1000}},
        ),
    ],
)
def test_actionable_deterministic_clarification_is_preserved(query, category, ai_result):
    base = make_ai_intent(query, category=category, max_budget=ai_result.get("hard_constraints", {}).get("max_budget"))
    if "preferences" in ai_result:
        base.preferences = type(base.preferences).model_validate(ai_result["preferences"])

    def parse_with_intent(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        assert request.category == category
        return base

    intent = resolve_intent(query, category, ai_parser=parse_with_intent)

    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_generic_deterministic_laptop_question_does_not_override_category_intent():
    query = "Camera with a full-frame sensor, preferably mirrorless"
    camera_intent = make_ai_intent(query, category="camera")

    def parse_camera(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        assert request.category == "camera"
        return camera_intent

    intent = resolve_intent(query, "camera", ai_parser=parse_camera)

    assert intent.clarification_needed is False


def test_shared_normalizer_does_not_match_use_case_synonyms():
    expected = {"preferences": {"use_case": "virtual machines"}}
    actual = {"preferences": {"use_case": "virtualization"}}

    assert values_equivalent(
        "preferences.use_case",
        expected["preferences"]["use_case"],
        actual["preferences"]["use_case"],
        expected,
        actual,
    ) is False


def test_identical_hard_constraint_preference_is_normalized():
    intent = make_ai_intent(
        "Windows laptop",
        operating_system={
            "operating_system": "Windows",
            "operating_system_family": "Windows",
        },
        preferences={
            "operating_system": "Windows",
            "operating_system_family": "Windows",
        },
    )

    assert intent.preferences.operating_system is None
    assert intent.preferences.operating_system_family is None


def test_contradictory_hard_constraint_preference_is_rejected():
    with pytest.raises(ValidationError, match="contradicts its hard constraint"):
        make_ai_intent(
            "Windows only laptop",
            operating_system={
                "operating_system": "Windows",
                "operating_system_family": "Windows",
            },
            preferences={
                "operating_system": "Ubuntu Linux",
                "operating_system_family": "Ubuntu Linux",
            },
        )


def test_identical_category_constraint_preference_is_normalized():
    intent = make_ai_intent(
        "camera with full-frame sensor",
        category_hard_constraints={"sensor_format": "full-frame"},
        category_preferences={"sensor_format": "full-frame"},
    )

    assert intent.category_preferences == {}


def test_contradictory_category_constraint_preference_is_rejected():
    with pytest.raises(ValidationError, match="category preference 'sensor_format'"):
        make_ai_intent(
            "camera with full-frame sensor",
            category_hard_constraints={"sensor_format": "full-frame"},
            category_preferences={"sensor_format": "aps-c"},
        )


@pytest.mark.parametrize(
    "os_fields",
    [
        {
            "operating_system": "Windows 11",
            "operating_system_family": "Windows",
            "operating_system_version": "10",
        },
        {
            "operating_system": "Windows",
            "operating_system_family": "Windows",
            "operating_system_version": "11",
        },
        {"operating_system_version": "11"},
    ],
)
def test_inconsistent_os_string_family_version_is_rejected(os_fields):
    with pytest.raises(ValidationError):
        make_ai_intent("Windows laptop", operating_system=os_fields)


def test_expected_vertex_failure_falls_back():
    query = "laptop under $1000"

    def fail(request: IntentRequest) -> ParsedShoppingIntent:
        assert request.query == query
        raise VertexIntentError("Vertex request failed")

    assert resolve_intent(query, ai_parser=fail) == parse_intent(query)


def test_unexpected_comparison_error_surfaces(monkeypatch):
    import app.services.intent_service as intent_service

    def fail_comparison(*args):
        assert len(args) == 2
        raise RuntimeError("comparison bug")

    monkeypatch.setattr(intent_service, "_differing_fields", fail_comparison)
    with pytest.raises(RuntimeError, match="comparison bug"):
        resolve_intent(
            "laptop under $1000",
            ai_parser=lambda request: make_ai_intent(request.query, max_budget=1000),
        )


def test_missing_genai_sdk_allows_app_startup_and_deterministic_fallback():
    backend_directory = Path(__file__).resolve().parents[1]
    script = """
import importlib
import os

original_import_module = importlib.import_module
def without_genai(name, package=None):
    if name == "google.genai" or name.startswith("google.genai."):
        raise ModuleNotFoundError("SDK unavailable", name="google.genai")
    return original_import_module(name, package)

importlib.import_module = without_genai
os.environ["VERTEX_AI_PROJECT"] = "test-project"
os.environ["VERTEX_AI_REGION"] = "test-region"
os.environ["SHOPSENSE_INTENT_MODEL"] = "test-model"
from app.main import app
from app.services.intent_service import resolve_intent

assert app is not None
result = resolve_intent("laptop under $1000")
assert result.parser_source == "deterministic"
assert result.hard_constraints.max_budget == 1000
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_directory,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr