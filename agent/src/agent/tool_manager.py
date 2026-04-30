"""
Tool Manager - Manages MCP server connections and tool execution.

This module:
- Connects to multiple MCP servers
- Aggregates tools from all servers
- Routes tool calls to the appropriate server
- Tracks which server provides which tool
"""

from typing import Dict, List, Any
from .mcp_client import MCPServerConnection, MCPServerStatus, MCPTool


def convert_mcp_tools_to_openai(mcp_tools: List[MCPTool]) -> List[Dict[str, Any]]:
    """
    Convert MCP tool definitions to OpenAI tool calling format.

    MCP tools use JSON Schema for their input definitions.
    OpenAI's tool calling also uses a similar format, so this is mostly
    a straightforward conversion.

    Args:
        mcp_tools: List of MCP tool definitions

    Returns:
        List of tool definitions in OpenAI format
    """
    openai_tools = []

    for tool in mcp_tools:
        input_schema = tool.inputSchema
        properties = input_schema.get('properties', {})
        required = input_schema.get('required', [])

        # Convert to OpenAI function calling format
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or f"Tool: {tool.name}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

        openai_tools.append(openai_tool)

    return openai_tools


class ToolManager:
    """
    Manages multiple MCP server connections and aggregates their tools.

    The ToolManager connects to one or more MCP servers, discovers their tools,
    and provides a unified interface for executing tools across all servers.
    """

    def __init__(self):
        """Initialize the tool manager with no servers"""
        self.mcp_servers: List[MCPServerConnection] = []
        self.tools: List[Dict[str, Any]] = []
        self.tool_to_server_map: Dict[str, MCPServerConnection] = {}

    def add_mcp_server(self, config: str) -> None:
        """
        Add an MCP server and load its tools.

        Args:
            config: Server configuration string (HTTP URL or stdio command)

        Raises:
            Exception: If connection fails
        """
        server = MCPServerConnection(config)

        try:
            server.connect()

            # List tools from this server
            mcp_tools = server.tools  # Already cached during connect
            print(f"   📋 Found {len(mcp_tools)} tools from {config}")

            # Convert to OpenAI format
            converted_tools = convert_mcp_tools_to_openai(mcp_tools)

            # Track which server provides which tool
            for tool_def in converted_tools:
                tool_name = tool_def['function']['name']

                # Skip the 'reset' tool from being exposed to the agent
                if tool_name == "reset":
                    continue

                # Check for duplicate tool names
                if tool_name in self.tool_to_server_map:
                    print(f"   ⚠️  Tool '{tool_name}' already exists, skipping")
                else:
                    self.tools.append(tool_def)
                    self.tool_to_server_map[tool_name] = server

            self.mcp_servers.append(server)

            tool_names = [t['function']['name'] for t in converted_tools if t['function']['name'] != 'reset']
            print(f"   ✅ Connected to server {config}, found {len(tool_names)} tools: {', '.join(tool_names)}\n")

        except Exception as error:
            error_msg = str(error)
            print(f"   ❌ Failed to connect to {config}: {error_msg}\n")
            raise

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        Get all available tools in OpenAI format.

        Returns:
            List of tool definitions
        """
        return self.tools

    def execute_tool(self, tool_name: str, input_data: Dict[str, Any]) -> str:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            input_data: Input arguments for the tool

        Returns:
            Tool execution result as a string

        Raises:
            Exception: If tool execution fails
        """
        mcp_server = self.tool_to_server_map.get(tool_name)

        if mcp_server:
            try:
                result = mcp_server.call_tool(tool_name, input_data)
                return result
            except Exception as error:
                error_msg = str(error)
                raise Exception(f"Tool execution failed: {error_msg}")
        else:
            return "Invalid tool call"

    def get_server_status(self) -> List[MCPServerStatus]:
        """
        Get status of all MCP servers.

        Returns:
            List of server status information
        """
        return [server.get_status() for server in self.mcp_servers]

    def disconnect(self) -> None:
        """Disconnect from all MCP servers"""
        for server in self.mcp_servers:
            server.disconnect()

    def reset_all(self) -> bool:
        """
        For testing and evaluations, this will call a reset method on all connected MCP servers.

        Returns:
            True if all servers have the method and return "true" when called
        """
        results = []
        for server in self.mcp_servers:
            try:
                result = server.call_tool("reset", {})
                results.append(result == "true")
            except:
                results.append(False)

        return all(results)

    @classmethod
    def from_servers(cls, mcp_servers: List[str]) -> 'ToolManager':
        """
        Create a ToolManager and connect to a list of MCP servers.

        Args:
            mcp_servers: List of MCP server URLs or commands

        Returns:
            Initialized ToolManager with connected servers
        """
        tool_manager = cls()

        if not mcp_servers:
            print('⚠️  No MCP servers configured\n')
            return tool_manager

        print(f"Connecting to {len(mcp_servers)} MCP server(s)...\n")

        for server in mcp_servers:
            try:
                tool_manager.add_mcp_server(server)
            except Exception as error:
                print(f"⚠️  Warning: Failed to connect to {server}: {error}\n")

        return tool_manager
