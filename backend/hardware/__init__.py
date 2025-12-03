"""
Hardware abstraction layer.
"""

from .controller import BaseHardwareController, MockHardwareController

__all__ = ["BaseHardwareController", "MockHardwareController"]

