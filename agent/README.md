# Simple Tool-Calling Agent (Python Implementation)

A minimal implementation of a tool-calling agent with MCP (Model Context Protocol) integration. The agent dynamically loads tools from MCP servers and uses them to help users.

## Quick Start

### Prerequisites

```bash
# Python 3.10 or higher
python --version
```

### Installation

From this directory, install the package in editable mode:

```bash
# With uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

### Set Up API Keys

The agent uses LiteLLM, which supports many LLM providers. Create a `.env` file in the project root with the appropriate API key:

```bash
# .env file
# For OpenAI
OPENAI_API_KEY=your-key-here

# For Anthropic Claude
ANTHROPIC_API_KEY=your-key-here

# For Google Gemini
GOOGLE_API_KEY=your-key-here
```


### Running the Agent

#### Start an MCP Server First


#### Run the Agent CLI

```bash
# Interactive CLI with MCP server
agent-cli http://localhost:3000/mcp

# Or run directly with python
python -m agent.cli http://localhost:3000/mcp

# Without MCP servers (limited functionality)
agent-cli
```

#### Alternatively Run the Web UI

```bash
# Start the web interface
agent-webui http://localhost:3000/mcp

# Or with custom port
agent-webui --port 8000 http://localhost:3000/mcp

# Then visit http://localhost:8000 in your browser
```

#### Run Benchmarks

```bash
# Run all benchmark tasks
agent-benchmark http://localhost:3000/mcp

# Filter by task ID (e.g., run task 15)
TASK_FILTER="15" agent-benchmark http://localhost:3000/mcp
```

## Architecture

```
User Input → Agent Loop → LLM Response
               ↓
         Tool Calls?
          ↙      ↘
        Yes      No
         ↓        ↓
    Call MCP    Return
     Server     Response
       ↓
   Continue
    Loop

MCP Servers (HTTP/stdio) ← → Agent
     ↓
   Tools dynamically loaded at startup
```

**Flow:**
1. Agent connects to MCP servers on initialization
2. Fetches available tools via `tools/list`
3. Converts tool schemas to OpenAI format
4. LLM generates tool calls based on available tools
5. Agent routes tool calls to appropriate MCP server
6. Results returned to LLM for next reasoning step

**Stopping Conditions:**
- No tool calls (agent provides answer/question)
- Max steps reached (default: 5)

## Configuration

### Changing the LLM Model

Edit `src/agent/config.py`:

```python
# In agent_llm function, change the model parameter:
return completion(
    model="gemini/gemini-2.0-flash",  # Change this
    messages=messages,
    tools=tools if has_tools else None,
    tool_choice="auto" if has_tools else None,
    temperature=0.0,
)
```

See [LiteLLM Providers](https://docs.litellm.ai/docs/providers) for all supported models. You need a modern model that supports tool calls.

### Adjusting Rate Limits

Edit `src/agent/config.py`:

```python
# Change the rate limiter configuration
rate_limiter = RateLimiter(max_calls=15, period=60)  # 15 per minute
```

## License

This is educational code for teaching purposes.
