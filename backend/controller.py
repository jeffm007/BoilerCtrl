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
    Simulates realistic room temperature dynamics with gradual heating/cooling.
    """

    def __init__(self, zones: Iterable[str]):
        import time
        # Keep an in-memory dictionary that mirrors the relay states.
        self._states: Dict[str, bool] = {zone: False for zone in zones}

        # Current simulated room temperatures (start at ambient)
        self._current_room_temps: Dict[str, float] = {
            zone: random.uniform(65.0, 68.0) for zone in zones
        }

        # Target setpoints for each zone (will be updated by control logic)
        self._target_setpoints: Dict[str, float] = {
            zone: 68.0 for zone in zones
        }

        # Track last update time for realistic time-based temperature changes
        self._last_update: Dict[str, float] = {
            zone: time.time() for zone in zones
        }

        # Ambient (outside) temperature - rooms drift toward this when off
        self._ambient_temp: float = 65.0

        # Pipe temps are warmer when zone is ON
        self._pipe_temps: Dict[str, float] = {
            zone: 75.0 for zone in zones
        }

    def set_zone_state(self, zone: str, is_on: bool) -> None:
        # Update the cached state; a real implementation would toggle GPIO pins here.
        self._states[zone] = is_on

    def get_zone_states(self) -> Mapping[str, bool]:
        # Return a copy so callers cannot mutate our internal dict.
        return dict(self._states)

    def set_zone_setpoint(self, zone: str, setpoint: float) -> None:
        """Update the target setpoint for temperature simulation."""
        if zone in self._target_setpoints:
            self._target_setpoints[zone] = setpoint

    def read_zone_temperature(self, zone: str) -> float | None:
        """
        Return simulated room temperature with realistic thermal dynamics.
        - When heating (ON): gradually rises toward setpoint + 0.5°F
        - When off (OFF): gradually drifts toward ambient temperature
        - Heating rate: ~1-2°F per minute
        - Cooling rate: ~0.3-0.5°F per minute
        """
        import time

        if zone not in self._current_room_temps:
            return None

        current_temp = self._current_room_temps[zone]
        is_heating = self._states.get(zone, False)
        target_setpoint = self._target_setpoints.get(zone, 68.0)

        # Calculate time delta since last update (in minutes)
        now = time.time()
        last_update = self._last_update.get(zone, now)
        time_delta_minutes = (now - last_update) / 60.0
        self._last_update[zone] = now

        # Simulate temperature change based on heating state
        if is_heating:
            # Heating: rise toward setpoint + 0.5°F overshoot
            target_temp = target_setpoint + 0.5
            if current_temp < target_temp:
                # Heat at 1.5°F per minute
                temp_rise = min(1.5 * time_delta_minutes, target_temp - current_temp)
                current_temp += temp_rise
        else:
            # Not heating: drift toward ambient
            if current_temp > self._ambient_temp:
                # Cool at 0.4°F per minute
                temp_drop = min(0.4 * time_delta_minutes, current_temp - self._ambient_temp)
                current_temp -= temp_drop

        # Add small random measurement noise (-0.1 to +0.1°F)
        noise = random.uniform(-0.1, 0.1)
        current_temp += noise

        # Update stored temperature
        self._current_room_temps[zone] = current_temp

        return round(current_temp, 1)

    def read_pipe_temperature(self, zone: str) -> float | None:
        """
        Return simulated pipe temperature.
        Pipes heat up quickly when valve opens, cool slowly when closed.
        """
        import time

        if zone not in self._pipe_temps:
            return None

        current_pipe_temp = self._pipe_temps[zone]
        is_on = self._states.get(zone, False)

        # Calculate time delta
        now = time.time()
        time_delta_minutes = (now - self._last_update.get(zone, now)) / 60.0

        if is_on:
            # Heating: pipe quickly heats to 130°F
            target_pipe_temp = 130.0
            if current_pipe_temp < target_pipe_temp:
                # Heat at 10°F per minute (pipes heat fast)
                temp_rise = min(10.0 * time_delta_minutes, target_pipe_temp - current_pipe_temp)
                current_pipe_temp += temp_rise
        else:
            # Cooling: pipe gradually cools toward room temp
            room_temp = self._current_room_temps.get(zone, 70.0)
            if current_pipe_temp > room_temp + 5:
                # Cool at 3°F per minute
                temp_drop = min(3.0 * time_delta_minutes, current_pipe_temp - (room_temp + 5))
                current_pipe_temp -= temp_drop

        # Update stored pipe temperature
        self._pipe_temps[zone] = current_pipe_temp

        return round(current_pipe_temp, 1)

