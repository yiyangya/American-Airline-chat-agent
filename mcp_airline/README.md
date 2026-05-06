# Airline MCP Server Starter

This folder contains a starter implementation for an airline reservation MCP
server. 

## Quick start

1. Install Python 3.10+.
2. From this directory, install the package in editable mode (pick your favourite manager):

   ```bash
   uv sync
   ```

   or

   ```bash
   pip install -e .
   ```

3. Start the HTTP transport (recommended) so you get both the MCP endpoint and the web UI:

   ```bash
   # bash / zsh (Linux, macOS, Git Bash)
   PORT=8000 uv run start-airline-server
   
   # PowerShell (Windows)
   $env:PORT = "8000"; uv run start-airline-server
   ```
   
   This binds to `http://127.0.0.1:8000` by default. 

   For stdio transport, omit `PORT` (bash) or skip the `$env:PORT` assignment (PowerShell).

## Trying it out with the MCP Inspector

The [Model Context Protocol Inspector](https://github.com/modelcontextprotocol/inspector) offers a
great way to explore the tools interactively:

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

This launches the inspector and lets you inspect argument schemas,
preview responses, and debug new tools rapidly.
