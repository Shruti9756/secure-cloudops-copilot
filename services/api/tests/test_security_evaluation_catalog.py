"""Tests for the versioned SecureCloudOps AI-security evaluation catalogue."""

import json
from pathlib import Path

from app.services.safety import validate_answer_safety

# This resolves from services/api/tests back to the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SECURITY_EVALUATION_PATH = REPOSITORY_ROOT / "docs" / "evaluation" / "security-eval-cases-v1.json"

REQUIRED_SECURITY_CATEGORIES = {
    "indirect_prompt_injection",
    "unsafe_operational_action",
    "secret_exposure",
    "destructive_command",
    "safe_negated_guidance",
    "cross_tenant_access",
}


def load_security_evaluation_catalog() -> dict[str, object]:
    """Load the versioned security cases kept as reviewable project evidence."""
    return json.loads(SECURITY_EVALUATION_PATH.read_text(encoding="utf-8"))


def test_security_evaluation_catalog_has_required_structure_and_coverage() -> None:
    """Keep the catalogue valid, uniquely identified, and broad enough to be useful."""
    catalog = load_security_evaluation_catalog()

    assert catalog["suite_name"] == "SecureCloudOps AI Security Evaluation Cases"
    assert catalog["suite_version"] == "v1"

    cases = catalog["cases"]
    assert isinstance(cases, list)
    assert len(cases) >= len(REQUIRED_SECURITY_CATEGORIES)
    assert all(isinstance(case, dict) for case in cases)

    case_ids = [case["id"] for case in cases]
    assert all(isinstance(case_id, str) for case_id in case_ids)
    assert len(case_ids) == len(set(case_ids))

    categories = {case["category"] for case in cases}
    assert REQUIRED_SECURITY_CATEGORIES <= categories

    for case in cases:
        assert {"id", "category", "title", "threat", "attack_surface", "input", "expected"} <= set(
            case
        )

        expected = case["expected"]
        assert isinstance(expected, dict)
        assert expected["safety_validation"] in {
            "allowed",
            "blocked",
            "not_applicable",
        }
        assert isinstance(expected["expected_errors"], list)
        assert isinstance(expected["required_controls"], list)
        assert expected["required_controls"]


def test_catalogue_safety_cases_match_the_deterministic_output_guard() -> None:
    """Execute candidate answers that the output-safety guard is responsible for."""
    catalog = load_security_evaluation_catalog()

    for case in catalog["cases"]:
        expected = case["expected"]
        assert isinstance(expected, dict)

        expected_validation = expected["safety_validation"]
        if expected_validation == "not_applicable":
            # Tenant isolation is enforced in retrieval/API tests, not by output text checks.
            continue

        input_data = case["input"]
        assert isinstance(input_data, dict)

        candidate_answer = input_data.get("candidate_answer")
        assert isinstance(candidate_answer, str)

        result = validate_answer_safety(candidate_answer)

        assert result.is_safe is (expected_validation == "allowed"), case["id"]
        assert list(result.errors) == expected["expected_errors"], case["id"]
