"""
BOILERPLATE CODE - NOT IMPORTANT FOR ASSIGNMENT

This file is a thin wrapper around the MCP SDK that handles:
- Connecting to MCP servers (via stdio or HTTP)
- Listing available tools from servers
- Calling tools with arguments
- Managing connection lifecycle

This is standard integration code for working with MCP servers.
The interesting agent logic is in agent.py and tool_manager.py.
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


@dataclass
class MCPServerStatus:
    """Status information for an MCP server connection"""
    config: str
    transport: str  # 'stdio' or 'http'
    status: str  # 'connected' or 'failed'
    error: Optional[str] = None


@dataclass
class MCPTool:
    """MCP tool definition from the MCP protocol"""
    name: str
    description: Optional[str]
    inputSchema: Dict[str, Any]


class MCPServerConnection:
    """
    Manages connection to a single MCP server.
    Simple wrapper around the MCP SDK Client.
    """

    def __init__(self, config_string: str):
        """
        Initialize MCP server connection.

        Args:
            config_string: Either an HTTP URL (http://...) or a command string for stdio
        """
        self.config_string = config_string
        self.is_connected = False
        self.error: Optional[str] = None
        self.tools: List[MCPTool] = []

        # Detect transport type from config string
        if config_string.startswith('http://') or config_string.startswith('https://'):
            self.transport_type = 'http'
            self.server_url = config_string
            self.server_params = None
        else:
            self.transport_type = 'stdio'
            self.server_url = None
            # Parse command and args for stdio
            parts = config_string.split()
            self.server_params = StdioServerParameters(
                command=parts[0],
                args=parts[1:] if len(parts) > 1 else []
            )

    def connect(self) -> None:
        """Connect to the MCP server and cache the tools list synchronously"""
        try:
            # Just test the connection and cache tools
            self.tools = self._run(self._list_tools())
            self.is_connected = True
        except Exception as e:
            self.error = str(e)
            self.is_connected = False
            raise

    def list_tools(self) -> List[MCPTool]:
        """Synchronously request list of available tools from the server"""
        return self._run(self._list_tools())

    def call_tool(self, name: str, args: Dict[str, Any]) -> str:
        """
        Call a tool on the server with given arguments (blocking).

        Args:
            name: Tool name
            args: Tool arguments as a dictionary

        Returns:
            Tool result as a string
        """
        return self._run(self._call_tool(name, args))

    def disconnect(self) -> None:
        """Close connection to the server"""
    # With HTTP and stdio clients, connections are managed by context managers
        # so no explicit cleanup needed
        self.is_connected = False

    def _run(self, coro):
        """Helper to execute an async coroutine synchronously."""
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            raise RuntimeError(
                "MCP operations must run from synchronous code. "
                "Detected an existing running event loop."
            ) from exc

    async def _list_tools(self) -> List[MCPTool]:
        """Request list of available tools from the server"""
        if self.transport_type == 'http':
            async with streamablehttp_client(self.server_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    return [
                        MCPTool(
                            name=tool.name,
                            description=tool.description,
                            inputSchema=tool.inputSchema
                        )
                        for tool in response.tools
                    ]
        else:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    return [
                        MCPTool(
                            name=tool.name,
                            description=tool.description,
                            inputSchema=tool.inputSchema
                        )
                        for tool in response.tools
                    ]

    async def _call_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Internal async helper for calling tools"""
        if self.transport_type == 'http':
            async with streamablehttp_client(self.server_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(name, arguments=args)
                    return '\n'.join(
                        item.text for item in response.content
                        if item.type == 'text'
                    )
        else:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(name, arguments=args)
                    return '\n'.join(
                        item.text for item in response.content
                        if item.type == 'text'
                    )

    def get_status(self) -> MCPServerStatus:
        """Get current connection status"""
        return MCPServerStatus(
            config=self.config_string,
            transport=self.transport_type,
            status='connected' if self.is_connected else 'failed',
            error=self.error
        )
