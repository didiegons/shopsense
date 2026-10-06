import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.intent import ParsedShoppingIntent
from app.services.intent_comparison import values_equivalent
from app.services.intent_parser import parse_intent

DEFAULT_DATASET = BACKEND_ROOT / "evaluations" / "intent_cases.json"
MISSING = object()


def load_cases(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as dataset_file:
        cases = json.load(dataset_file)
    if not isinstance(cases, list):
        raise ValueError("Evaluation dataset must be a JSON array")
    identifiers: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Evaluation case {index} must be an object")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"Evaluation case {index} requires a non-empty id")
        if identifier in identifiers:
            raise ValueError(f"Duplicate evaluation case id: {identifier}")
        identifiers.add(identifier)
        if not isinstance(case.get("query"), str) or not isinstance(case.get("category"), str):
            raise ValueError(f"Evaluation case {identifier} requires query and category strings")
        if not isinstance(case.get("expected"), dict) or "clarification_needed" not in case["expected"]:
            raise ValueError(f"Evaluation case {identifier} requires expected.clarification_needed")
    return cases


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return MISSING
            current = current[part]
        else:
            return None
    return current


def _expected_fields(expected: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for section in (
        "category",
        "hard_constraints",
        "preferences",
        "category_hard_constraints",
        "category_preferences",
    ):
        if section not in expected:
            continue
        value = expected[section]
        if section.startswith("category_"):
            fields[section] = value
        elif section == "category" or not isinstance(value, dict):
            fields[section] = value
        else:
            for name, field_value in value.items():
                fields[f"{section}.{name}"] = field_value
    return fields


def _metric_counts(passed: int, failed: int) -> dict[str, int | float]:
    evaluated = passed + failed
    return {
        "passed": passed,
        "failed": failed,
        "evaluated": evaluated,
        "accuracy": passed / evaluated if evaluated else 0.0,
    }


def evaluate_cases(cases: list[dict[str, Any]], use_vertex: bool = False) -> dict[str, Any]:
    vertex_parser = None
    if use_vertex:
        from app.services.vertex_intent import VertexIntentAdapter

        adapter = VertexIntentAdapter.from_environment()
        if adapter is None:
            raise RuntimeError(
                "Vertex evaluation requested, but VERTEX_AI_PROJECT, VERTEX_AI_REGION, "
                "and SHOPSENSE_INTENT_MODEL are not all configured."
            )
        vertex_parser = adapter.parse

    field_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    category_field_counts: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    category_counts: Counter[str] = Counter()
    category_clarification: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    clarification = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    parser_sources: Counter[str] = Counter()
    case_results: list[dict[str, Any]] = []

    for case in cases:
        category = case["category"]
        category_counts[category] += 1
        if vertex_parser:
            intent = _resolve_with_vertex(case, vertex_parser)
        else:
            intent = parse_intent(case["query"], category)

        parser_sources[intent.parser_source] += 1
        actual = intent.model_dump(mode="json")
        expected = case["expected"]
        case_field_results: dict[str, dict[str, Any]] = {}
        diagnostics = {
            "parser_source": intent.parser_source,
            "confidence": intent.confidence,
            "deterministic_agreement": intent.deterministic_agreement,
            "differing_fields": intent.differing_fields,
        }

        for field_path, expected_value in _expected_fields(expected).items():
            actual_value = _get_path(actual, field_path)
            passed = values_equivalent(field_path, expected_value, actual_value, expected, actual)
            case_field_results[field_path] = {
                "expected": expected_value,
                "actual": "<missing>" if actual_value is MISSING else actual_value,
                "passed": passed,
                **diagnostics,
                "clarification_expected": expected["clarification_needed"],
                "clarification_actual": intent.clarification_needed,
            }
            field_counts[field_path][0 if passed else 1] += 1
            category_field_counts[category][field_path][0 if passed else 1] += 1

        expected_clarification = expected["clarification_needed"]
        actual_clarification = intent.clarification_needed
        if actual_clarification and expected_clarification:
            clarification["tp"] += 1
        elif actual_clarification:
            clarification["fp"] += 1
        elif expected_clarification:
            clarification["fn"] += 1
        else:
            clarification["tn"] += 1
        category_clarification[category][0 if actual_clarification == expected_clarification else 1] += 1
        case_field_results["clarification_needed"] = {
            "expected": expected_clarification,
            "actual": actual_clarification,
            "passed": actual_clarification == expected_clarification,
            **diagnostics,
            "clarification_expected": expected_clarification,
            "clarification_actual": actual_clarification,
        }

        case_results.append(
            {
                "id": case["id"],
                "category": category,
                "parser_source": intent.parser_source,
                "confidence": intent.confidence,
                "deterministic_agreement": intent.deterministic_agreement,
                "differing_fields": intent.differing_fields,
                "expected_intent_fields": _expected_fields(expected),
                "actual_intent": actual,
                "field_results": case_field_results,
                "clarification_expected": expected_clarification,
                "clarification_actual": actual_clarification,
                "clarification_pass": actual_clarification == expected_clarification,
            }
        )

    field_report = {
        field: _metric_counts(counts[0], counts[1])
        for field, counts in sorted(field_counts.items())
    }
    category_report: dict[str, Any] = {}
    for category, count in sorted(category_counts.items()):
        per_field = {
            field: _metric_counts(counts[0], counts[1])
            for field, counts in sorted(category_field_counts[category].items())
        }
        clarification_passed, clarification_failed = category_clarification[category]
        evaluated_fields = sum(metric["evaluated"] for metric in per_field.values())
        passed_fields = sum(metric["passed"] for metric in per_field.values())
        category_report[category] = {
            "cases": count,
            "field_extraction": _metric_counts(passed_fields, evaluated_fields - passed_fields),
            "fields": per_field,
            "clarification": _metric_counts(clarification_passed, clarification_failed),
        }

    total_fields = sum(counts[0] + counts[1] for counts in field_counts.values())
    passed_fields = sum(counts[0] for counts in field_counts.values())
    clarification_total = sum(clarification.values())
    clarification_correct = clarification["tp"] + clarification["tn"]
    precision_denominator = clarification["tp"] + clarification["fp"]
    recall_denominator = clarification["tp"] + clarification["fn"]
    precision = clarification["tp"] / precision_denominator if precision_denominator else 0.0
    recall = clarification["tp"] / recall_denominator if recall_denominator else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "mode": "vertex" if use_vertex else "deterministic",
        "total_cases": len(cases),
        "parser_source_counts": dict(sorted(parser_sources.items())),
        "field_extraction": {
            **_metric_counts(passed_fields, total_fields - passed_fields),
            "by_field": field_report,
        },
        "clarification": {
            **clarification,
            "evaluated": clarification_total,
            "accuracy": clarification_correct / clarification_total if clarification_total else 0.0,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "category_counts": dict(sorted(category_counts.items())),
        "by_category": category_report,
        "cases": case_results,
    }


def _resolve_with_vertex(case: dict[str, Any], parser) -> ParsedShoppingIntent:
    from app.services.intent_service import resolve_intent

    return resolve_intent(case["query"], case["category"], ai_parser=parser)


def main() -> int:
    argument_parser = argparse.ArgumentParser(description="Offline ShopSense intent evaluation")
    argument_parser.add_argument("--vertex", action="store_true", help="Opt in to live Vertex AI requests")
    argument_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    arguments = argument_parser.parse_args()

    try:
        report = evaluate_cases(load_cases(arguments.dataset), use_vertex=arguments.vertex)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        argument_parser.error(str(error))

    print(json.dumps(report, indent=2, sort_keys=True))
    metrics_failed = report["field_extraction"]["failed"] > 0 or (
        report["clarification"]["fp"] + report["clarification"]["fn"] > 0
    )
    vertex_fallbacks = arguments.vertex and report["parser_source_counts"].get("deterministic", 0) > 0
    return 1 if metrics_failed or vertex_fallbacks else 0


if __name__ == "__main__":
    raise SystemExit(main())