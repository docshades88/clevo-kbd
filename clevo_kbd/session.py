"""The one place that changes the keyboard and keeps the saved state in step.

The CLI and GUI both drive this class, so they cannot drift apart. A value is
saved only after the hardware accepted it, so `apply` never replays something
that never took effect.
"""

from __future__ import annotations

from pathlib import Path

from .backend import RGB, Backend, HardwareState, Zone
from .errors import ClevoKbdError, InvalidValueError, StateError
from .state import SavedState, format_color, load_state, parse_color, save_state, state_path

ALL_ZONES = "all"
ZONE_ALIASES = {"center": "centre"}


class Session:
    def __init__(self, backend: Backend, path: Path | None = None) -> None:
        self.backend = backend
        self.path = path or state_path()
        self.load_error: StateError | None = None
        self._state: SavedState | None = None
        self._dirty = False
        try:
            self._state = load_state(self.path)
        except StateError as error:
            self.load_error = error

    @property
    def has_saved_state(self) -> bool:
        return self._state is not None

    @property
    def link_zones(self) -> bool:
        return self._state.link_zones if self._state else False

    @property
    def saved_brightness(self) -> int:
        return self._state.brightness if self._state else 0

    def zones(self) -> list[Zone]:
        return self.backend.list_zones()

    def read(self) -> HardwareState:
        return self.backend.read_state()

    def resolve_zones(self, name: str) -> list[str]:
        known = [zone.name for zone in self.backend.list_zones()]
        if name == ALL_ZONES:
            return known
        name = ZONE_ALIASES.get(name, name)
        if name not in known:
            raise InvalidValueError(f"No zone named {name}. Zones here: {', '.join(known)}.")
        return [name]

    def set_color(self, zone_name: str, rgb: RGB) -> None:
        targets = self.resolve_zones(zone_name)
        state = self._current()
        for zone in targets:
            self.backend.set_color(zone, rgb)
            state.colors[zone] = format_color(rgb)
            self._dirty = True

    def set_brightness(self, value: int) -> None:
        state = self._current()
        self.backend.set_brightness(value)
        state.brightness = value
        state.on = True
        self._dirty = True

    def set_power(self, on: bool) -> None:
        state = self._current()
        level = state.brightness or self.backend.read_state().max_brightness
        self.backend.set_power(on, level)
        state.brightness = level
        state.on = on
        self._dirty = True

    def set_link_zones(self, linked: bool) -> None:
        self._current().link_zones = linked
        self._dirty = True

    def restore(self) -> bool:
        """Re-apply the saved state. Returns False if nothing is saved."""
        if self.load_error:
            raise self.load_error
        if self._state is None:
            return False
        known = {zone.name for zone in self.backend.list_zones() if zone.has_color}
        problems = []
        for zone, color in self._state.colors.items():
            if zone in known:
                try:
                    self.backend.set_color(zone, parse_color(color))
                except ClevoKbdError as error:
                    problems.append(error)
        try:
            top = self.backend.read_state().max_brightness
            level = min(self._state.brightness, top) if self._state.on else 0
            self.backend.set_brightness(level, refresh=True)
        except ClevoKbdError as error:
            problems.append(error)
        if problems:
            raise problems[0]
        return True

    def save(self) -> None:
        """Write the state, but only once the hardware accepted something."""
        if self._state is not None and self._dirty:
            save_state(self.path, self._state)
            self.load_error = None
            self._dirty = False

    def _current(self) -> SavedState:
        """Return the state, starting from the hardware if nothing is saved."""
        if self._state is None:
            live = self.backend.read_state()
            colors = {
                zone: format_color(rgb) for zone, rgb in live.colors.items() if rgb is not None
            }
            self._state = SavedState(live.on, live.brightness, False, colors)
        return self._state
