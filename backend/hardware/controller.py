"""
Hardware abstraction for zone relay control.
"""

from __future__ import annotations

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

    def sync_zone_states(self, desired: Mapping[str, bool]) -> None:
        """
        Convenience helper to set many zones at once.
        """
        for zone, state in desired.items():
            self.set_zone_state(zone, state)


class MockHardwareController(BaseHardwareController):
    """
    In-memory simulation used for development and automated tests.
    """

    def __init__(self, zones: Iterable[str]):
        # Keep an in-memory dictionary that mirrors the relay states.
        self._states: Dict[str, bool] = {zone: False for zone in zones}

    def set_zone_state(self, zone: str, is_on: bool) -> None:
        # Update the cached state; a real implementation would toggle GPIO pins here.
        self._states[zone] = is_on

    def get_zone_states(self) -> Mapping[str, bool]:
        # Return a copy so callers cannot mutate our internal dict.
        return dict(self._states)
