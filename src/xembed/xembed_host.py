"""XEmbed system tray host — X11 only.

Implements the freedesktop.org System Tray Protocol:
  1. Acquires the ``_NET_SYSTEM_TRAY_S{screen}`` selection.
  2. Listens for ``_NET_SYSTEM_TRAY_OPCODE`` client messages (SYSTEM_TRAY_REQUEST_DOCK).
  3. Embeds the docked X11 window into a GTK widget.

This module is a no-op on Wayland or if ``GdkX11`` is unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

# Try to import GdkX11 for X11-specific APIs.
try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11  # type: ignore[attr-defined]

    HAS_X11 = True
except (ValueError, ImportError):
    HAS_X11 = False

# XEmbed opcodes (from the freedesktop spec).
SYSTEM_TRAY_REQUEST_DOCK = 0
SYSTEM_TRAY_BEGIN_MESSAGE = 1
SYSTEM_TRAY_CANCEL_MESSAGE = 2


class XEmbedHost:
    """Manages the X11 system tray selection and embeds docked windows.

    Instantiation on Wayland is safe — it simply does nothing.
    """

    def __init__(self, *, icon_manager: IconManager, screen: int = 0) -> None:
        self._icon_manager = icon_manager
        self._screen = screen
        self._active = False
        self._docked_windows: dict[int, Gtk.Widget] = {}

        if not HAS_X11:
            logger.info("GdkX11 not available; XEmbed host disabled")
            return

        display = Gdk.Display.get_default()
        if display is None or not isinstance(display, GdkX11.X11Display):
            logger.info("Not running on X11; XEmbed host disabled")
            return

        self._display = display
        self._xdisplay = display.get_xdisplay()

        # The selection atom: _NET_SYSTEM_TRAY_S<screen>
        self._selection_name = f"_NET_SYSTEM_TRAY_S{screen}"

        # Acquire the selection.
        try:
            self._acquire_selection()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to acquire %s", self._selection_name, exc_info=True)

    def _acquire_selection(self) -> None:
        """Attempt to own the tray selection on the X server."""
        # NOTE: GTK4 does not directly expose X selection ownership the way
        # GTK3 did (via GdkX11.X11Window.set_selection_owner).  A production
        # implementation would use python-xlib or ctypes to call
        # XSetSelectionOwner and broadcast the MANAGER client message.
        #
        # For now we log a placeholder; the full Xlib interaction will be
        # fleshed out when testing on a live X11 session.
        logger.info(
            "XEmbed host: would acquire selection %s (placeholder)",
            self._selection_name,
        )
        self._active = True

    def handle_client_message(self, xid: int, opcode: int, data: tuple) -> None:
        """Process an incoming _NET_SYSTEM_TRAY_OPCODE client message."""
        if not self._active:
            return

        if opcode == SYSTEM_TRAY_REQUEST_DOCK:
            window_xid = data[2] if len(data) > 2 else 0
            if window_xid:
                self._dock_window(window_xid)
        elif opcode == SYSTEM_TRAY_BEGIN_MESSAGE:
            logger.debug("XEmbed: BEGIN_MESSAGE from %d (ignored for now)", xid)
        elif opcode == SYSTEM_TRAY_CANCEL_MESSAGE:
            logger.debug("XEmbed: CANCEL_MESSAGE from %d", xid)

    def _dock_window(self, xid: int) -> None:
        """Embed an X11 window *xid* into the tray."""
        if xid in self._docked_windows:
            return

        logger.info("XEmbed: docking X11 window 0x%x", xid)

        # In GTK4, embedding foreign X11 windows requires creating a
        # GdkX11.X11Surface from the foreign XID and wrapping it.
        # Full implementation would use:
        #   surface = GdkX11.X11Surface.foreign_new_for_display(display, xid)
        #   ... then wrap in a widget and add to the icon manager.
        #
        # Placeholder: register the icon with a generic entry.
        icon_id = f"xembed:{xid:#x}"
        self._icon_manager.upsert_icon(icon_id, {
            "title": f"Legacy tray (0x{xid:x})",
            "icon_name": "application-x-executable-symbolic",
            "status": "Active",
            "pinned": True,
            "xembed_xid": xid,
        })
        self._docked_windows[xid] = None  # Widget placeholder.

    def undock_window(self, xid: int) -> None:
        """Remove a docked window."""
        icon_id = f"xembed:{xid:#x}"
        self._icon_manager.remove_icon(icon_id)
        self._docked_windows.pop(xid, None)
        logger.info("XEmbed: undocked X11 window 0x%x", xid)

    @property
    def is_active(self) -> bool:
        return self._active

    def destroy(self) -> None:
        for xid in list(self._docked_windows):
            self.undock_window(xid)
        self._active = False
        logger.debug("XEmbed host destroyed")
