"""A fake sysfs tree, plus the kernel's own acceptance rule for multi_intensity.

Plain files accept any bytes, so a fake alone would pass a format the kernel
rejects. kernel_accepts_multi_intensity() re-implements multi_intensity_store
from drivers/leds/led-class-multicolor.c (6.18.55) so the tests can hold the
backend to the real contract.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DRIVER_ZONE_LEDS = ("rgb:kbd_backlight", "rgb:kbd_backlight_1", "rgb:kbd_backlight_2")
UNRELATED_LEDS = ("input4::capslock", "input4::numlock", "phy0-led")

_PERCENT_I = re.compile(r"\s*[+-]?(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)")


def kernel_accepts_multi_intensity(data: bytes, num_colors: int = 3) -> bool:
    """Port of the parse loop and the trailing-data check."""
    text = data.decode("ascii")
    offset = 0
    for _ in range(num_colors):
        match = _PERCENT_I.match(text, offset)
        if not match:
            return False
        offset = match.end()
    return offset + 1 >= len(data)


def percent_i_values(data: bytes) -> list[int]:
    """What sscanf("%i") would actually read, so octal surprises show up."""
    return [int(token, 0) if not re.fullmatch(r"0[0-7]+", token) else int(token, 8)
            for token in data.decode("ascii").split()]


class FakeSysfs:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.leds = root / "class" / "leds"
        self.leds.mkdir(parents=True)
        for name in UNRELATED_LEDS:
            (self.leds / name).mkdir()
            (self.leds / name / "brightness").write_text("0\n")

    def add_rgb(self, name: str, max_brightness: int = 255,
                channels: str = "red green blue") -> Path:
        path = self.leds / name
        path.mkdir()
        (path / "max_brightness").write_text(f"{max_brightness}\n")
        (path / "brightness").write_text("0\n")
        (path / "multi_index").write_text(channels + "\n")
        (path / "multi_intensity").write_text(
            " ".join([str(max_brightness)] * len(channels.split())) + "\n"
        )
        return path

    def add_white(self, name: str, max_brightness: int = 2) -> Path:
        path = self.leds / name
        path.mkdir()
        (path / "max_brightness").write_text(f"{max_brightness}\n")
        (path / "brightness").write_text("0\n")
        return path

    def add_three_zones(self) -> None:
        for name in DRIVER_ZONE_LEDS:
            self.add_rgb(name)

    def forget_like_a_reboot(self) -> None:
        """What clevo_leds_init leaves behind: white at brightness 0."""
        for name in DRIVER_ZONE_LEDS:
            (self.leds / name / "multi_intensity").write_text("255 255 255\n")
            (self.leds / name / "brightness").write_text("0\n")

    def intensity(self, name: str) -> str:
        return (self.leds / name / "multi_intensity").read_text()

    def brightness(self, name: str) -> str:
        return (self.leds / name / "brightness").read_text().strip()

    def snapshot(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.root)): path.read_text()
            for path in sorted(self.root.rglob("*")) if path.is_file()
        }


class FakeRootTestCase(unittest.TestCase):
    """Every test runs against a private tree and a private config directory."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="clevo-kbd-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fake = FakeSysfs(self.tmp / "sys")
        patcher = mock.patch.dict("os.environ", {
            "CLEVO_KBD_SYSFS_ROOT": str(self.fake.root),
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state_file = self.tmp / "config" / "clevo-kbd" / "state.json"
