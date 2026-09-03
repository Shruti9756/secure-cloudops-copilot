import pytest

from app.services.structured_answer import (
    parse_structured_answer,
    render_answer_with_citations,
)

VALID_MODEL_OUTPUT = (
    '{"answer":"The timeout change is a likely hypothesis.",'
    '"citations":["deployments/checkout-2.4.0.md#chunk-0"]}'
)


def test_parse_structured_answer_accepts_the_expected_json_shape() -> None:
    answer = parse_structured_answer(VALID_MODEL_OUTPUT)

    assert answer.answer == "The timeout change is a likely hypothesis."
    assert answer.citations == ["deployments/checkout-2.4.0.md#chunk-0"]
    assert render_answer_with_citations(answer) == (
        "The timeout change is a likely hypothesis. [source: deployments/checkout-2.4.0.md#chunk-0]"
    )


@pytest.mark.parametrize(
    "content",
    [
        "This is ordinary model text, not JSON.",
        '{"answer":"A response without citations."}',
        '{"answer":"A response.","citations":[]}',
        (
            '{"answer":"A response.",'
            '"citations":["runbooks/checkout-latency.md#chunk-0",'
            '"runbooks/checkout-latency.md#chunk-0"]}'
        ),
        (
            '{"answer":"A response [source: runbooks/checkout-latency.md#chunk-0].",'
            '"citations":["runbooks/checkout-latency.md#chunk-0"]}'
        ),
        (
            '{"answer":"A response.",'
            '"citations":["runbooks/checkout-latency.md#chunk-0"],'
            '"reasoning":"This extra field must be rejected."}'
        ),
    ],
)
def test_parse_structured_answer_rejects_invalid_model_output(content: str) -> None:
    with pytest.raises(
        ValueError,
        match="generated response did not match the required answer schema",
    ):
        parse_structured_answer(content)
