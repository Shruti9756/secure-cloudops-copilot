from server import (
    SERVER_NAME,
    SERVER_VERSION,
    get_investigation_scope_payload,
)


def test_investigation_scope_describes_the_server_identity() -> None:
    scope = get_investigation_scope_payload()

    assert scope["server_name"] == SERVER_NAME
    assert scope["server_version"] == SERVER_VERSION
    assert scope["transport"] == "stdio"
    assert scope["mode"] == "read_only"


def test_investigation_scope_denies_dangerous_operations() -> None:
    scope = get_investigation_scope_payload()

    assert scope["allowed_operations"] == [
        "search tenant-scoped incident knowledge",
        "retrieve approved deployment context",
        "retrieve approved runbook context",
    ]
    assert scope["prohibited_operations"] == [
        "arbitrary shell commands",
        "arbitrary SQL queries",
        "unrestricted AWS API calls",
        "production resource changes",
    ]
