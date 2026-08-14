import pytest

from scripts.ask_knowledge import parse_arguments


def test_parse_arguments_uses_safe_defaults() -> None:
    args = parse_arguments(["Why did checkout latency increase?"])

    assert args.question == "Why did checkout latency increase?"
    assert args.tenant == "nimbuscart"
    assert args.limit == 3


def test_parse_arguments_accepts_tenant_and_limit() -> None:
    args = parse_arguments(
        [
            "What changed in checkout 2.4.0?",
            "--tenant",
            "demo-tenant",
            "--limit",
            "5",
        ]
    )

    assert args.question == "What changed in checkout 2.4.0?"
    assert args.tenant == "demo-tenant"
    assert args.limit == 5


def test_parse_arguments_rejects_an_out_of_range_limit() -> None:
    with pytest.raises(SystemExit):
        parse_arguments(
            [
                "What changed in checkout 2.4.0?",
                "--limit",
                "11",
            ]
        )
