"""
Sync protocol implementation for Pi <-> NAS communication.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Union
from collections import deque

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SyncProtocol:
    """Base class for sync protocol handling."""

    def __init__(self, max_queue_size: int = 1000):
        self.sequence_id = 0
        self.message_queue = deque(maxlen=max_queue_size)
        self.pending_commands: Dict[str, asyncio.Future] = {}

    def next_sequence(self) -> int:
        """Get next sequence ID."""
        self.sequence_id += 1
        return self.sequence_id

    def create_message(self, event_type: str, payload: Union[BaseModel, dict]) -> Dict[str, Any]:
        """Create a sync message. Payload can be a Pydantic model or dict."""
        if isinstance(payload, dict):
            payload_data = payload
        else:
            payload_data = payload.model_dump(by_alias=True)

        return {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sequence_id": self.next_sequence(),
            "payload": payload_data
        }

    def serialize_message(self, message: Dict[str, Any]) -> str:
        """Serialize message to JSON."""
        return json.dumps(message)

    def deserialize_message(self, data: str) -> Dict[str, Any]:
        """Deserialize JSON message."""
        return json.loads(data)


class SyncServer(SyncProtocol):
    """Sync server for Pi controller (publishes state, receives commands)."""

    def __init__(self, max_queue_size: int = 1000, batch_interval: float = 1.0):
        super().__init__(max_queue_size)
        self.batch_interval = batch_interval
        self.command_handlers: Dict[str, Callable] = {}
        self.connected_clients = set()
        self.batch_buffer = []

    def register_command_handler(self, command_type: str, handler: Callable):
        """Register handler for command type."""
        self.command_handlers[command_type] = handler

    async def handle_command(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process command from NAS."""
        payload = message["payload"]
        command_type = payload.get("command_type")

        handler = self.command_handlers.get(command_type)
        if not handler:
            return self.create_message("command_response", {
                "command_id": payload["command_id"],
                "success": False,
                "error": f"Unknown command type: {command_type}"
            })

        try:
            result = await handler(payload)
            return self.create_message("command_response", {
                "command_id": payload["command_id"],
                "success": True,
                "result": result
            })
        except Exception as e:
            logger.exception(f"Command handler failed: {e}")
            return self.create_message("command_response", {
                "command_id": payload["command_id"],
                "success": False,
                "error": str(e)
            })

    def queue_state_update(self, zones: list, system: Optional[dict] = None):
        """Queue zone state update for batching."""
        self.batch_buffer.append({
            "zones": zones,
            "system": system,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

    async def send_batched_updates(self, send_func: Callable):
        """Send batched state updates."""
        if not self.batch_buffer:
            return

        # Combine recent updates (last state wins)
        latest_zones = {}
        latest_system = None

        for update in self.batch_buffer:
            for zone in update["zones"]:
                latest_zones[zone["ZoneName"]] = zone
            if update["system"]:
                latest_system = update["system"]

        message = self.create_message("zone_state_update", {
            "zones": list(latest_zones.values()),
            "system": latest_system
        })

        await send_func(self.serialize_message(message))
        self.batch_buffer.clear()


class SyncClient(SyncProtocol):
    """Sync client for NAS dashboard (subscribes to state, sends commands)."""

    def __init__(self, max_queue_size: int = 1000, command_timeout: float = 30.0):
        super().__init__(max_queue_size)
        self.command_timeout = command_timeout
        self.state_update_handlers = []
        self.last_received_sequence = 0
        self.reconnect_backoff = 1.0
        self.max_reconnect_backoff = 60.0

    def register_state_handler(self, handler: Callable):
        """Register handler for state updates."""
        self.state_update_handlers.append(handler)

    async def handle_state_update(self, message: Dict[str, Any]):
        """Process state update from Pi."""
        sequence = message["sequence_id"]

        # Detect gaps (missed messages during disconnect)
        if sequence > self.last_received_sequence + 1:
            logger.warning(f"Sequence gap detected: {self.last_received_sequence} -> {sequence}")
            # Could request full sync here

        self.last_received_sequence = sequence
        payload = message["payload"]

        for handler in self.state_update_handlers:
            try:
                await handler(payload)
            except Exception as e:
                logger.exception(f"State handler failed: {e}")

    async def send_command(self, command_type: str, command_data: dict,
                          zone_name: Optional[str] = None,
                          send_func: Callable = None) -> Dict[str, Any]:
        """Send command to Pi and wait for response."""
        import uuid

        command_id = str(uuid.uuid4())
        message = self.create_message("command_request", {
            "command_id": command_id,
            "zone_name": zone_name,
            "command_type": command_type,
            "command_data": command_data
        })

        # Create future for response
        future = asyncio.Future()
        self.pending_commands[command_id] = future

        await send_func(self.serialize_message(message))

        try:
            response = await asyncio.wait_for(future, timeout=self.command_timeout)
            return response
        except asyncio.TimeoutError:
            self.pending_commands.pop(command_id, None)
            raise TimeoutError(f"Command {command_id} timed out")

    async def handle_command_response(self, message: Dict[str, Any]):
        """Process command response from Pi."""
        payload = message["payload"]
        command_id = payload["command_id"]

        future = self.pending_commands.pop(command_id, None)
        if future and not future.done():
            future.set_result(payload)

    def reset_reconnect_backoff(self):
        """Reset backoff after successful connection."""
        self.reconnect_backoff = 1.0

    def increase_reconnect_backoff(self):
        """Increase backoff after failed connection."""
        self.reconnect_backoff = min(
            self.reconnect_backoff * 2,
            self.max_reconnect_backoff
        )
