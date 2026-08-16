"""Read-only MCP server for SecureCloudOps Copilot."""

from mcp.server import MCPServer

SERVER_NAME = "secure-cloudops-mcp"
SERVER_VERSION = "0.1.0"

# The SDK uses type hints and docstrings to publish the MCP tool schema.
mcp = MCPServer(SERVER_NAME)


def get_investigation_scope_payload() -> dict[str, object]:
    """Build a visible, testable description of this server's security boundary."""
    return {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "transport": "stdio",
        "mode": "read_only",
        "allowed_operations": [
            "search tenant-scoped incident knowledge",
            "retrieve approved deployment context",
            "retrieve approved runbook context",
        ],
        "prohibited_operations": [
            "arbitrary shell commands",
            "arbitrary SQL queries",
            "unrestricted AWS API calls",
            "production resource changes",
        ],
    }


@mcp.tool()
def get_investigation_scope() -> dict[str, object]:
    """Return the capabilities and enforced safety boundaries of this MCP server."""
    return get_investigation_scope_payload()


if __name__ == "__main__":
    # STDIO carries JSON-RPC messages, so this server must never use print().
    mcp.run(transport="stdio")
