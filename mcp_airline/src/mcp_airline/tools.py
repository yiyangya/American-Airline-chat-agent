"""Tool registrations for the airline MCP server.

The goal of this module is to stay approachable for anyone extending the
codebase. The `register_tools` function is the single place where every tool is
declared. Each tool maps closely to an operation on the
``AirlineDatabase``—think of it as the contract between the MCP surface area and
your underlying data access layer.

When you add new behaviour, prefer creating small helper functions (similar to
``_search_direct_flight``) and keep the tool definitions focused on:

* validating parameters
* calling database helpers
* returning serialisable payloads (usually JSON strings)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Annotated, List
from typing import Any

from fastmcp import FastMCP

from .database import AirlineDatabase

__all__ = ["register_tools"]


def _search_direct_flight(
    db: AirlineDatabase,
    date: str,
    origin: str | None = None,
    destination: str | None = None,
    leave_after: str | None = None,
) -> List[dict]:
    """Internal helper to search for direct flights."""

    results: List[dict] = []
    db_state = db.get_state()

    for flight in db_state["flights"].values():
        matches_query = (
            (origin is None or flight["origin"] == origin)
            and (destination is None or flight["destination"] == destination)
            and (date in flight["dates"])
            and (flight["dates"][date]["status"] == "available")
            and (
                leave_after is None
                or flight["scheduled_departure_time_est"] >= leave_after
            )
        )

        if not matches_query:
            continue

        flight_date_data = flight["dates"][date]
        results.append(
            {
                "flight_number": flight["flight_number"],
                "origin": flight["origin"],
                "destination": flight["destination"],
                "status": "available",
                "scheduled_departure_time_est": flight["scheduled_departure_time_est"],
                "scheduled_arrival_time_est": flight["scheduled_arrival_time_est"],
                "available_seats": flight_date_data["available_seats"],
                "prices": flight_date_data["prices"],
            }
        )

    return results


def _payment_for_update(
    user: dict,
    payment_id: str,
    total_price: float,
) -> dict | None:
    """Process payment for a reservation update."""

    if payment_id not in user["payment_methods"]:
        raise ValueError("Payment method not found")

    payment_method = user["payment_methods"][payment_id]

    if payment_method["source"] == "certificate":
        raise ValueError("Certificate cannot be used to update reservation")

    if (
        payment_method["source"] == "gift_card"
        and payment_method["amount"] < total_price
    ):
        raise ValueError("Gift card balance is not enough")

    if payment_method["source"] == "gift_card":
        payment_method["amount"] -= total_price

    if total_price != 0:
        return {
            "payment_id": payment_id,
            "amount": total_price,
        }

    return None


def _parse_json_argument(raw_value: str, argument_name: str) -> Any:
    """Parse a JSON string and raise a friendly ``ValueError`` on failure."""

    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{argument_name} must be valid JSON") from exc


def register_tools(mcp: FastMCP, db: AirlineDatabase) -> None:
    """Register all airline tools with the MCP server."""

    # ------------------------------------------------------------------
    # Reservation lifecycle tools
    # ------------------------------------------------------------------
    @mcp.tool()
    def book_reservation(
        user_id: Annotated[
            str,
            "The ID of the user to book the reservation such as 'sara_doe_496'",
        ],
        origin: Annotated[
            str,
            "The IATA code for the origin city such as 'SFO'",
        ],
        destination: Annotated[
            str,
            "The IATA code for the destination city such as 'JFK'",
        ],
        flight_type: Annotated[
            str,
            "The type of flight such as 'one_way' or 'round_trip'",
        ],
        cabin: Annotated[
            str,
            "The cabin class such as 'basic_economy', 'economy', or 'business'",
        ],
        flights: Annotated[
            str,
            "JSON array of objects containing flight_number and date for each flight segment",
        ],
        passengers: Annotated[
            str,
            "JSON array of objects containing first_name, last_name, and dob for each passenger",
        ],
        payment_methods: Annotated[
            str,
            "JSON array of objects containing payment_id and amount for each payment",
        ],
        total_baggages: Annotated[
            int,
            "The total number of baggage items to book",
        ],
        nonfree_baggages: Annotated[
            int,
            "The number of non-free baggage items to book",
        ],
        insurance: Annotated[str, "Whether the reservation has insurance: 'yes' or 'no'"],
        user_confirmed: Annotated[
            bool,
            "Must be True. Indicates user has explicitly confirmed the booking details and total price before payment.",
        ] = False,
    ) -> str:
        """
        Create a brand-new reservation and record the full payment detail.
        
        POLICY ENFORCEMENT: Requires explicit user confirmation before processing payment.
        Agent must present booking details and total price to user and obtain confirmation first.
        """
        
        # Validate user confirmation requirement
        if not user_confirmed:
            raise ValueError(
                "Payment action requires explicit user confirmation. "
                "Present the booking details and total price to the user first, "
                "obtain their explicit confirmation, then call this tool with user_confirmed=True."
            )

        flights_list = _parse_json_argument(flights, "flights")
        if not isinstance(flights_list, list):
            raise ValueError("flights must be a JSON array")

        passengers_list = _parse_json_argument(passengers, "passengers")
        if not isinstance(passengers_list, list):
            raise ValueError("passengers must be a JSON array")

        payment_methods_list = _parse_json_argument(
            payment_methods,
            "payment_methods",
        )
        if not isinstance(payment_methods_list, list):
            raise ValueError("payment_methods must be a JSON array")

        user = db.get_user(user_id)
        reservation_id = db.get_new_reservation_id()
        db_state = db.get_state()

        reservation = {
            "reservation_id": reservation_id,
            "user_id": user_id,
            "origin": origin,
            "destination": destination,
            "flight_type": flight_type,
            "cabin": cabin,
            "flights": [],
            "passengers": json.loads(json.dumps(passengers_list)),
            "payment_history": json.loads(json.dumps(payment_methods_list)),
            "created_at": db.get_date_time(),
            "total_baggages": total_baggages,
            "nonfree_baggages": nonfree_baggages,
            "insurance": insurance,
        }

        total_price = 0.0
        all_flights_date_data = []

        for flight_info in flights_list:
            flight_number = flight_info["flight_number"]
            flight = db.get_flight(flight_number)
            flight_date_data = db.get_flight_instance(
                flight_number, flight_info["date"]
            )

            if flight_date_data["status"] != "available":
                raise ValueError(
                    f"Flight {flight_number} not available on date {flight_info['date']}"
                )

            if flight_date_data["available_seats"][cabin] < len(passengers_list):
                raise ValueError(f"Not enough seats on flight {flight_number}")

            price = flight_date_data["prices"][cabin]

            reservation["flights"].append(
                {
                    "origin": flight["origin"],
                    "destination": flight["destination"],
                    "flight_number": flight_number,
                    "date": flight_info["date"],
                    "price": price,
                }
            )

            all_flights_date_data.append(flight_date_data)
            total_price += price * len(passengers_list)

        if insurance == "yes":
            total_price += 30 * len(passengers_list)

        total_price += 50 * nonfree_baggages

        for payment_method in payment_methods_list:
            payment_id = payment_method["payment_id"]
            amount = payment_method["amount"]

            if payment_id not in user["payment_methods"]:
                raise ValueError(f"Payment method {payment_id} not found")

            user_payment_method = user["payment_methods"][payment_id]
            if user_payment_method["source"] in ["gift_card", "certificate"] and user_payment_method["amount"] < amount:
                raise ValueError(
                    f"Not enough balance in payment method {payment_id}"
                )

        total_payment = sum(p["amount"] for p in payment_methods_list)
        if total_payment != total_price:
            raise ValueError(
                "Payment amount does not add up, total price is"
                f" {total_price}, but paid {total_payment}"
            )

        for payment_method in payment_methods_list:
            payment_id = payment_method["payment_id"]
            amount = payment_method["amount"]
            user_payment_method = user["payment_methods"][payment_id]

            if user_payment_method["source"] == "gift_card":
                user_payment_method["amount"] -= amount
            elif user_payment_method["source"] == "certificate":
                del user["payment_methods"][payment_id]

        for flight_date_data in all_flights_date_data:
            flight_date_data["available_seats"][cabin] -= len(passengers_list)

        db_state["reservations"][reservation_id] = reservation
        user["reservations"].append(reservation_id)

        db.save()
        return json.dumps(reservation, indent=2)

    @mcp.tool()
    def cancel_reservation(
        reservation_id: Annotated[str, "The reservation ID, such as 'ZFA04Y'"],
        cancellation_reason: Annotated[
            str,
            "The reason for cancellation: 'change_of_plan', 'airline_cancelled_flight', or 'other'",
        ],
        booking_within_24hrs: Annotated[
            bool,
            "Whether the booking was made within the last 24 hours (checked by agent)",
        ] = False,
    ) -> str:
        """
        Cancel an existing reservation with policy validation.
        
        Policy rules enforced:
        1. Cannot cancel if any flight has been flown (flying/landed status)
        2. Can only cancel if: booking within 24hrs OR flight cancelled by airline OR 
           business flight OR (user has insurance AND reason covered by insurance)
        """

        reservation = db.get_reservation(reservation_id)
        
        # Validate cancellation reason
        valid_reasons = ["change_of_plan", "airline_cancelled_flight", "other"]
        if cancellation_reason not in valid_reasons:
            raise ValueError(
                f"Invalid cancellation_reason '{cancellation_reason}'. "
                f"Must be one of: {', '.join(valid_reasons)}"
            )
        
        # Check if any portion of the flight has already been flown
        db_state = db.get_state()
        for flight_info in reservation["flights"]:
            flight_instance = db.get_flight_instance(
                flight_info["flight_number"], flight_info["date"]
            )
            flight_status = flight_instance.get("status")
            if flight_status in ["flying", "landed"]:
                raise ValueError(
                    f"Cannot cancel reservation {reservation_id}: "
                    f"Flight {flight_info['flight_number']} on {flight_info['date']} "
                    f"has status '{flight_status}'. Transfer to human agent required."
                )
        
        # Check if flight is cancelled by airline
        has_airline_cancelled_flight = False
        for flight_info in reservation["flights"]:
            flight_instance = db.get_flight_instance(
                flight_info["flight_number"], flight_info["date"]
            )
            if flight_instance.get("status") == "cancelled":
                has_airline_cancelled_flight = True
                break
        
        # Get user to check membership and insurance
        user = db.get_user(reservation["user_id"])
        
        # Validate cancellation eligibility according to policy
        # Can cancel if ANY of the following is true:
        can_cancel = (
            booking_within_24hrs  # Booking made within last 24 hours
            or has_airline_cancelled_flight  # Flight cancelled by airline
            or reservation["cabin"] == "business"  # Business flight
            or (
                reservation["insurance"] == "yes"
                and cancellation_reason == "change_of_plan"
                # Insurance covers change of plan (and airline cancellation is always allowed)
            )
        )
        
        if not can_cancel:
            raise ValueError(
                f"Cannot cancel reservation {reservation_id}: Policy violation. "
                f"Cancellation requires one of: "
                f"booking within 24hrs (got {booking_within_24hrs}), "
                f"airline cancelled flight (got {has_airline_cancelled_flight}), "
                f"business cabin (got {reservation['cabin']}), or "
                f"insurance covering reason (insurance={reservation['insurance']}, "
                f"reason={cancellation_reason}). "
                f"Transfer to human agent may be required."
            )

        # All validations passed - proceed with cancellation
        refunds = [
            {
                "payment_id": payment["payment_id"],
                "amount": -payment["amount"],
            }
            for payment in reservation["payment_history"]
        ]

        reservation["payment_history"].extend(refunds)
        reservation["status"] = "cancelled"

        print("⚠️  Seats release not implemented for cancellation", flush=True)

        db.save()
        return json.dumps(reservation, indent=2)

    @mcp.tool()
    def get_reservation_details(
        reservation_id: Annotated[str, "The reservation ID, such as '8JX2WO'"],
    ) -> str:
        """Return the reservation payload so MCP clients can render it."""

        reservation = db.get_reservation(reservation_id)
        return json.dumps(reservation, indent=2)

    @mcp.tool()
    def update_reservation_baggages(
        reservation_id: Annotated[str, "The reservation ID, such as 'ZFA04Y'"],
        total_baggages: Annotated[int, "The updated total number of baggage items"],
        nonfree_baggages: Annotated[
            int, "The updated number of non-free baggage items"
        ],
        payment_id: Annotated[
            str,
            "The payment id stored in user profile, such as 'credit_card_7815826'",
        ],
        user_confirmed: Annotated[
            bool,
            "Must be True. Indicates user has explicitly confirmed the baggage update and additional charge before payment.",
        ] = False,
    ) -> str:
        """
        Adjust baggage counts while collecting any additional payment.
        
        POLICY ENFORCEMENT: Requires explicit user confirmation before processing payment.
        Agent must calculate and present the additional charge to user and obtain confirmation first.
        """
        
        # Validate user confirmation requirement
        if not user_confirmed:
            raise ValueError(
                "Payment action requires explicit user confirmation. "
                "Calculate and present the additional baggage charge to the user first, "
                "obtain their explicit confirmation, then call this tool with user_confirmed=True."
            )

        reservation = db.get_reservation(reservation_id)
        user = db.get_user(reservation["user_id"])

        total_price = 50 * max(0, nonfree_baggages - reservation["nonfree_baggages"])

        payment = _payment_for_update(user, payment_id, total_price)
        if payment is not None:
            reservation["payment_history"].append(payment)

        reservation["total_baggages"] = total_baggages
        reservation["nonfree_baggages"] = nonfree_baggages

        db.save()
        return json.dumps(reservation, indent=2)

    @mcp.tool()
    def update_reservation_flights(
        reservation_id: Annotated[str, "The reservation ID, such as 'ZFA04Y'"],
        cabin: Annotated[
            str,
            "The cabin class: 'basic_economy', 'economy', or 'business'",
        ],
        flights: Annotated[
            str,
            "JSON array of flight info objects with flight_number and date for ALL flights in reservation",
        ],
        payment_id: Annotated[
            str,
            "The payment id stored in user profile, such as 'credit_card_7815826'",
        ],
        user_confirmed: Annotated[
            bool,
            "Must be True. Indicates user has explicitly confirmed the flight changes and fare difference before payment.",
        ] = False,
    ) -> str:
        """
        Swap flights in a reservation, charging the fare difference.
        
        POLICY ENFORCEMENT: Requires explicit user confirmation before processing payment.
        Agent must calculate and present the fare difference to user and obtain confirmation first.
        """
        
        # Validate user confirmation requirement
        if not user_confirmed:
            raise ValueError(
                "Payment action requires explicit user confirmation. "
                "Calculate and present the fare difference to the user first, "
                "obtain their explicit confirmation, then call this tool with user_confirmed=True."
            )

        flights_list = _parse_json_argument(flights, "flights")
        if not isinstance(flights_list, list):
            raise ValueError("flights must be a JSON array")

        reservation = db.get_reservation(reservation_id)
        user = db.get_user(reservation["user_id"])

        total_price = 0.0
        reservation_flights = []

        for flight_info in flights_list:
            matching_flight = next(
                (
                    rf
                    for rf in reservation["flights"]
                    if rf["flight_number"] == flight_info["flight_number"]
                    and rf["date"] == flight_info["date"]
                    and cabin == reservation["cabin"]
                ),
                None,
            )

            if matching_flight:
                total_price += matching_flight["price"] * len(
                    reservation["passengers"]
                )
                reservation_flights.append(matching_flight)
                continue

            flight = db.get_flight(flight_info["flight_number"])
            flight_date_data = db.get_flight_instance(
                flight_info["flight_number"], flight_info["date"]
            )

            if flight_date_data["status"] != "available":
                raise ValueError(
                    f"Flight {flight_info['flight_number']} not available on date {flight_info['date']}"
                )

            if flight_date_data["available_seats"][cabin] < len(reservation["passengers"]):
                raise ValueError(
                    f"Not enough seats on flight {flight_info['flight_number']}"
                )

            reservation_flight = {
                "flight_number": flight_info["flight_number"],
                "date": flight_info["date"],
                "price": flight_date_data["prices"][cabin],
                "origin": flight["origin"],
                "destination": flight["destination"],
            }
            total_price += reservation_flight["price"] * len(
                reservation["passengers"]
            )
            reservation_flights.append(reservation_flight)

        original_price = (
            sum(f["price"] for f in reservation["flights"])
            * len(reservation["passengers"])
        )
        total_price -= original_price

        payment = _payment_for_update(user, payment_id, total_price)
        if payment is not None:
            reservation["payment_history"].append(payment)

        reservation["flights"] = reservation_flights
        reservation["cabin"] = cabin

        db.save()
        return json.dumps(reservation, indent=2)

    @mcp.tool()
    def update_reservation_passengers(
        reservation_id: Annotated[str, "The reservation ID, such as 'ZFA04Y'"],
        passengers: Annotated[
            str,
            "JSON array of objects containing first_name, last_name, and dob for each passenger",
        ],
    ) -> str:
        """Update passenger information while preserving passenger count."""

        passengers_list = _parse_json_argument(passengers, "passengers")
        if not isinstance(passengers_list, list):
            raise ValueError("passengers must be a JSON array")

        reservation = db.get_reservation(reservation_id)

        if len(passengers_list) != len(reservation["passengers"]):
            raise ValueError("Number of passengers does not match")

        reservation["passengers"] = json.loads(json.dumps(passengers_list))

        db.save()
        return json.dumps(reservation, indent=2)

    # ------------------------------------------------------------------
    # Flight search and status tools
    # ------------------------------------------------------------------
    @mcp.tool()
    def search_direct_flight(
        origin: Annotated[
            str, "The origin city airport in three letters, such as 'JFK'"
        ],
        destination: Annotated[
            str, "The destination city airport in three letters, such as 'LAX'"
        ],
        date: Annotated[
            str,
            "The date of the flight in the format 'YYYY-MM-DD', such as '2024-01-01'",
        ],
    ) -> str:
        """Search same-day direct flights that have available seats."""

        results = _search_direct_flight(db, date, origin, destination)
        return json.dumps(results, indent=2)

    @mcp.tool()
    def search_onestop_flight(
        origin: Annotated[
            str, "The origin city airport in three letters, such as 'JFK'"
        ],
        destination: Annotated[
            str, "The destination city airport in three letters, such as 'LAX'"
        ],
        date: Annotated[
            str,
            "The date of the flight in the format 'YYYY-MM-DD', such as '2024-05-01'",
        ],
    ) -> str:
        """Find itineraries with a single connection, including next-day legs."""

        results = []

        for first_leg in _search_direct_flight(db, date, origin, None):
            first_leg["date"] = date

            has_next_day = "+1" in first_leg["scheduled_arrival_time_est"]

            date_obj = datetime.strptime(date, "%Y-%m-%d")
            if has_next_day:
                date_obj += timedelta(days=1)
            date2 = date_obj.strftime("%Y-%m-%d")

            for second_leg in _search_direct_flight(
                db,
                date2,
                first_leg["destination"],
                destination,
                first_leg["scheduled_arrival_time_est"],
            ):
                second_leg["date"] = date2
                results.append([first_leg, second_leg])

        return json.dumps(results, indent=2)

    @mcp.tool()
    def get_flight_status(
        flight_number: Annotated[str, "The flight number"],
        date: Annotated[str, "The date of the flight"],
    ) -> str:
        """Return the operational status string for a specific flight instance."""

        flight_instance = db.get_flight_instance(flight_number, date)
        return flight_instance["status"]

    # ------------------------------------------------------------------
    # User profile and utility helpers
    # ------------------------------------------------------------------
    @mcp.tool()
    def get_user_details(
        user_id: Annotated[str, "The user ID, such as 'sara_doe_496'"],
    ) -> str:
        """Fetch user contact info, payment methods, and reservation IDs."""

        user = db.get_user(user_id)
        return json.dumps(user, indent=2)

    @mcp.tool()
    def send_certificate(
        user_id: Annotated[str, "The ID of the user, such as 'sara_doe_496'"],
        amount: Annotated[float, "The amount of the certificate to send"],
        reservation_id: Annotated[
            str,
            "The reservation ID for which compensation is being issued, such as 'ZFA04Y'",
        ],
        event_type: Annotated[
            str,
            "The event type: 'cancelled' for cancelled flights or 'delayed' for delayed flights",
        ],
        facts_confirmed: Annotated[
            bool,
            "Whether the agent has confirmed the facts about the event before offering compensation",
        ] = False,
    ) -> str:
        """
        Grant the user a certificate payment method with validation.
        
        This tool validates that:
        1. Compensation is only for policy-allowed events (cancelled or delayed flights)
        2. User is eligible (silver/gold member OR has insurance OR flies business)
        3. Amount matches policy ($100/passenger for cancelled, $50/passenger for delayed)
        4. Facts have been confirmed
        5. No double compensation for the same reservation
        """

        # Get user and reservation
        user = db.get_user(user_id)
        reservation = db.get_reservation(reservation_id)
        
        # Validate reservation belongs to user
        if reservation["user_id"] != user_id:
            raise ValueError(
                f"Reservation {reservation_id} does not belong to user {user_id}"
            )
        
        # Check if compensation already issued for this reservation
        if "compensation_issued" in reservation:
            raise ValueError(
                f"Compensation has already been issued for reservation {reservation_id}. "
                f"Only one compensation per reservation is allowed."
            )
        
        # Validate facts are confirmed
        if not facts_confirmed:
            raise ValueError(
                "Facts must be confirmed before offering compensation. "
                "Set facts_confirmed=True after verifying the event details."
            )
        
        # Validate event type
        if event_type not in ["cancelled", "delayed"]:
            raise ValueError(
                f"Invalid event_type '{event_type}'. Must be 'cancelled' or 'delayed'."
            )
        
        # Check user eligibility: silver/gold member OR has insurance OR flies business
        is_eligible = (
            user["membership"] in ["silver", "gold"]
            or reservation["insurance"] == "yes"
            or reservation["cabin"] == "business"
        )
        
        if not is_eligible:
            raise ValueError(
                "User is not eligible for compensation. Policy requires: "
                "silver/gold member OR travel insurance OR business cabin. "
                f"Current: membership={user['membership']}, "
                f"insurance={reservation['insurance']}, cabin={reservation['cabin']}"
            )
        
        # Validate event matches reservation status
        num_passengers = len(reservation["passengers"])
        
        if event_type == "cancelled":
            # Check if any flight in reservation is cancelled
            db_state = db.get_state()
            has_cancelled_flight = False
            for flight_info in reservation["flights"]:
                flight_instance = db.get_flight_instance(
                    flight_info["flight_number"], flight_info["date"]
                )
                if flight_instance.get("status") == "cancelled":
                    has_cancelled_flight = True
                    break
            
            if not has_cancelled_flight:
                raise ValueError(
                    "Cannot compensate for cancelled flights: "
                    "No cancelled flights found in this reservation."
                )
            
            # Validate amount: $100 per passenger
            expected_amount = 100.0 * num_passengers
            if abs(amount - expected_amount) > 0.01:  # Allow small floating point differences
                raise ValueError(
                    f"Invalid compensation amount for cancelled flights. "
                    f"Expected ${expected_amount:.2f} ($100 × {num_passengers} passengers), "
                    f"but got ${amount:.2f}"
                )
        
        elif event_type == "delayed":
            # Check if any flight in reservation is delayed
            db_state = db.get_state()
            has_delayed_flight = False
            for flight_info in reservation["flights"]:
                flight_instance = db.get_flight_instance(
                    flight_info["flight_number"], flight_info["date"]
                )
                if flight_instance.get("status") == "delayed":
                    has_delayed_flight = True
                    break
            
            if not has_delayed_flight:
                raise ValueError(
                    "Cannot compensate for delayed flights: "
                    "No delayed flights found in this reservation."
                )
            
            # Validate amount: $50 per passenger
            expected_amount = 50.0 * num_passengers
            if abs(amount - expected_amount) > 0.01:
                raise ValueError(
                    f"Invalid compensation amount for delayed flights. "
                    f"Expected ${expected_amount:.2f} ($50 × {num_passengers} passengers), "
                    f"but got ${amount:.2f}"
                )
        
        # All validations passed - issue certificate
        payment_ids = db.get_new_payment_ids()
        
        for payment_id_num in payment_ids:
            payment_id = f"certificate_{payment_id_num}"
            
            if payment_id not in user["payment_methods"]:
                new_payment = {
                    "id": payment_id,
                    "amount": amount,
                    "source": "certificate",
                }
                user["payment_methods"][payment_id] = new_payment
                
                # Mark compensation as issued in reservation to prevent double-compensation
                reservation["compensation_issued"] = {
                    "event_type": event_type,
                    "amount": amount,
                    "payment_id": payment_id,
                    "issued_at": db.get_date_time(),
                }

                db.save()
                return (
                    f"Certificate {payment_id} added to user {user_id} with amount "
                    f"${amount:.2f} for reservation {reservation_id} "
                    f"(event: {event_type})."
                )
        
        raise ValueError("Too many certificates")

    @mcp.tool()
    def list_all_airports() -> str:
        """Return a curated list of airports useful for demo prompts."""

        airports = [
            {"iata": "SFO", "city": "San Francisco"},
            {"iata": "JFK", "city": "New York"},
            {"iata": "LAX", "city": "Los Angeles"},
            {"iata": "ORD", "city": "Chicago"},
            {"iata": "DFW", "city": "Dallas"},
            {"iata": "DEN", "city": "Denver"},
            {"iata": "PIT", "city": "Pittsburgh"},
            {"iata": "ATL", "city": "Atlanta"},
            {"iata": "MIA", "city": "Miami"},
            {"iata": "BOS", "city": "Boston"},
            {"iata": "PHX", "city": "Phoenix"},
            {"iata": "IAH", "city": "Houston"},
            {"iata": "LAS", "city": "Las Vegas"},
            {"iata": "MCO", "city": "Orlando"},
            {"iata": "EWR", "city": "Newark"},
            {"iata": "CLT", "city": "Charlotte"},
            {"iata": "MSP", "city": "Minneapolis"},
            {"iata": "DTW", "city": "Detroit"},
            {"iata": "PHL", "city": "Philadelphia"},
            {"iata": "LGA", "city": "LaGuardia"},
        ]
        return json.dumps(airports, indent=2)

    @mcp.tool()
    def calculate(
        expression: Annotated[
            str,
            "Mathematical expression like '2 + 2' with numbers and operators (+, -, *, /)",
        ],
    ) -> str:
        """Evaluate simple arithmetic—handy for lightweight agent tasks."""

        try:
            allowed_names = {"__builtins__": {}}
            result = eval(expression, allowed_names)
            return str(round(result, 2))
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid expression") from exc

    @mcp.tool()
    def transfer_to_human_agents(
        summary: Annotated[str, "A summary of the user's issue"],
    ) -> str:
        """Placeholder utility so agents can gracefully escalate."""

        return "Transfer successful"