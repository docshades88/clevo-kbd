"""Errors shared by every layer. Each carries the CLI exit code it maps to."""


class ClevoKbdError(Exception):
    exit_code = 1


class InvalidValueError(ClevoKbdError):
    """A zone, colour or brightness the hardware cannot take."""

    exit_code = 2


class NoDeviceError(ClevoKbdError):
    """No keyboard backlight is available to this backend."""

    exit_code = 3


class WriteDeniedError(ClevoKbdError):
    """The backlight exists but this user may not change it."""

    exit_code = 4


class UnsupportedPlatformError(ClevoKbdError):
    """No backend exists for this operating system."""

    exit_code = 5


class StateError(ClevoKbdError):
    """The saved state file exists but cannot be used."""

    exit_code = 1
