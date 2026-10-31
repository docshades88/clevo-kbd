"""The hardware interface.

Everything outside clevo_kbd/backends/ talks to the keyboard through this class
and nothing else. A backend owns all platform knowledge, including the wording
of its own errors, so the shared code stays platform-neutral.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Zone:
    name: str
    has_color: bool


@dataclass(frozen=True)
class HardwareState:
    """What the hardware reports right now. A colour is None if it has none."""

    colors: dict[str, RGB | None]
    brightness: int
    max_brightness: int

    @property
    def on(self) -> bool:
        return self.brightness > 0


class Backend(abc.ABC):
    @abc.abstractmethod
    def list_zones(self) -> list[Zone]:
        """Return the zones in physical order, or raise NoDeviceError."""

    @abc.abstractmethod
    def read_state(self) -> HardwareState:
        """Return the current state, or raise NoDeviceError."""

    @abc.abstractmethod
    def set_color(self, zone: str, rgb: RGB) -> None:
        """Set one zone's colour. Components are 0 to 255."""

    @abc.abstractmethod
    def set_brightness(self, value: int, refresh: bool = False) -> None:
        """Set the brightness, 0 to HardwareState.max_brightness.

        A backend may skip hardware that already reports this value. With
        refresh=True it must write regardless, because firmware can lose a
        value that the driver still reports.
        """

    @abc.abstractmethod
    def set_power(self, on: bool, brightness: int) -> None:
        """Turn the backlight off, or on at the given brightness."""
