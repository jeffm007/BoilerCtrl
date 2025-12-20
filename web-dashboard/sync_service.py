"""
Sync Service for NAS Web Dashboard
Syncs event_log data from Pi backend to local NAS database
"""

import logging
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx

from database import get_connection

logger = logging.getLogger(__name__)


class SyncService:
    """Manages synchronization of event_log data from Pi to NAS database."""

    def __init__(self, pi_http_url: str):
        self.pi_http_url = pi_http_url
        self.sync_endpoint = f"{pi_http_url}/api/sync/events"

    def get_last_synced_id(self) -> Optional[int]:
        """Get the highest event ID we've synced so far."""
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT MAX(Id) as max_id FROM EventLog")
                row = cursor.fetchone()
                return row["max_id"] if row and row["max_id"] is not None else None
        except sqlite3.Error as e:
            logger.error(f"Error getting last synced ID: {e}")
            return None

    def store_events(self, events: List[Dict[str, Any]]) -> int:
        """
        Store synced events in local database.
        Returns count of events inserted/updated.
        """
        if not events:
            return 0

        count = 0
        try:
            with get_connection() as conn:
                for event in events:
                    # Insert or replace to handle updates
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO EventLog (
                            Id, Timestamp, Source, Event,
                            ZoneRoomTemp_F, PipeTemp_F, OutsideTemp_F, DurationSeconds
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.get("Id"),
                            event.get("Timestamp"),
                            event.get("Source"),
                            event.get("Event"),
                            event.get("ZoneRoomTemp_F"),
                            event.get("PipeTemp_F"),
                            event.get("OutsideTemp_F"),
                            event.get("DurationSeconds"),
                        )
                    )
                    count += 1
                conn.commit()
                logger.info(f"Stored {count} events in local database")
        except sqlite3.Error as e:
            logger.error(f"Error storing events: {e}")

        return count

    async def sync_from_pi(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Fetch new events from Pi and store them locally.
        Returns dict with sync statistics.
        """
        last_id = self.get_last_synced_id()

        try:
            params = {}
            if last_id is not None:
                params["since_id"] = last_id
                logger.info(f"Syncing events since ID {last_id}")
            else:
                logger.info("Performing initial sync (last 7 days)")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.sync_endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                events = data.get("events", [])  # Pi returns {"events": [...], "count": N}

            if not events:
                logger.info("No new events to sync")
                return {
                    "success": True,
                    "events_fetched": 0,
                    "events_stored": 0,
                    "last_synced_id": last_id,
                }

            # Store events
            stored_count = self.store_events(events)
            new_last_id = events[-1].get("Id") if events else last_id  # Capital I for Id

            logger.info(f"Sync completed: fetched {len(events)}, stored {stored_count}, last_id: {new_last_id}")

            return {
                "success": True,
                "events_fetched": len(events),
                "events_stored": stored_count,
                "last_synced_id": new_last_id,
                "synced_at": datetime.utcnow().isoformat(),
            }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during sync: {e}")
            return {
                "success": False,
                "error": str(e),
                "last_synced_id": last_id,
            }
        except Exception as e:
            logger.error(f"Unexpected error during sync: {e}")
            return {
                "success": False,
                "error": str(e),
                "last_synced_id": last_id,
            }
