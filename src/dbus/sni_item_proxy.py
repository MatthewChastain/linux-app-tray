"""Proxy for a single org.kde.StatusNotifierItem on D-Bus.

Creates a :class:`Gio.DBusProxy` for the item, monitors property changes, and
translates them into :class:`IconManager` updates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from gi.repository import Gio, GLib

from src.dbus.interfaces import STATUS_NOTIFIER_ITEM_XML

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

SNI_INTERFACE = "org.kde.StatusNotifierItem"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DEBOUNCE_MS = 30

# Signals emitted by the item and the property they correspond to.
_SIGNAL_TO_PROP: dict[str, str] = {
    "NewTitle": "Title",
    "NewIcon": "IconName",
    "NewAttentionIcon": "AttentionIconName",
    "NewOverlayIcon": "OverlayIconName",
    "NewToolTip": "ToolTip",
    "NewStatus": "Status",
    "XAyatanaNewLabel": "XAyatanaLabel",
}


class SNIItemProxy:
    """Wraps a remote StatusNotifierItem and keeps the IconManager in sync."""

    def __init__(
        self,
        *,
        bus_name: str,
        object_path: str,
        connection: Gio.DBusConnection,
        icon_manager: IconManager,
        cancellable: Gio.Cancellable,
    ) -> None:
        self._bus_name = bus_name
        self._object_path = object_path
        self._connection = connection
        self._icon_manager = icon_manager
        self._cancellable = Gio.Cancellable()
        self._parent_cancellable = cancellable
        self._destroy_cb: Callable[[], None] | None = None
        self._debounce_source: int = 0
        self._pending_props: set[str] = set()
        self._proxy: Gio.DBusProxy | None = None
        self._signal_sub_ids: list[int] = []

        self._item_id = f"{bus_name}{object_path}"

        # Parse interface info for the proxy.
        node_info = Gio.DBusNodeInfo.new_for_xml(STATUS_NOTIFIER_ITEM_XML)
        iface_info = node_info.interfaces[0]

        # Create the proxy asynchronously.
        Gio.DBusProxy.new(
            connection,
            Gio.DBusProxyFlags.GET_INVALIDATED_PROPERTIES,
            iface_info,
            bus_name,
            object_path,
            SNI_INTERFACE,
            self._cancellable,
            self._on_proxy_ready,
        )

    # -- Proxy creation callback ----------------------------------------------

    def _on_proxy_ready(self, _source: object, result: Gio.AsyncResult) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_finish(result)
        except GLib.Error as exc:
            logger.warning("Failed to create proxy for %s: %s", self._item_id, exc.message)
            self._notify_destroyed()
            return

        # Monitor property changes.
        self._proxy.connect("g-properties-changed", self._on_properties_changed)

        # Monitor name owner loss (app exited).
        self._proxy.connect("notify::g-name-owner", self._on_name_owner_changed)

        # Subscribe to custom SNI signals (NewIcon, NewTitle, etc.).
        for signal_name in _SIGNAL_TO_PROP:
            sub_id = self._connection.signal_subscribe(
                self._bus_name,
                SNI_INTERFACE,
                signal_name,
                self._object_path,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_sni_signal,
            )
            self._signal_sub_ids.append(sub_id)

        # Initial property push.
        self._push_all_properties()
        logger.debug("Proxy ready for %s", self._item_id)

    # -- Property change handling --------------------------------------------

    def _on_properties_changed(
        self,
        _proxy: Gio.DBusProxy,
        changed: GLib.Variant,
        _invalidated: list[str],
    ) -> None:
        props = changed.unpack() if changed else {}
        self._pending_props.update(props.keys())
        self._schedule_debounce()

    def _on_sni_signal(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _iface: str,
        signal_name: str,
        _params: GLib.Variant,
    ) -> None:
        prop = _SIGNAL_TO_PROP.get(signal_name)
        if prop:
            self._pending_props.add(prop)
            self._schedule_debounce()

    def _schedule_debounce(self) -> None:
        if self._debounce_source:
            return
        self._debounce_source = GLib.timeout_add(DEBOUNCE_MS, self._flush_pending)

    def _flush_pending(self) -> bool:
        self._debounce_source = 0
        if self._proxy is None:
            return GLib.SOURCE_REMOVE
        self._push_all_properties()
        self._pending_props.clear()
        return GLib.SOURCE_REMOVE

    def _push_all_properties(self) -> None:
        """Read all cached properties and push to the icon manager."""
        if self._proxy is None:
            return

        props = self._read_cached_properties()
        icon_info = self._build_icon_info(props)
        self._icon_manager.upsert_icon(self._item_id, icon_info)

    def _read_cached_properties(self) -> dict[str, object]:
        """Return a dict of all cached property values from the proxy."""
        result: dict[str, object] = {}
        if self._proxy is None:
            return result
        for name in (
            "Id", "Title", "Status", "Category",
            "IconName", "OverlayIconName", "AttentionIconName",
            "ToolTip", "Menu", "ItemIsMenu",
            "IconAccessibleDesc", "AttentionAccessibleDesc",
            "XAyatanaLabel", "IconThemePath",
        ):
            v = self._proxy.get_cached_property(name)
            if v is not None:
                result[name] = v.unpack()
        return result

    @staticmethod
    def _build_icon_info(props: dict[str, object]) -> dict[str, object]:
        """Translate raw D-Bus properties into the icon-manager dict format."""
        status = props.get("Status", "Active")
        tooltip_raw = props.get("ToolTip")
        tooltip: dict[str, str] | None = None

        if tooltip_raw and isinstance(tooltip_raw, tuple) and len(tooltip_raw) == 4:
            # (icon_name, icon_pixmap, title, body)
            t_icon, _t_pixmap, t_title, t_body = tooltip_raw
            if t_title or t_body:
                tooltip = {"title": t_title or "", "body": t_body or "", "icon_name": t_icon or None}

        # Pick the right icon name based on status.
        if status == "NeedsAttention":
            icon_name = props.get("AttentionIconName") or props.get("IconName", "")
        else:
            icon_name = props.get("IconName", "")

        return {
            "sni_id": props.get("Id", ""),
            "title": props.get("Title", ""),
            "status": status,
            "icon_name": icon_name,
            "icon_theme_path": props.get("IconThemePath"),
            "overlay_icon_name": props.get("OverlayIconName"),
            "tooltip": tooltip,
            "menu_path": props.get("Menu"),
            "item_is_menu": props.get("ItemIsMenu", False),
            "category": props.get("Category", "ApplicationStatus"),
            "accessible_desc": props.get("IconAccessibleDesc", ""),
            "label": props.get("XAyatanaLabel", ""),
            "pinned": True,
        }

    # -- Name owner loss (app exit) ------------------------------------------

    def _on_name_owner_changed(self, proxy: Gio.DBusProxy, _pspec: object) -> None:
        if not proxy.get_name_owner():
            logger.info("Name owner lost for %s", self._item_id)
            GLib.timeout_add(500, self._check_still_gone)

    def _check_still_gone(self) -> bool:
        if self._proxy and not self._proxy.get_name_owner():
            self.destroy()
        return GLib.SOURCE_REMOVE

    # -- Action methods (called via IconManager) ------------------------------

    def activate(self, x: int, y: int) -> None:
        if self._proxy is None:
            return
        self._proxy.call(
            "Activate",
            GLib.Variant("(ii)", (x, y)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    def secondary_activate(self, x: int, y: int) -> None:
        if self._proxy is None:
            return
        self._proxy.call(
            "SecondaryActivate",
            GLib.Variant("(ii)", (x, y)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    def scroll(self, delta: int, orientation: str) -> None:
        if self._proxy is None:
            return
        self._proxy.call(
            "Scroll",
            GLib.Variant("(is)", (delta, orientation)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    def context_menu(self, x: int, y: int) -> None:
        if self._proxy is None:
            return
        self._proxy.call(
            "ContextMenu",
            GLib.Variant("(ii)", (x, y)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    # -- Refresh (re-read everything) ----------------------------------------

    def refresh(self) -> None:
        if self._proxy is not None:
            self._push_all_properties()

    # -- Destroy / cleanup ---------------------------------------------------

    def connect_destroy(self, cb: Callable[[], None]) -> None:
        self._destroy_cb = cb

    def _notify_destroyed(self) -> None:
        self._icon_manager.remove_icon(self._item_id)
        if self._destroy_cb:
            self._destroy_cb()
            self._destroy_cb = None

    def destroy(self) -> None:
        self._cancellable.cancel()
        if self._debounce_source:
            GLib.source_remove(self._debounce_source)
            self._debounce_source = 0
        for sub_id in self._signal_sub_ids:
            self._connection.signal_unsubscribe(sub_id)
        self._signal_sub_ids.clear()
        self._proxy = None
        self._notify_destroyed()
        logger.debug("SNIItemProxy destroyed: %s", self._item_id)
