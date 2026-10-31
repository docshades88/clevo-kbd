"""Linux backend: the kernel LED class under /sys/class/leds.

This is the only file that knows sysfs exists. It speaks the standard LED and
multicolor LED class, so it does not care which kernel driver made the devices.

Facts it relies on, read from the kernel and driver source:
- Duplicate LED names get a "_1", "_2" suffix in registration order, and
  clevo_leds.h registers zone 0, 1, 2, so sorted order is left, centre, right.
- multi_intensity_store parses with "%i", so a leading zero means octal, and it
  rejects trailing data. It wants one write of plain decimals.
- It does not range-check, and the Clevo driver truncates to u8, so values must
  be validated here. 256 would become 0.
- Channel order comes from multi_index. It is never assumed.
- Writing multi_intensity re-applies the current brightness, so colour and
  brightness can be written in either order. Colours go first only to avoid a
  moment of the old colour at the new brightness.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..backend import RGB, Backend, HardwareState, Zone
from ..errors import ClevoKbdError, InvalidValueError, NoDeviceError, WriteDeniedError

ENV_SYSFS_ROOT = "CLEVO_KBD_SYSFS_ROOT"
DEFAULT_SYSFS_ROOT = "/sys"

_LED_NAME = re.compile(r"^(?P<base>.+:kbd_backlight)(?:_(?P<index>[0-9]+))?$")
_THREE_ZONES = ("left", "centre", "right")

_NO_DEVICE_HELP = (
    "No keyboard backlight LED device under {leds}.\n"
    "Colour control on this laptop needs a kernel driver, and none has created a "
    "device. Nothing was changed. See 'Install the driver' in the README."
)
_DENIED_HELP = (
    "Not allowed to write {path}.\n"
    "The backlight exists, but this user has no write access to it. Run "
    "packaging/linux/install-system.sh as described in the README, then reboot."
)


@dataclass(frozen=True)
class _Led:
    zone: str
    path: Path
    max_brightness: int
    channels: tuple[str, ...]


class LinuxSysfsBackend(Backend):
    def __init__(self, sysfs_root: str | os.PathLike | None = None) -> None:
        root = sysfs_root or os.environ.get(ENV_SYSFS_ROOT) or DEFAULT_SYSFS_ROOT
        self._leds_dir = Path(root) / "class" / "leds"

    def list_zones(self) -> list[Zone]:
        return [Zone(led.zone, bool(led.channels)) for led in self._scan()]

    def read_state(self) -> HardwareState:
        leds = self._scan()
        colors = {led.zone: self._read_color(led) for led in leds}
        brightness = max(self._read_int(led.path / "brightness") for led in leds)
        return HardwareState(colors, brightness, max(led.max_brightness for led in leds))

    def set_color(self, zone: str, rgb: RGB) -> None:
        if any(not 0 <= part <= 255 for part in rgb):
            raise InvalidValueError(f"Colour out of range: {rgb}")
        led = self._find(zone)
        if not led.channels:
            raise InvalidValueError(f"Zone {zone} has no colour control.")
        by_name = dict(zip(("red", "green", "blue"), rgb))
        values = [
            round(by_name.get(channel, 0) * led.max_brightness / 255)
            for channel in led.channels
        ]
        self._write(led.path / "multi_intensity", " ".join(map(str, values)) + "\n")

    def set_brightness(self, value: int, refresh: bool = False) -> None:
        leds = self._scan()
        top = max(led.max_brightness for led in leds)
        if not 0 <= value <= top:
            raise InvalidValueError(f"Brightness must be 0 to {top}, not {value}.")
        for led in leds:
            target = min(value, led.max_brightness)
            path = led.path / "brightness"
            if refresh or self._read_int(path) != target:
                self._write(path, f"{target}\n")

    def set_power(self, on: bool, brightness: int) -> None:
        # The LED class has no separate power switch: off is brightness 0.
        self.set_brightness(brightness if on else 0)

    def _scan(self) -> list[_Led]:
        try:
            names = os.listdir(self._leds_dir)
        except OSError:
            names = []
        found = []
        for name in names:
            match = _LED_NAME.match(name)
            if match:
                found.append((match["base"], int(match["index"] or 0), name))
        if not found:
            raise NoDeviceError(_NO_DEVICE_HELP.format(leds=self._leds_dir))
        found.sort()
        zone_names = self._zone_names(len(found))
        return [
            self._describe(zone, self._leds_dir / name)
            for zone, (_, _, name) in zip(zone_names, found)
        ]

    @staticmethod
    def _zone_names(count: int) -> tuple[str, ...]:
        if count == 3:
            return _THREE_ZONES
        if count == 1:
            return ("keyboard",)
        return tuple(f"zone{number}" for number in range(1, count + 1))

    def _describe(self, zone: str, path: Path) -> _Led:
        top = self._read_int(path / "max_brightness")
        if top <= 0:
            raise ClevoKbdError(f"{path} reports max_brightness {top}.")
        index = path / "multi_index"
        channels = tuple(self._read(index).split()) if index.exists() else ()
        return _Led(zone, path, top, channels)

    def _find(self, zone: str) -> _Led:
        leds = self._scan()
        for led in leds:
            if led.zone == zone:
                return led
        known = ", ".join(led.zone for led in leds)
        raise InvalidValueError(f"No zone named {zone}. Zones here: {known}.")

    def _read_color(self, led: _Led) -> RGB | None:
        if not led.channels:
            return None
        text = self._read(led.path / "multi_intensity")
        try:
            values = [int(part) for part in text.split()]
        except ValueError:
            raise ClevoKbdError(f"Unexpected multi_intensity: {text!r}") from None
        if len(values) != len(led.channels):
            raise ClevoKbdError(f"Unexpected multi_intensity: {text!r}")
        scaled = {
            channel: min(255, round(value * 255 / led.max_brightness))
            for channel, value in zip(led.channels, values)
        }
        return (scaled.get("red", 0), scaled.get("green", 0), scaled.get("blue", 0))

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            raise NoDeviceError(f"{path} disappeared. Was the driver unloaded?") from None
        except OSError as error:
            raise ClevoKbdError(f"Cannot read {path}: {error.strerror}") from None

    @classmethod
    def _read_int(cls, path: Path) -> int:
        text = cls._read(path)
        try:
            return int(text)
        except ValueError:
            raise ClevoKbdError(f"{path} holds {text!r}, not a number.") from None

    @staticmethod
    def _write(path: Path, text: str) -> None:
        # One write() call: sysfs treats each write as a complete value. No
        # O_CREAT, so a missing attribute is an error and never a new file.
        data = text.encode("ascii")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC)
        except PermissionError:
            raise WriteDeniedError(_DENIED_HELP.format(path=path)) from None
        except FileNotFoundError:
            raise NoDeviceError(f"{path} disappeared. Was the driver unloaded?") from None
        except OSError as error:
            raise ClevoKbdError(f"Cannot open {path}: {error.strerror}") from None
        try:
            if os.write(descriptor, data) != len(data):
                raise ClevoKbdError(f"Short write to {path}.")
        except OSError as error:
            raise ClevoKbdError(f"The driver rejected {path}: {error.strerror}") from None
        finally:
            os.close(descriptor)
