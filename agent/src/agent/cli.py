#!/usr/bin/env python3
"""
CLI Interface - Interactive command-line interface for the agent.

Usage:
    agent-cli [MCP_SERVER_URL]...

Examples:
    agent-cli
    agent-cli http://localhost:3000/mcp
    agent-cli http://localhost:3000/mcp http://localhost:3001/mcp
"""

import sys
from .agent import ToolCallingAgent
from .tool_manager import ToolManager


def main():
    """Main CLI entrypoint"""
    mcp_servers = sys.argv[1:]

    # Connect to MCP servers
    tool_manager = ToolManager.from_servers(mcp_servers)

    if not mcp_servers:
        print('Usage: agent-cli [MCP_SERVER_URL]...')
        print('Example: agent-cli http://localhost:3000/mcp\n')

    # Create agent
    agent = ToolCallingAgent(tool_manager)

    # Interactive loop
    print("\n" + "=" * 60)
    print("🤖 Agent ready! Type 'quit' or 'exit' to stop.")
    print("=" * 60)

    try:
        while True:
            try:
                user_input = input('\n💬 You: ').strip()

                # Check for exit commands
                if not user_input or user_input.lower() in ['quit', 'exit']:
                    print('\n👋 Goodbye!\n')
                    break

                # Execute the user's task
                try:
                    response = agent.execute(user_input)

                    if response:
                        print(f"\n🤖 Agent: {response}\n")
                    else:
                        print('\n🤖 Agent: (no response)\n')
                except Exception as agent_error:
                    print(f"\n❌ Agent error: {agent_error}\n")
                    raise

            except KeyboardInterrupt:
                print('\n\n👋 Goodbye!\n')
                break
            except Exception as e:
                print(f'\n❌ Error: {e}\n')

    finally:
        tool_manager.disconnect()


if __name__ == '__main__':
    main()
