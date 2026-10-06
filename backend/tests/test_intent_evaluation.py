import pytest

from app.models.intent import ParsedShoppingIntent
from scripts.evaluate_intents import evaluate_cases, load_cases


def test_fixed_dataset_has_laptop_and_non_laptop_coverage():
    cases = load_cases()

    assert len(cases) == 11
    assert {case["category"] for case in cases} == {"laptop", "camera"}
    assert any(case["expected"]["clarification_needed"] for case in cases)
    assert any(
        case["expected"].get("category_hard_constraints")
        or case["expected"].get("category_preferences")
        for case in cases
    )


def test_deterministic_evaluation_reports_field_and_clarification_metrics(monkeypatch):
    from app.services.vertex_intent import VertexIntentAdapter

    def vertex_must_not_be_checked():
        raise AssertionError("Default evaluation must not inspect or call Vertex")

    monkeypatch.setattr(VertexIntentAdapter, "from_environment", vertex_must_not_be_checked)
    cases = [
        {
            "id": "budget",
            "query": "Laptop under $1000",
            "category": "laptop",
            "expected": {
                "category": "laptop",
                "hard_constraints": {"max_budget": 1000},
                "clarification_needed": False,
            },
        },
        {
            "id": "vague",
            "query": "Lightweight laptop for school",
            "category": "laptop",
            "expected": {
                "preferences": {"portability_preference": "lightweight"},
                "clarification_needed": True,
            },
        },
    ]

    report = evaluate_cases(cases)

    assert report["mode"] == "deterministic"
    assert report["field_extraction"]["passed"] == 3
    assert report["field_extraction"]["failed"] == 0
    assert report["clarification"]["tp"] == 1
    assert report["clarification"]["tn"] == 1
    assert report["clarification"]["accuracy"] == 1
    assert report["category_counts"] == {"laptop": 2}
    assert report["by_category"]["laptop"]["fields"]["hard_constraints.max_budget"]["accuracy"] == 1
    budget_diagnostic = report["cases"][0]["field_results"]["hard_constraints.max_budget"]
    assert budget_diagnostic["expected"] == 1000
    assert budget_diagnostic["actual"] == 1000
    assert budget_diagnostic["passed"] is True
    assert budget_diagnostic["parser_source"] == "deterministic"
    assert budget_diagnostic["confidence"] == 0.92
    assert budget_diagnostic["deterministic_agreement"] is None
    assert budget_diagnostic["differing_fields"] == []
    assert budget_diagnostic["clarification_expected"] is False
    assert budget_diagnostic["clarification_actual"] is False
    clarification_diagnostic = report["cases"][1]["field_results"]["clarification_needed"]
    assert clarification_diagnostic["expected"] is True
    assert clarification_diagnostic["actual"] is True


def test_category_report_has_per_field_accuracy():
    cases = [
        {
            "id": "camera",
            "query": "Camera",
            "category": "camera",
            "expected": {
                "category_hard_constraints": {},
                "category_preferences": {},
                "clarification_needed": True,
            },
        }
    ]

    report = evaluate_cases(cases)

    assert report["category_counts"] == {"camera": 1}
    assert report["by_category"]["camera"]["fields"]["category_hard_constraints"]["accuracy"] == 1
    assert report["by_category"]["camera"]["fields"]["category_preferences"]["accuracy"] == 1


def test_evaluator_uses_shared_os_and_use_case_normalization(monkeypatch):
    import scripts.evaluate_intents as evaluator

    actual_intent = ParsedShoppingIntent.model_validate(
        {
            "original_query": "Windows laptop for cybersecurity school and virtual machines",
            "category": "laptop",
            "hard_constraints": {
                "operating_system": None,
                "operating_system_family": "Windows",
                "operating_system_version": None,
            },
            "preferences": {"use_case": "Virtual Machines ; CYBERSECURITY and School"},
            "clarification_needed": False,
            "confidence": 0.9,
        }
    )
    def return_formatted_intent(query: str, category: str | None) -> ParsedShoppingIntent:
        assert query == "Windows laptop for cybersecurity school and virtual machines"
        assert category == "laptop"
        return actual_intent

    monkeypatch.setattr(evaluator, "parse_intent", return_formatted_intent)
    cases = [
        {
            "id": "normalization",
            "query": "Windows laptop for cybersecurity school and virtual machines",
            "category": "laptop",
            "expected": {
                "hard_constraints": {
                    "operating_system": "Windows",
                    "operating_system_family": "Windows",
                    "operating_system_version": None,
                },
                "preferences": {"use_case": "cybersecurity, school, virtual machines"},
                "clarification_needed": False,
            },
        }
    ]

    report = evaluate_cases(cases)

    assert report["field_extraction"]["passed"] == 4
    assert report["field_extraction"]["failed"] == 0
    assert report["cases"][0]["field_results"]["hard_constraints.operating_system"]["passed"] is True
    assert report["cases"][0]["field_results"]["preferences.use_case"]["passed"] is True


def test_vertex_mode_requires_explicit_configuration(monkeypatch):
    from app.services.vertex_intent import VertexIntentAdapter

    monkeypatch.setattr(VertexIntentAdapter, "from_environment", lambda: None)

    with pytest.raises(RuntimeError, match="Vertex evaluation requested"):
        evaluate_cases(load_cases()[:1], use_vertex=True)