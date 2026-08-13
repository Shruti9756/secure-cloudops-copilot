import pytest

from scripts.search_knowledge import parse_arguments


def test_parse_arguments_uses_safe_defaults() -> None:
    args = parse_arguments(["Why is checkout slow after deployment?"])

    assert args.query == "Why is checkout slow after deployment?"
    assert args.tenant == "nimbuscart"
    assert args.limit == 3


def test_parse_arguments_accepts_tenant_and_limit() -> None:
    args = parse_arguments(
        [
            "Show the checkout deployment details",
            "--tenant",
            "demo-tenant",
            "--limit",
            "5",
        ]
    )

    assert args.query == "Show the checkout deployment details"
    assert args.tenant == "demo-tenant"
    assert args.limit == 5


def test_parse_arguments_rejects_an_out_of_range_limit() -> None:
    with pytest.raises(SystemExit):
        parse_arguments(
            [
                "Show the checkout deployment details",
                "--limit",
                "11",
            ]
        )
