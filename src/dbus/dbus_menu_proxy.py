"""Client for the com.canonical.dbusmenu protocol.

Fetches the menu layout from a remote app and builds a :class:`Gio.Menu` tree
that GTK can consume directly.
"""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gio, GLib

from src.dbus.interfaces import DBUS_MENU_XML

logger = logging.getLogger(__name__)

DBUS_MENU_IFACE = "com.canonical.dbusmenu"


class DBusMenuClient:
    """Fetches and tracks a com.canonical.dbusmenu tree from a remote app."""

    def __init__(
        self,
        *,
        bus_name: str,
        menu_object_path: str,
        connection: Gio.DBusConnection,
        on_menu_changed: Callable[[Gio.Menu], None] | None = None,
    ) -> None:
        self._bus_name = bus_name
        self._object_path = menu_object_path
        self._connection = connection
        self._on_menu_changed = on_menu_changed
        self._cancellable = Gio.Cancellable()
        self._proxy: Gio.DBusProxy | None = None
        self._menu = Gio.Menu()
        self._revision: int = 0
        self._signal_sub_ids: list[int] = []

        node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_MENU_XML)
        iface_info = node_info.interfaces[0]

        Gio.DBusProxy.new(
            connection,
            Gio.DBusProxyFlags.NONE,
            iface_info,
            bus_name,
            menu_object_path,
            DBUS_MENU_IFACE,
            self._cancellable,
            self._on_proxy_ready,
        )

    @property
    def menu(self) -> Gio.Menu:
        return self._menu

    # -- Proxy ready ----------------------------------------------------------

    def _on_proxy_ready(self, _src: object, result: Gio.AsyncResult) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_finish(result)
        except GLib.Error as exc:
            logger.warning("DBusMenu proxy creation failed: %s", exc.message)
            return

        # Subscribe to layout/property update signals.
        for sig in ("LayoutUpdated", "ItemsPropertiesUpdated"):
            sub = self._connection.signal_subscribe(
                self._bus_name, DBUS_MENU_IFACE, sig,
                self._object_path, None, Gio.DBusSignalFlags.NONE,
                self._on_menu_signal,
            )
            self._signal_sub_ids.append(sub)

        self.refresh()
        logger.debug("DBusMenu proxy ready for %s:%s", self._bus_name, self._object_path)

    def _on_menu_signal(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _iface: str,
        signal_name: str,
        _params: GLib.Variant,
    ) -> None:
        # Both signals mean "the menu tree may have changed".
        self.refresh()

    # -- Fetch layout ---------------------------------------------------------

    def refresh(self) -> None:
        """Re-fetch the full layout from the root."""
        if self._proxy is None:
            return
        self._proxy.call(
            "GetLayout",
            GLib.Variant("(iias)", (0, -1, [])),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            self._on_layout_received,
        )

    def _on_layout_received(self, proxy: Gio.DBusProxy, result: Gio.AsyncResult) -> None:
        try:
            variant = proxy.call_finish(result)
        except GLib.Error as exc:
            logger.warning("GetLayout failed: %s", exc.message)
            return

        revision, layout = variant.unpack()
        self._revision = revision
        self._menu.remove_all()
        self._parse_node(layout, self._menu)

        if self._on_menu_changed:
            self._on_menu_changed(self._menu)

    # -- Recursive layout parsing ---------------------------------------------

    def _parse_node(self, node: tuple, menu: Gio.Menu) -> None:
        """Parse a ``(ia{sv}av)`` node into *menu*."""
        item_id, props, children = node

        for child_variant in children:
            child = child_variant.unpack() if hasattr(child_variant, "unpack") else child_variant
            child_id, child_props, child_children = child

            item_type = self._prop_str(child_props, "type", "")
            visible = self._prop_bool(child_props, "visible", True)
            if not visible:
                continue

            if item_type == "separator":
                # Gio.Menu doesn't have separators natively; use a section.
                section = Gio.Menu()
                menu.append_section(None, section)
                continue

            label = self._prop_str(child_props, "label", "").replace("_", "")
            toggle_type = self._prop_str(child_props, "toggle-type", "")
            toggle_state = self._prop_int(child_props, "toggle-state", -1)
            enabled = self._prop_bool(child_props, "enabled", True)
            children_present = self._prop_str(child_props, "children-display", "")

            action_name = f"dbusmenu.item-{child_id}"
            menu_item = Gio.MenuItem.new(label, action_name)

            if toggle_type == "checkmark":
                menu_item.set_attribute_value(
                    "toggle-type", GLib.Variant("s", "checkmark"),
                )
                menu_item.set_attribute_value(
                    "toggle-state", GLib.Variant("i", toggle_state),
                )
            elif toggle_type == "radio":
                menu_item.set_attribute_value(
                    "toggle-type", GLib.Variant("s", "radio"),
                )
                menu_item.set_attribute_value(
                    "toggle-state", GLib.Variant("i", toggle_state),
                )

            # Recurse into submenus.
            if child_children and children_present == "submenu":
                submenu = Gio.Menu()
                self._parse_node(child, submenu)
                menu_item.set_submenu(submenu)

            menu.append_item(menu_item)

    # -- Invoke menu events ---------------------------------------------------

    def send_event(self, item_id: int, event: str = "clicked") -> None:
        """Send an Event to the remote menu (e.g. item clicked)."""
        if self._proxy is None:
            return
        self._proxy.call(
            "Event",
            GLib.Variant("(isvu)", (item_id, event, GLib.Variant("s", ""), 0)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    def about_to_show(self, item_id: int) -> None:
        """Notify the app that we are about to display *item_id*."""
        if self._proxy is None:
            return
        self._proxy.call(
            "AboutToShow",
            GLib.Variant("(i)", (item_id,)),
            Gio.DBusCallFlags.NONE,
            -1,
            self._cancellable,
            None,
        )

    # -- Property helpers -----------------------------------------------------

    @staticmethod
    def _prop_str(props: dict, key: str, default: str = "") -> str:
        v = props.get(key)
        if v is None:
            return default
        return v.get_string() if hasattr(v, "get_string") else str(v)

    @staticmethod
    def _prop_bool(props: dict, key: str, default: bool = True) -> bool:
        v = props.get(key)
        if v is None:
            return default
        return v.get_boolean() if hasattr(v, "get_boolean") else bool(v)

    @staticmethod
    def _prop_int(props: dict, key: str, default: int = 0) -> int:
        v = props.get(key)
        if v is None:
            return default
        return v.get_int32() if hasattr(v, "get_int32") else int(v)

    # -- Cleanup --------------------------------------------------------------

    def destroy(self) -> None:
        self._cancellable.cancel()
        for sub in self._signal_sub_ids:
            self._connection.signal_unsubscribe(sub)
        self._signal_sub_ids.clear()
        self._proxy = None
        logger.debug("DBusMenuClient destroyed for %s", self._bus_name)
