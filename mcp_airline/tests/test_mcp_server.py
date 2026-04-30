"""Test MCP server tools via MCP client connection over HTTP."""

import asyncio
import pytest
import pytest_asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# Default server URL - can be overridden with environment variable
SERVER_URL = "http://localhost:3000/mcp"


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    """Reset the database before each test."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Call reset tool to restore database to initial state
            await session.call_tool("reset", {})
    yield


@pytest.mark.asyncio
async def test_reset_database():
    """Test that the reset tool properly restores database state."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # Get initial reservation state
            result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})
            original_reservation = json.loads(result.content[0].text)
            assert "status" not in original_reservation or original_reservation.get("status") != "cancelled"

            # Cancel the reservation
            await session.call_tool("cancel_reservation", {"reservation_id": "4WQ150"})

            # Verify it's cancelled
            result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})
            cancelled_reservation = json.loads(result.content[0].text)
            assert cancelled_reservation["status"] == "cancelled"

            # Call reset
            reset_result = await session.call_tool("reset", {})
            assert reset_result.content[0].text == "true"

            # Verify the reservation is back to original state
            result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})
            restored_reservation = json.loads(result.content[0].text)
            assert "status" not in restored_reservation or restored_reservation.get("status") != "cancelled"
            # Payment history should be back to original length
            assert len(restored_reservation["payment_history"]) == len(original_reservation["payment_history"])


@pytest.mark.asyncio
async def test_list_tools():
    """Test that we can connect and list available tools."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()

            # List all tools
            tools = await session.list_tools()

            # Verify we have tools
            assert len(tools.tools) > 0

            # Check for expected tools
            tool_names = [tool.name for tool in tools.tools]
            assert "list_all_airports" in tool_names
            assert "calculate" in tool_names
            # assert "reset" in tool_names


@pytest.mark.asyncio
async def test_list_all_airports():
    """Test calling list_all_airports tool."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the tool
            result = await session.call_tool("list_all_airports", {})

            # Verify result
            assert len(result.content) > 0
            assert result.content[0].type == "text"

            # Parse and verify the airport data
            import json
            airports = json.loads(result.content[0].text)
            assert isinstance(airports, list)
            assert len(airports) > 0
            assert "iata" in airports[0]
            assert "city" in airports[0]


@pytest.mark.asyncio
async def test_calculate():
    """Test calling calculate tool."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the tool
            result = await session.call_tool("calculate", {"expression": "2 + 2"})

            # Verify result
            assert len(result.content) > 0
            assert result.content[0].type == "text"
            assert result.content[0].text == "4"


@pytest.mark.asyncio
async def test_get_user_details():
    """Test calling get_user_details tool with valid user."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the tool with a valid user ID
            result = await session.call_tool("get_user_details", {"user_id": "mia_li_3668"})

            # Verify result
            assert len(result.content) > 0
            assert result.content[0].type == "text"

            # Parse and verify the user data
            import json
            user_data = json.loads(result.content[0].text)
            assert user_data["user_id"] == "mia_li_3668"
            assert user_data["name"]["first_name"] == "Mia"
            assert user_data["name"]["last_name"] == "Li"
            assert "payment_methods" in user_data
            assert "reservations" in user_data


@pytest.mark.asyncio
async def test_get_user_details_invalid():
    """Test calling get_user_details tool with invalid user returns error."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Call the tool with an invalid user ID
            result = await session.call_tool("get_user_details", {"user_id": "invalid_user"})

            # Verify we get an error response
            assert len(result.content) > 0
            assert result.content[0].type == "text"
            assert "not found" in result.content[0].text.lower() or "error" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_get_reservation_details():
    """Test getting reservation details."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # Get details for an existing reservation
            result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})

            assert len(result.content) > 0
            assert result.content[0].type == "text"

            reservation = json.loads(result.content[0].text)
            assert reservation["reservation_id"] == "4WQ150"
            assert "user_id" in reservation
            assert "flights" in reservation
            assert "passengers" in reservation


