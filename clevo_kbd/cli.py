"""Command line. Platform-neutral: all hardware goes through Session."""

from __future__ import annotations

import argparse
import sys

from .backends import create_backend
from .errors import ClevoKbdError
from .session import ALL_ZONES, Session
from .state import format_color, parse_color


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clevo-kbd", description="Control the keyboard backlight colour and brightness."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="show zones, colours and brightness")
    commands.add_parser("gui", help="open the window")
    commands.add_parser("on", help="turn the backlight on at the saved brightness")
    commands.add_parser("off", help="turn the backlight off, keeping the saved brightness")
    commands.add_parser("apply", help="re-apply the saved state")
    set_parser = commands.add_parser("set", help="set a zone's colour")
    set_parser.add_argument("--zone", default=ALL_ZONES, help="left, centre, right or all")
    set_parser.add_argument("--color", "--colour", required=True, help="#rrggbb")
    brightness = commands.add_parser("brightness", help="set the brightness")
    brightness.add_argument("value", type=int)
    return parser


def run_command(args, session: Session) -> int:
    if session.load_error and args.command != "apply":
        print(f"clevo-kbd: warning: {session.load_error}", file=sys.stderr)
    if args.command == "status":
        return show_status(session)
    if args.command == "apply":
        if not session.restore():
            print("Nothing saved yet, so nothing to apply.")
        return 0
    if args.command == "set":
        session.set_color(args.zone, parse_color(args.color))
    elif args.command == "brightness":
        session.set_brightness(args.value)
    elif args.command == "on":
        session.set_power(True)
    elif args.command == "off":
        session.set_power(False)
    session.save()
    return 0


def show_status(session: Session) -> int:
    live = session.read()
    for zone in session.zones():
        color = live.colors.get(zone.name)
        print(f"{zone.name:<12}{format_color(color) if color else '(no colour control)'}")
    state = "on" if live.on else "off"
    print(f"{'brightness':<12}{live.brightness}/{live.max_brightness} ({state})")
    print(f"{'saved in':<12}{session.path if session.has_saved_state else '(nothing saved yet)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "gui":
        return run_gui()
    try:
        return run_command(args, Session(create_backend()))
    except ClevoKbdError as error:
        print(f"clevo-kbd: {error}", file=sys.stderr)
        return error.exit_code


def run_gui() -> int:
    try:
        from .gui import run
    except ImportError as error:
        print(f"clevo-kbd: the window needs PySide6: {error}", file=sys.stderr)
        return 1
    return run()
