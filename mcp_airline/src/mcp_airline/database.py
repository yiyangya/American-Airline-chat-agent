"""Airline database management."""

import json
import logging
import os
import random
import string
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


def _persist_enabled() -> bool:
    """Read the AIRLINE_PERSIST_DB env var; defaults to enabled."""
    return os.getenv("AIRLINE_PERSIST_DB", "1").lower() not in ("0", "false", "no", "")


class AirlineDatabase:
    """
    Airline database manager for flights, users, and reservations.

    Provides methods to load and query airline data including users,
    flights, and reservations.
    """

    def __init__(
        self,
        db_path: Path | str,
        seed_path: Path | str | None = None,
        persist: bool | None = None,
    ):
        """
        Initialize database from a JSON file.

        Args:
            db_path: Path to the working database JSON file. Mutations from
                tools are written back here when persistence is enabled.
            seed_path: Path to the immutable seed snapshot used by ``reload()``
                to restore the initial state. Defaults to ``db.seed.json``
                sitting next to ``db_path``.
            persist: Whether mutations should be written back to ``db_path``.
                When ``None`` (default), reads ``AIRLINE_PERSIST_DB`` from the
                environment (enabled unless explicitly set to a falsy value).

        Raises:
            ValueError: If database file cannot be loaded or is invalid
        """
        self._db_path = Path(db_path)
        self._seed_path = (
            Path(seed_path) if seed_path is not None
            else self._db_path.with_name("db.seed.json")
        )
        self._persist = _persist_enabled() if persist is None else persist
        # On first run, promote the existing db.json to the seed snapshot so
        # subsequent resets have a baseline to restore from.
        self._ensure_seed()
        self._data = self._load_data()

    def _ensure_seed(self) -> None:
        """Create ``db.seed.json`` from ``db.json`` if it doesn't yet exist."""
        if self._seed_path.exists():
            return
        if self._db_path.exists():
            self._seed_path.write_bytes(self._db_path.read_bytes())
            logger.info("Created seed snapshot at %s", self._seed_path)

    @classmethod
    def from_tau2_bench(cls, base_path: Optional[Path] = None) -> "AirlineDatabase":
        """
        Create database from tau2-bench data directory.

        Args:
            base_path: Base path to data directory. If None, uses relative path.

        Returns:
            Initialized AirlineDatabase instance

        Raises:
            ValueError: If tau2-bench data cannot be found
        """
        if base_path is None:
            # Navigate from src/mcp_airline/ up to the repository root, then
            # into the top-level ``data`` directory shared by all domains.
            base_path = Path(__file__).parent.parent.parent.parent / "data"

        db_path = base_path / "airline" / "db.json"
        seed_path = base_path / "airline" / "db.seed.json"
        if not db_path.exists() and not seed_path.exists():
            raise ValueError(f"Database not found at {db_path}")
        # If only the seed exists (fresh checkout after someone gitignored the
        # working copy), bootstrap ``db.json`` from it so tools have a target
        # to persist into.
        if not db_path.exists() and seed_path.exists():
            db_path.write_bytes(seed_path.read_bytes())

        return cls(db_path, seed_path=seed_path)

    def _load_data(self) -> dict:
        """
        Load and validate database from file.

        Returns:
            Parsed database dictionary

        Raises:
            ValueError: If file cannot be read or structure is invalid
        """
        try:
            with self._db_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate structure
            if not all(key in data for key in ['flights', 'users', 'reservations']):
                raise ValueError(
                    "Invalid database structure: missing flights, users, or reservations"
                )

            logger.info("Loaded airline database from: %s", self._db_path)
            return data

        except FileNotFoundError:
            raise ValueError(f"Database file not found: {self._db_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in database file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load airline data: {e}")

    def get_user(self, user_id: str) -> dict:
        """
        Get user by ID.

        Args:
            user_id: The user ID to look up

        Returns:
            User data dictionary

        Raises:
            ValueError: If user not found
        """
        if user_id not in self._data['users']:
            raise ValueError(f"User {user_id} not found")
        return self._data['users'][user_id]

    def get_reservation(self, reservation_id: str) -> dict:
        """
        Get reservation by ID.

        Args:
            reservation_id: The reservation ID to look up

        Returns:
            Reservation data dictionary

        Raises:
            ValueError: If reservation not found
        """
        if reservation_id not in self._data['reservations']:
            raise ValueError(f"Reservation {reservation_id} not found")
        return self._data['reservations'][reservation_id]

    def get_flight(self, flight_number: str) -> dict:
        """
        Get flight by flight number.

        Args:
            flight_number: The flight number to look up

        Returns:
            Flight data dictionary

        Raises:
            ValueError: If flight not found
        """
        if flight_number not in self._data['flights']:
            raise ValueError(f"Flight {flight_number} not found")
        return self._data['flights'][flight_number]

    def get_flight_instance(self, flight_number: str, date: str) -> dict:
        """
        Get specific flight instance for a date.

        Args:
            flight_number: The flight number
            date: The date in YYYY-MM-DD format

        Returns:
            Flight date status dictionary

        Raises:
            ValueError: If flight or date not found
        """
        flight = self.get_flight(flight_number)
        if date not in flight['dates']:
            raise ValueError(f"Flight {flight_number} not found on date {date}")
        return flight['dates'][date]

    def get_new_reservation_id(self) -> str:
        """
        Generate a unique 6-character alphanumeric reservation ID.

        Returns:
            New unique reservation ID

        Raises:
            ValueError: If unable to generate unique ID after max attempts
        """
        chars = string.ascii_uppercase + string.digits
        max_attempts = 100

        for _ in range(max_attempts):
            reservation_id = ''.join(random.choices(chars, k=6))
            if reservation_id not in self._data['reservations']:
                return reservation_id

        raise ValueError("Failed to generate unique reservation ID after multiple attempts")

    def get_new_payment_id(self) -> int:
        """
        Generate a 7-digit payment ID.

        Returns:
            New payment ID as integer
        """
        return random.randint(1000000, 9999999)

    def get_new_payment_ids(self, count: int = 3) -> list[int]:
        """
        Generate multiple payment IDs.

        Args:
            count: Number of IDs to generate

        Returns:
            List of payment IDs
        """
        return [self.get_new_payment_id() for _ in range(count)]

    def get_date_time(self) -> str:
        """
        Get current datetime for the simulation.

        Returns:
            Fixed datetime string for tau2-bench compatibility
        """
        return "2024-05-15T15:00:00"

    def get_state(self) -> dict:
        """
        Get the entire database state.

        Returns:
            Complete database dictionary
        """
        return self._data

    def save(self) -> None:
        """Atomically persist the in-memory state to the working database file.

        Writing to a temp file and renaming avoids leaving a half-written
        ``db.json`` on disk if the process crashes mid-write. Does nothing when
        persistence is disabled (e.g. during benchmark runs that need a
        pristine baseline).

        Raises:
            OSError: If the temp write or rename fails.
        """
        if not self._persist:
            return
        tmp_path = self._db_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp_path, self._db_path)

    def reload(self) -> None:
        """
        Reset database to the seed snapshot.

        Restores both in-memory state and (when persistence is enabled) the
        on-disk working copy, so subsequent reads see a clean baseline
        regardless of prior mutations.

        Raises:
            ValueError: If neither the seed nor the working database file can
                be read.
        """
        if self._seed_path.exists():
            if self._persist:
                self._db_path.write_bytes(self._seed_path.read_bytes())
            with self._seed_path.open("r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info("Reloaded airline database from seed: %s", self._seed_path)
        else:
            # No seed to restore from — fall back to re-reading the working
            # copy (matches the pre-persistence behaviour).
            self._data = self._load_data()
