"""
Hardware abstraction for zone relay control.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Dict, Iterable, Mapping


class BaseHardwareController(ABC):
    """
    Base interface implemented by concrete hardware controllers.
    """

    @abstractmethod
    def set_zone_state(self, zone: str, is_on: bool) -> None:
        """
        Drive the relay/output associated with a zone.
        """

    @abstractmethod
    def get_zone_states(self) -> Mapping[str, bool]:
        """
        Return the current known relay state for each zone.
        """

    @abstractmethod
    def read_zone_temperature(self, zone: str) -> float | None:
        """
        Read the room temperature for a zone (in Fahrenheit).
        Returns None if sensor unavailable.
        """

    @abstractmethod
    def read_pipe_temperature(self, zone: str) -> float | None:
        """
        Read the pipe temperature for a zone (in Fahrenheit).
        Returns None if sensor unavailable.
        """

    def sync_zone_states(self, desired: Mapping[str, bool]) -> None:
        """
        Convenience helper to set many zones at once.
        """
        for zone, state in desired.items():
            self.set_zone_state(zone, state)


class MockHardwareController(BaseHardwareController):
    """
    In-memory simulation used for development and automated tests.
    Generates realistic mock temperature readings.
    """

    def __init__(self, zones: Iterable[str]):
        # Keep an in-memory dictionary that mirrors the relay states.
        self._states: Dict[str, bool] = {zone: False for zone in zones}
        # Generate base temperatures for each zone (simulate different room temps)
        self._base_room_temps: Dict[str, float] = {
            zone: random.uniform(65.0, 72.0) for zone in zones
        }
        # Pipe temps are warmer when zone is ON
        self._base_pipe_temps: Dict[str, float] = {
            zone: random.uniform(75.0, 85.0) for zone in zones
        }

    def set_zone_state(self, zone: str, is_on: bool) -> None:
        # Update the cached state; a real implementation would toggle GPIO pins here.
        self._states[zone] = is_on

    def get_zone_states(self) -> Mapping[str, bool]:
        # Return a copy so callers cannot mutate our internal dict.
        return dict(self._states)

    def read_zone_temperature(self, zone: str) -> float | None:
        """
        Return simulated room temperature with small random variation.
        Zones that are ON will gradually warm up.
        """
        if zone not in self._base_room_temps:
            return None

        base_temp = self._base_room_temps[zone]
        # Add small random variation (-0.5 to +0.5 degrees)
        variation = random.uniform(-0.5, 0.5)

        # If zone is ON, add 2-3 degrees to simulate heating
        if self._states.get(zone, False):
            heating_offset = random.uniform(2.0, 3.0)
            return round(base_temp + heating_offset + variation, 1)

        return round(base_temp + variation, 1)

    def read_pipe_temperature(self, zone: str) -> float | None:
        """
        Return simulated pipe temperature.
        Pipes are much warmer when zone valve is open (ON).
        """
        if zone not in self._base_pipe_temps:
            return None

        # If zone is ON, pipe temp is hot (120-140°F)
        if self._states.get(zone, False):
            return round(random.uniform(120.0, 140.0), 1)

        # If zone is OFF, pipe temp is close to room temp
        base_temp = self._base_pipe_temps[zone]
        variation = random.uniform(-2.0, 2.0)
        return round(base_temp + variation, 1)