@pytest.mark.asyncio
async def test_search_direct_flight():
    """Test searching for direct flights."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # Search for flights from PHL to LGA on 2024-05-16
            result = await session.call_tool(
                "search_direct_flight",
                {"origin": "PHL", "destination": "LGA", "date": "2024-05-16"}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"

            flights = json.loads(result.content[0].text)
            assert isinstance(flights, list)
            # Should find at least one flight
            if len(flights) > 0:
                flight = flights[0]
                assert flight["origin"] == "PHL"
                assert flight["destination"] == "LGA"
                assert "flight_number" in flight
                assert "prices" in flight
                assert "available_seats" in flight


@pytest.mark.asyncio
async def test_search_onestop_flight():
    """Test searching for one-stop flights."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # Search for one-stop flights
            result = await session.call_tool(
                "search_onestop_flight",
                {"origin": "SFO", "destination": "JFK", "date": "2024-05-20"}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"

            flight_pairs = json.loads(result.content[0].text)
            assert isinstance(flight_pairs, list)
            # Each result should be a pair of flights
            if len(flight_pairs) > 0:
                pair = flight_pairs[0]
                assert len(pair) == 2
                assert pair[0]["destination"] == pair[1]["origin"]


@pytest.mark.asyncio
async def test_get_flight_status():
    """Test getting flight status."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Get status for a landed flight
            result = await session.call_tool(
                "get_flight_status",
                {"flight_number": "HAT001", "date": "2024-05-01"}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"
            assert result.content[0].text == "landed"

            # Get status for an available flight
            result2 = await session.call_tool(
                "get_flight_status",
                {"flight_number": "HAT001", "date": "2024-05-16"}
            )

            assert len(result2.content) > 0
            assert result2.content[0].type == "text"
            assert result2.content[0].text == "available"


@pytest.mark.asyncio
async def test_send_certificate():
    """Test sending a certificate to a user."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # Get the user before
            user_before = await session.call_tool("get_user_details", {"user_id": "mia_li_3668"})
            user_data_before = json.loads(user_before.content[0].text)
            cert_count_before = sum(1 for pm in user_data_before["payment_methods"].values()
                                   if pm.get("source") == "certificate")

            # Send a certificate to a user
            result = await session.call_tool(
                "send_certificate",
                {"user_id": "mia_li_3668", "amount": 100.0}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"
            assert "certificate" in result.content[0].text.lower()
            assert "mia_li_3668" in result.content[0].text

            # Verify the certificate was added
            user_after = await session.call_tool("get_user_details", {"user_id": "mia_li_3668"})
            user_data_after = json.loads(user_after.content[0].text)
            cert_count_after = sum(1 for pm in user_data_after["payment_methods"].values()
                                  if pm.get("source") == "certificate")
            assert cert_count_after == cert_count_before + 1


@pytest.mark.asyncio
async def test_transfer_to_human_agents():
    """Test transfer to human agents."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "transfer_to_human_agents",
                {"summary": "Customer needs help with complex itinerary"}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"
            assert "transfer" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_cancel_reservation():
    """Test canceling a reservation."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # First get the reservation details
            result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})
            original = json.loads(result.content[0].text)

            # Cancel the reservation
            result = await session.call_tool("cancel_reservation", {"reservation_id": "4WQ150"})

            assert len(result.content) > 0
            assert result.content[0].type == "text"

            reservation = json.loads(result.content[0].text)
            assert reservation["reservation_id"] == "4WQ150"
            assert reservation["status"] == "cancelled"
            # Should have refund entries
            assert len(reservation["payment_history"]) > len(original["payment_history"])


@pytest.mark.asyncio
async def test_update_reservation_passengers():
    """Test updating reservation passengers."""
    async with streamablehttp_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            import json

            # First get the reservation to see how many passengers it has
            res_result = await session.call_tool("get_reservation_details", {"reservation_id": "4WQ150"})
            res_data = json.loads(res_result.content[0].text)
            num_passengers = len(res_data["passengers"])

            # Update passengers for the reservation (must match original passenger count)
            passengers_list = [
                {"first_name": f"Passenger{i}", "last_name": f"Test{i}", "dob": "1990-01-01"}
                for i in range(num_passengers)
            ]

            # Python server expects JSON string, TypeScript expects array
            # Send as array directly (TypeScript format)
            result = await session.call_tool(
                "update_reservation_passengers",
                {"reservation_id": "4WQ150", "passengers": passengers_list}
            )

            assert len(result.content) > 0
            assert result.content[0].type == "text"

            reservation = json.loads(result.content[0].text)
            assert len(reservation["passengers"]) == num_passengers
            assert reservation["passengers"][0]["first_name"] == "Passenger0"
