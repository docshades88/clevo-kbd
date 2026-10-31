"""Picks the backend for this platform."""

from __future__ import annotations

import sys

from ..backend import Backend
from ..errors import UnsupportedPlatformError


def create_backend(platform: str | None = None) -> Backend:
    platform = platform or sys.platform
    if platform.startswith("linux"):
        from .linux_sysfs import LinuxSysfsBackend

        return LinuxSysfsBackend()
    raise UnsupportedPlatformError(
        f"clevo-kbd has no backend for this platform ({platform}) yet. "
        "Only Linux is built so far."
    )
