from scripts.embed_chunked_documents import parse_arguments


def test_parse_arguments_uses_the_safe_default_tenant_and_real_run_mode() -> None:
    args = parse_arguments([])

    assert args.tenant == "nimbuscart"
    assert args.dry_run is False


def test_parse_arguments_accepts_a_tenant_and_dry_run_mode() -> None:
    args = parse_arguments(
        [
            "--tenant",
            "demo-tenant",
            "--dry-run",
        ]
    )

    assert args.tenant == "demo-tenant"
    assert args.dry_run is True
