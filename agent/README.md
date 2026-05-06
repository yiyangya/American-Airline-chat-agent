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
uv sync
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux or macOS

# Or with pip
pip install -e .
```
> **Tip:** if you'd rather not activate the venv, prefix every command with
> `uv run` (e.g. `uv run agent-cli http://localhost:8000/mcp`).

### Set Up API Keys

The agent uses LiteLLM, which supports many LLM providers. Create a `.env` file in this directory (`agent/`) with the appropriate API key. LiteLLM automatically loads it on startup, so no extra setup is needed:

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

```bash
# In a separate terminal, from the mcp_airline/ folder:
# bash / zsh (Linux, macOS, Git Bash)
PORT=8000 uv run start-airline-server

# PowerShell (Windows)
$env:PORT = "8000"; uv run start-airline-server
# MCP endpoint will be at http://localhost:8000/mcp
```

#### Run the Agent CLI

```bash
# Interactive CLI with MCP server
agent-cli http://localhost:8000/mcp

# Or run directly with python
python -m agent.cli http://localhost:8000/mcp

# Without MCP servers (limited functionality)
agent-cli
```

#### Alternatively Run the Web UI

```bash
# Start the web interface
agent-webui http://localhost:8000/mcp

# Or with custom port
agent-webui --port 3000 http://localhost:8000/mcp

# Then visit http://localhost:8000 in your browser
```

#### Run Benchmarks

```bash
# Run all benchmark tasks
agent-benchmark http://localhost:8000/mcp

# Or run directly with python
python -m agent.benchmark http://localhost:8000/mcp

# Filter by task ID (e.g., run task 15)
# bash / zsh (Linux, macOS, Git Bash)
TASK_FILTER="15" agent-benchmark http://localhost:3000/mcp

# PowerShell (Windows)
$env:TASK_FILTER="15"; agent-benchmark http://localhost:8000/mcp
```

#### Sample Benchmark Run

Below is the output from running task **22** — a multi-action booking modification where the simulated user (a Gold member) asks the agent to change a reservation's passenger, upgrade its cabin, add checked bags, and pay the upgrade fee with a specific gift card. It shows the full loop: MCP connection, turn-by-turn agent ↔ user-simulator dialogue, and the evaluator's scoring of both expected actions and natural-language assertions.

<details>
<summary><b>Click to expand full transcript</b></summary>

