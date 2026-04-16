"""Entry point for Linux App Tray."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib

from src.application import TrayApplication

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logger = logging.getLogger("linux-app-tray")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="linux-app-tray",
        description="Windows-style expandable system tray for Linux",
    )
    parser.add_argument(
        "--position",
        choices=("top", "bottom"),
        default="bottom",
        help="Screen edge for the tray bar (default: bottom)",
    )
    parser.add_argument(
        "--monitor",
        default="primary",
        help="Monitor to place the tray on (default: primary)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format=LOG_FORMAT, level=level)
    logger.info("Starting Linux App Tray (position=%s, monitor=%s)", args.position, args.monitor)

    # Ensure SIGINT terminates cleanly even inside the GLib main loop.
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, _quit_app, None)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, _quit_app, None)

    app = TrayApplication(position=args.position, monitor=args.monitor)

    # Store globally so the signal handler can reach it.
    main._app = app

    return app.run(sys.argv[:1])


def _quit_app(_user_data: object = None) -> bool:
    app = getattr(main, "_app", None)
    if app is not None:
        app.quit()
    return GLib.SOURCE_REMOVE


if __name__ == "__main__":
    raise SystemExit(main())
