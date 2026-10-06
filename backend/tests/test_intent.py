import pytest

from app.services.intent_parser import parse_intent


def test_extracts_budget_constraint():
    intent = parse_intent("I need a laptop under $1000")

    assert intent.hard_constraints.max_budget == 1000
    assert intent.category == "laptop"
    assert intent.clarification_needed is False


def test_extracts_minimum_ram_constraint():
    intent = parse_intent("Laptop with at least 16 GB RAM")

    assert intent.hard_constraints.min_ram_gb == 16


def test_extracts_maximum_weight_constraint():
    intent = parse_intent("Laptop under 1.5 kg")

    assert intent.hard_constraints.max_weight_kg == 1.5


@pytest.mark.parametrize(
    ("query", "constraint_os", "preference_os"),
    [
        ("I must use Windows", ("Windows", None), None),
        ("Windows only laptop", ("Windows", None), None),
        ("I prefer Windows", None, ("Windows", None)),
        ("Windows laptop under $1000", None, ("Windows", None)),
        ("I must use Windows 11", ("Windows", "11"), None),
        ("I prefer Windows 11", None, ("Windows", "11")),
    ],
)
def test_os_strength_depends_on_language(query, constraint_os, preference_os):
    intent = parse_intent(query)

    actual_constraint = intent.hard_constraints
    actual_preference = intent.preferences
    actual_constraint_os = (
        (actual_constraint.operating_system_family, actual_constraint.operating_system_version)
        if actual_constraint.operating_system
        else None
    )
    actual_preference_os = (
        (actual_preference.operating_system_family, actual_preference.operating_system_version)
        if actual_preference.operating_system
        else None
    )
    assert actual_constraint_os == constraint_os
    assert actual_preference_os == preference_os
    if constraint_os:
        assert actual_constraint.operating_system == " ".join(filter(None, constraint_os))
    if preference_os:
        assert actual_preference.operating_system == " ".join(filter(None, preference_os))


def test_extracts_combined_constraints_and_preferences():
    intent = parse_intent(
        "Windows only laptop under $1000 with at least 16 GB RAM under 1.5 kg "
        "for cybersecurity school and virtual machines, preferably 1 TB storage"
    )

    assert intent.hard_constraints.max_budget == 1000
    assert intent.hard_constraints.min_ram_gb == 16
    assert intent.hard_constraints.max_weight_kg == 1.5
    assert intent.hard_constraints.operating_system == "Windows"
    assert intent.hard_constraints.operating_system_family == "Windows"
    assert intent.hard_constraints.operating_system_version is None
    assert intent.preferences.operating_system is None
    assert intent.preferences.use_case == "cybersecurity, school, virtual machines"
    assert intent.preferences.storage_preference_gb == 1024
    assert "cybersecurity" in intent.evidence
    assert any("1 TB storage" in phrase for phrase in intent.evidence)
    assert intent.clarification_needed is False


def test_ambiguous_query_does_not_guess_numeric_constraint():
    intent = parse_intent("I want a lightweight laptop for school")

    assert intent.hard_constraints.max_weight_kg is None
    assert intent.preferences.portability_preference == "lightweight"
    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_conflicting_budget_values_need_clarification():
    intent = parse_intent("Laptop under $800 or under $1000")

    assert intent.hard_constraints.max_budget is None
    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_ambiguous_operating_systems_are_not_guessed():
    intent = parse_intent("Windows or Ubuntu laptop under $1000")

    assert intent.hard_constraints.operating_system is None
    assert intent.preferences.operating_system is None
    assert intent.clarification_needed is True
    assert intent.clarification_question


def test_intent_endpoint_returns_parsed_contract(client):
    response = client.post(
        "/api/v1/intent",
        json={"query": "Windows only laptop under $1000 with at least 16 GB RAM"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_query"] == "Windows only laptop under $1000 with at least 16 GB RAM"
    assert body["hard_constraints"]["operating_system"] == "Windows"
    assert body["hard_constraints"]["operating_system_family"] == "Windows"
    assert body["hard_constraints"]["operating_system_version"] is None
    assert body["hard_constraints"]["max_budget"] == 1000
    assert body["hard_constraints"]["min_ram_gb"] == 16
    assert body["preferences"]["operating_system"] is None


@pytest.mark.parametrize("body", [{}, {"query": "   "}, {"query": 42}, {"query": "x", "other": True}])
def test_intent_endpoint_rejects_malformed_request(client, body):
    response = client.post("/api/v1/intent", json=body)

    assert response.status_code == 422


def test_intent_endpoint_returns_clarification_state(client):
    response = client.post("/api/v1/intent", json={"query": "I need a lightweight laptop for school"})

    assert response.status_code == 200
    body = response.json()
    assert body["clarification_needed"] is True
    assert body["clarification_question"]
    assert body["hard_constraints"]["max_weight_kg"] is None


def test_non_laptop_category_intent_uses_generic_attribute_maps():
    from app.models.intent import ParsedShoppingIntent

    intent = ParsedShoppingIntent(
        original_query="Camera with a full-frame sensor",
        category="camera",
        category_hard_constraints={"sensor_format": "full-frame"},
        category_preferences={"body_style": "mirrorless"},
        clarification_needed=False,
        confidence=0.9,
    )

    assert intent.category == "camera"
    assert intent.category_hard_constraints == {"sensor_format": "full-frame"}
    assert intent.category_preferences == {"body_style": "mirrorless"}
    assert intent.hard_constraints.min_ram_gb is None
    assert intent.hard_constraints.max_weight_kg is None
    assert intent.hard_constraints.operating_system is None