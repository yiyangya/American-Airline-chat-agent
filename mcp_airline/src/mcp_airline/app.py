"""Entry point for the airline MCP server.

This module wires together the FastMCP server defined in :mod:`mcp_airline.server`
with the optional HTTP routes served by :mod:`mcp_airline.web_routes`.

The implementation highlights the two supported runtime modes:

* **stdio transport** (default) – ideal when launching the server from an MCP
    client or the inspector.
* **HTTP transport** – enabled when a ``PORT`` environment variable is set. This
    is useful for demonstrations that include the provided web UI.
"""

import os
import sys
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from .database import AirlineDatabase
from .server import create_mcp_server
from .web_routes import register_web_routes


def main() -> None:
    """Run the MCP server and, if requested, expose the accompanying web API.

    The runtime behaviour is controlled through environment variables:

    ``PORT``
        When provided, the server listens over HTTP on this port and the web UI
        routes are registered. Without it, the server falls back to stdio
        transport (the common case for MCP clients).
    ``HOST``
        Optional host/interface override for HTTP mode. Defaults to
        ``"127.0.0.1"`` to keep the service bound to localhost. Override this
        if you intentionally need to expose the server to other machines.
    """

    database = AirlineDatabase.from_tau2_bench()
    mcp = create_mcp_server(database)

    port = os.environ.get("PORT")
    host = os.environ.get("HOST", "127.0.0.1")

    if port:
        # The HTTP transport exposes both MCP and the small Starlette web UI.
        register_web_routes(mcp, database)
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["*"],
                expose_headers=["mcp-session-id", "mcp-protocol-version"],
                max_age=86400,
            )
        ]

        port_num = int(port)
        print(f"✈️ MCP Server running on http://{host}:{port_num}/mcp", file=sys.stderr)
        print(f"🌐 Web UI for user data management running on http://{host}:{port_num}/", file=sys.stderr)
        mcp.run(transport="http", host=host, port=port_num, middleware=middleware)
    else:
        # StdIO transport keeps compatibility with the MCP inspector and most
        # agents. This is the default execution path unless HTTP transport is
        # explicitly requested via environment variables.
        mcp.run()


if __name__ == "__main__":
    main()