```text
PS C:\...\AA_Capstone\agent> uv run python -m agent.benchmark http://localhost:8000/mcp
🚀 Starting Tau2 Benchmark

📋 Loaded 50 tasks
Connecting to 1 MCP server(s)...

   📋 Found 15 tools from http://localhost:8000/mcp
   ✅ Connected to server http://localhost:8000/mcp, found 14 tools: book_reservation,
      cancel_reservation, get_reservation_details, update_reservation_baggages,
      update_reservation_flights, update_reservation_passengers, search_direct_flight,
      search_onestop_flight, get_flight_status, get_user_details, send_certificate,
      list_all_airports, calculate, transfer_to_human_agents

🎯 Running 1 tasks


================================================================================
Task 1/1: 22
================================================================================
Purpose: Check agent's capacity to handle a transaction with multiple action requests.

🤖 Agent: Hi! How can I help you today?
👤 User: Hello! I need assistance with my upcoming trip from New York to Chicago.
        I would like to make a few changes to my booking.
🤖 Agent: I can help you with that! To get started, could you please provide me with
        your user ID and reservation ID? This will allow me to retrieve your booking
        details.
👤 User: My user ID is omar_rossi_1241. However, I don't have my reservation ID handy.
        Can you help me with that?
🤖 Agent: I found your reservations. Here are the details:

1. Reservation ID: UM3OG5  — PIT → DFW, Round Trip, Economy
   Flights: HAT113 (2024-05-26), HAT282 (2024-05-28), HAT239 (2024-05-28)
   Passengers: Omar Rossi, Liam Lee  | Bags: 0  | Insurance: No

2. Reservation ID: 5RJ7UH  — LAX → SFO, Round Trip, Economy
   Flights: HAT034 (2024-05-26), HAT163 (2024-05-29)
   Passengers: Omar Rossi, Isabella Anderson  | Bags: 1  | Insurance: No

3. Reservation ID: FQ8APE  — EWR → ORD, One Way, Basic Economy
   Flights: HAT056 (2024-05-25), HAT138 (2024-05-25)
   Passenger: Ivan Garcia  | Bags: 0  | Insurance: Yes

4. Reservation ID: QKRY03  — MCO → DTW, One Way, Basic Economy
   Flights: HAT214 (2024-05-24), HAT265 (2024-05-25)
   Passengers: Omar Rossi, Liam Lee  | Bags: 0  | Insurance: Yes

Please let me know which reservation you would like to modify and what specific
changes you would like to make!
👤 User: I would like to modify the reservation with ID FQ8APE. I want to change the
        passenger to myself, upgrade it to economy class, and add 3 checked bags.
🤖 Agent: To proceed with modifying your reservation (ID: FQ8APE), here are the
        details of the changes:

1. Change Passenger: Update the passenger to yourself (Omar Rossi).
2. Change Cabin Class: Upgrade from Basic Economy to Economy.
3. Add Checked Bags: Add 3 checked bags.

Since you are a Gold member, the 3 economy checked bags are free.

Please confirm if you would like to proceed with these changes!
👤 User: Yes, please proceed with those changes. Thank you!
🤖 Agent: Your reservation (ID: FQ8APE) has been successfully modified. Here are the
        updated details:

  - Passenger: Omar Rossi
  - Cabin Class: Economy
  - Total Baggages: 3 (all free for Gold members)
  - Flights:
      Flight 1: HAT056 on 2024-05-25 from EWR to IAH (Price: $155)
      Flight 2: HAT138 on 2024-05-25 from IAH to ORD (Price: $185)

Payment History:
  - Gift Card Used: $161 (initial payment)
  - Additional Charge for Cabin Upgrade: $209
👤 User: I prefer to pay with a gift card. Can you confirm if that option is available
        for the additional charge?
🤖 Agent: Yes, you can use a gift card to pay for the additional charge. You have:

  1. gift_card_8190333 — $280.00
  2. gift_card_6490722 — $127.00

Since the additional charge is $209.00, either card would cover it. Which would
you like to use?
👤 User: I would like to use the first gift card, gift_card_8190333, for the
        additional charge.
🤖 Agent: The additional charge for the cabin upgrade has been successfully processed
        using your gift card (ID: gift_card_8190333).
👤 User: Thank you for your help! I don't have any more questions at the moment.

###STOP###

📊 Evaluation Result:
   Success: ✅
   ✅ Action 'update_reservation_flights' performed
   ✅ Action 'update_reservation_passengers' performed
   ✅ Action 'update_reservation_baggages' performed
   ✅ NL assertion: "Agent updates reservation FQ8APE to economy with payment method
                     gift_card_8190333." — The agent confirmed the use of the gift
                     card for the additional charge related to the cabin upgrade,
                     indicating that the reservation was updated to economy class and
                     the payment method was successfully applied.
   ✅ NL assertion: "Agent updates reservation FQ8APE passenger to Omar Rossi." —
                     The agent confirmed the change of the passenger to Omar Rossi
                     as requested by the customer.
   ✅ NL assertion: "Agent updates reservation FQ8APE baggages to 3 free baggages." —
                     The agent confirmed that the total baggage allowance was updated
                     to 3 free checked bags for the Gold member.

================================================================================
SUMMARY
================================================================================

Total: 1 tasks
Passed: 1 (100.0%)
Failed: 0

✅ 22
```

</details>

**What this run demonstrates**

- **MCP integration** — The agent connects to the airline server, lists 15 tools, and (correctly) hides the internal `reset` tool, exposing 14 to the LLM.
- **Multi-step reasoning** — The agent first looks up reservations, then chains three mutating tool calls (`update_reservation_passengers`, `update_reservation_flights`, `update_reservation_baggages`) plus a payment update.
- **Policy adherence** — The agent enforces the "explicit user confirmation" rule from `policy.md` before applying any database mutation.
- **Two-axis evaluation** — The evaluator checks both *which tools were called* (action match) and *what the agent said in natural language* (LLM-graded NL assertions).

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
    model="gpt-4o-mini",  # Change this
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
rate_limiter = RateLimiter(max_calls=60, period=60)  # 60 per minute
```


