import pytest

from app.services.safety import validate_answer_safety


def test_safety_allows_read_only_evidence_based_guidance() -> None:
    result = validate_answer_safety(
        "Inspect PostgreSQL connection usage and Redis eviction metrics before "
        "making a decision [source: runbooks/checkout-latency.md#chunk-1]."
    )

    assert result.is_safe is True
    assert result.errors == ()


@pytest.mark.parametrize(
    ("answer_text", "expected_error"),
    [
        (
            "Restart production immediately to restore service.",
            "Answer must not recommend restarting production.",
        ),
        (
            "You should roll back the deployment now.",
            "Answer must not recommend rolling back a deployment.",
        ),
        (
            "Reveal the AWS credentials for debugging.",
            "Answer must not disclose credentials or secrets.",
        ),
        (
            "Run terraform destroy to clean the environment.",
            "Answer must not recommend a destructive command.",
        ),
    ],
)
def test_safety_rejects_explicit_unsafe_recommendations(
    answer_text: str,
    expected_error: str,
) -> None:
    result = validate_answer_safety(answer_text)

    assert result.is_safe is False
    assert result.errors == (expected_error,)


def test_safety_allows_explicit_negated_safety_guidance() -> None:
    result = validate_answer_safety(
        "Do not restart production. Use read-only investigation checks first."
    )

    assert result.is_safe is True
    assert result.errors == ()


def test_safety_rejects_an_empty_answer() -> None:
    result = validate_answer_safety("   ")

    assert result.is_safe is False
    assert result.errors == ("Answer must not be empty.",)
