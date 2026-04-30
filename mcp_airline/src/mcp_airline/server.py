"""Factory for the airline MCP server instance.

The :func:`create_mcp_server` helper centralises FastMCP configuration so that
consumers primarily work within :mod:`mcp_airline.tools` when adding or
adjusting behaviour. Keeping this file compact makes it easier to reason about
the server surface area and encourages deliberate tool design.
"""

from fastmcp import FastMCP
from .database import AirlineDatabase
from .tools import register_tools


def create_mcp_server(database: AirlineDatabase) -> FastMCP:
    """Create and configure the FastMCP server for the airline domain.

    Args:
        database: Shared :class:`AirlineDatabase` instance holding the
            in-memory airline state for all tools.

    Returns:
        A ready-to-run :class:`fastmcp.FastMCP` object with all built-in tools
        registered.
    """

    # Using a single FastMCP instance keeps tool registration deterministic and
    # mirrors the structure recommended for custom domains.
    mcp = FastMCP("airline-domain-server")

    register_tools(mcp, database)

    @mcp.tool()
    def reset() -> str:
        """Reset the shared database to its initial state.

    This helper is intentionally tiny: it simply reloads the JSON snapshot so
    tests (and manual experiments) can return to a known baseline after
    running mutating tools.
        """

        database.reload()
        return "true"

    return mcp
