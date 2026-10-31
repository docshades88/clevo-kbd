"""Saved state and colour text. Platform-neutral.

The file holds logical zone names and values only. It never holds a device path
or any other platform detail, so it means the same thing on any backend.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .backend import RGB
from .errors import InvalidValueError, StateError

SCHEMA_VERSION = 1
APP_DIR_NAME = "clevo-kbd"
STATE_FILE_NAME = "state.json"

_HEX_COLOR = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_color(text: str) -> RGB:
    match = _HEX_COLOR.match(text.strip())
    if not match:
        raise InvalidValueError(f"Not a colour: {text!r}. Use #rrggbb.")
    digits = match[1]
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def format_color(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def config_dir(platform: str | None = None, environ=None) -> Path:
    """Return the per-user config directory for this platform."""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    if platform == "win32":
        base = environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = environ.get("XDG_CONFIG_HOME") or ""
        if not os.path.isabs(base):
            base = str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def state_path() -> Path:
    return config_dir() / STATE_FILE_NAME


@dataclass
class SavedState:
    on: bool = True
    brightness: int = 0
    link_zones: bool = False
    colors: dict[str, str] = field(default_factory=dict)


def load_state(path: Path) -> SavedState | None:
    """Return the saved state, None if there is none, or raise StateError."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise StateError(f"Cannot read {path}: {error}") from None
    try:
        data = json.loads(text)
        return _validated(data)
    except (ValueError, TypeError, KeyError) as error:
        raise StateError(f"Saved state in {path} is not usable: {error}") from None


def save_state(path: Path, state: SavedState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": SCHEMA_VERSION, **asdict(state)}
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _validated(data) -> SavedState:
    if not isinstance(data, dict):
        raise ValueError("top level is not an object")
    if data.get("version") != SCHEMA_VERSION:
        raise ValueError(f"unknown version {data.get('version')!r}")
    on, brightness, link_zones, colors = (
        data["on"], data["brightness"], data["link_zones"], data["colors"]
    )
    if not isinstance(on, bool) or not isinstance(link_zones, bool):
        raise ValueError("on and link_zones must be true or false")
    if not isinstance(brightness, int) or isinstance(brightness, bool) or brightness < 0:
        raise ValueError(f"bad brightness {brightness!r}")
    if not isinstance(colors, dict):
        raise ValueError("colors is not an object")
    for zone, color in colors.items():
        if not isinstance(color, str) or not _HEX_COLOR.match(color):
            raise ValueError(f"bad colour for {zone}: {color!r}")
    return SavedState(on, brightness, link_zones, dict(colors))
