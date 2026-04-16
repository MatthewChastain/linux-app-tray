"""Central icon registry — ordering, pinning, and state management.

Emits GObject signals so the UI layer (TrayWindow) can react to changes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, GObject

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "linux-app-tray"
STATE_FILE = CONFIG_DIR / "state.json"


class IconManager(GObject.Object):
    """Tracks every known tray icon and persists ordering/pinning state."""

    __gsignals__ = {
        "icon-added": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "icon-removed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "icon-updated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "layout-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__()
        # icon_id → info dict
        self._icons: dict[str, dict[str, Any]] = {}
        # Ordered list of icon IDs (display order).
        self._order: list[str] = []
        # D-Bus connection (set after the watcher starts).
        self._connection: Gio.DBusConnection | None = None
        # SNI proxy references (for action dispatch).
        self._sni_proxies: dict[str, Any] = {}

        self._load_state()

    # -- Icon CRUD ------------------------------------------------------------

    def upsert_icon(self, icon_id: str, info: dict[str, Any]) -> None:
        """Insert or update an icon entry. Emits the appropriate signal."""
        is_new = icon_id not in self._icons

        # Merge saved pinning/order state.
        saved = self._saved_state.get(icon_id, {})
        if "pinned" in saved:
            info.setdefault("pinned", saved["pinned"])

        self._icons[icon_id] = info

        if is_new:
            if icon_id not in self._order:
                # Insert at saved position or append.
                saved_idx = saved.get("order")
                if saved_idx is not None and 0 <= saved_idx <= len(self._order):
                    self._order.insert(saved_idx, icon_id)
                else:
                    self._order.append(icon_id)
            self.emit("icon-added", icon_id)
            logger.debug("Icon added: %s", icon_id)
        else:
            self.emit("icon-updated", icon_id)

    def remove_icon(self, icon_id: str) -> None:
        if icon_id in self._icons:
            del self._icons[icon_id]
        if icon_id in self._order:
            self._order.remove(icon_id)
        self._sni_proxies.pop(icon_id, None)
        self.emit("icon-removed", icon_id)
        self._save_state()
        logger.debug("Icon removed: %s", icon_id)

    def get_icon_info(self, icon_id: str) -> dict[str, Any] | None:
        return self._icons.get(icon_id)

    def ordered_ids(self) -> list[str]:
        return list(self._order)

    # -- Pinning --------------------------------------------------------------

    def set_pinned(self, icon_id: str, pinned: bool) -> None:
        info = self._icons.get(icon_id)
        if info is None:
            return
        info["pinned"] = pinned
        self._save_state()
        self.emit("layout-changed")

    # -- Reordering -----------------------------------------------------------

    def reorder(self, icon_id: str, *, before: str) -> None:
        """Move *icon_id* so it appears just before *before*."""
        if icon_id not in self._order or before not in self._order:
            return
        self._order.remove(icon_id)
        idx = self._order.index(before)
        self._order.insert(idx, icon_id)
        self._save_state()
        self.emit("layout-changed")
        logger.debug("Reordered: %s before %s", icon_id, before)

    # -- Action dispatch (called from TrayIcon) --------------------------------

    def register_sni_proxy(self, icon_id: str, proxy: Any) -> None:
        self._sni_proxies[icon_id] = proxy

    def activate(self, icon_id: str, x: int, y: int) -> None:
        proxy = self._sni_proxies.get(icon_id)
        if proxy:
            proxy.activate(x, y)

    def secondary_activate(self, icon_id: str, x: int, y: int) -> None:
        proxy = self._sni_proxies.get(icon_id)
        if proxy:
            proxy.secondary_activate(x, y)

    def scroll(self, icon_id: str, dx: float, dy: float) -> None:
        proxy = self._sni_proxies.get(icon_id)
        if proxy is None:
            return
        if abs(dx) > abs(dy):
            proxy.scroll(int(dx), "horizontal")
        else:
            proxy.scroll(int(dy), "vertical")

    # -- D-Bus connection accessor (used by ContextMenuBuilder) ---------------

    def set_connection(self, conn: Gio.DBusConnection) -> None:
        self._connection = conn

    def get_connection(self) -> Gio.DBusConnection | None:
        if self._connection is not None:
            return self._connection
        # Fallback: get the session bus directly.
        try:
            return Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return None

    # -- Persistent state (ordering, pinning) ---------------------------------

    def _load_state(self) -> None:
        self._saved_state: dict[str, dict] = {}
        if STATE_FILE.is_file():
            try:
                data = json.loads(STATE_FILE.read_text())
                self._saved_state = data.get("icons", {})
                self._order = data.get("order", [])
                logger.debug("Loaded state from %s", STATE_FILE)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load state: %s", exc)

    def _save_state(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        state: dict[str, dict] = {}
        for icon_id, info in self._icons.items():
            state[icon_id] = {"pinned": info.get("pinned", True)}

        data = {"icons": state, "order": self._order}
        try:
            STATE_FILE.write_text(json.dumps(data, indent=2))
        except OSError as exc:
            logger.warning("Failed to save state: %s", exc)

    # -- Cleanup --------------------------------------------------------------

    def destroy(self) -> None:
        self._save_state()
        self._icons.clear()
        self._order.clear()
        self._sni_proxies.clear()
        logger.debug("IconManager destroyed")
