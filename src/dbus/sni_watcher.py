"""StatusNotifierWatcher D-Bus service.

Owns ``org.kde.StatusNotifierWatcher`` on the session bus and keeps track of
every registered StatusNotifierItem.  When items appear or disappear the
corresponding signals are emitted and the central :class:`IconManager` is
updated.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from gi.repository import Gio, GLib

from src.dbus.interfaces import STATUS_NOTIFIER_WATCHER_XML
from src.dbus.sni_item_proxy import SNIItemProxy

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

WATCHER_BUS_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_OBJECT_PATH = "/StatusNotifierWatcher"
DEFAULT_ITEM_OBJECT_PATH = "/StatusNotifierItem"
BUS_ADDRESS_RE = re.compile(r"^[a-zA-Z_][\w.-]*$")


class StatusNotifierWatcher:
    """Owns the StatusNotifierWatcher bus name and manages item proxies."""

    def __init__(self, *, icon_manager: IconManager) -> None:
        self._icon_manager = icon_manager
        self._items: dict[str, SNIItemProxy] = {}
        self._name_owner_id: int = 0
        self._registration_id: int = 0
        self._cancellable = Gio.Cancellable()

        # Parse the interface XML.
        node_info = Gio.DBusNodeInfo.new_for_xml(STATUS_NOTIFIER_WATCHER_XML)
        self._iface_info = node_info.interfaces[0]

        # Export the object on the session bus.
        bus = Gio.BusType.SESSION
        try:
            self._connection = Gio.bus_get_sync(bus, None)
            self._registration_id = self._connection.register_object(
                WATCHER_OBJECT_PATH,
                self._iface_info,
                self._on_method_call,
                self._on_get_property,
                None,  # set_property not needed
            )
        except GLib.Error as exc:
            logger.error("Failed to export watcher object: %s", exc.message)
            return

        # Own the well-known bus name.
        self._name_owner_id = Gio.bus_own_name_on_connection(
            self._connection,
            WATCHER_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_name_acquired,
            self._on_name_lost,
        )

        # Announce ourselves as a host.
        self._emit_signal("StatusNotifierHostRegistered", None)

        # Discover items already on the bus.
        GLib.idle_add(self._discover_existing_items)

    # -- D-Bus method dispatch ------------------------------------------------

    def _on_method_call(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _iface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method_name == "RegisterStatusNotifierItem":
            service = parameters.unpack()[0]
            sender = invocation.get_sender()
            try:
                self._register_item(service, sender)
                invocation.return_value(None)
            except Exception as exc:  # noqa: BLE001
                invocation.return_dbus_error(
                    "org.freedesktop.DBus.Error.Failed", str(exc),
                )
        elif method_name == "RegisterStatusNotifierHost":
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.NotSupported",
                "Registering additional hosts is not supported",
            )
        else:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod",
                f"Unknown method: {method_name}",
            )

    def _on_get_property(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _object_path: str,
        _iface_name: str,
        property_name: str,
    ) -> GLib.Variant:
        if property_name == "RegisteredStatusNotifierItems":
            return GLib.Variant("as", list(self._items.keys()))
        if property_name == "IsStatusNotifierHostRegistered":
            return GLib.Variant("b", True)
        if property_name == "ProtocolVersion":
            return GLib.Variant("i", 0)
        return GLib.Variant("s", "")

    # -- Registration / unregistration ----------------------------------------

    def _register_item(self, service: str, sender: str) -> None:
        """Register a StatusNotifierItem given *service* (path or bus name)."""
        bus_name: str
        obj_path: str

        if service.startswith("/"):
            # Ayatana-style: the service is an object path.
            bus_name = sender
            obj_path = service
        elif BUS_ADDRESS_RE.match(service):
            # KDE-style: the service is a well-known bus name.
            bus_name = service
            obj_path = DEFAULT_ITEM_OBJECT_PATH
        else:
            raise ValueError(f"Cannot parse service string: {service!r}")

        item_id = f"{bus_name}{obj_path}"

        if item_id in self._items:
            logger.debug("Item %s already registered; resetting", item_id)
            self._items[item_id].refresh()
            return

        logger.info("Registering item %s", item_id)
        proxy = SNIItemProxy(
            bus_name=bus_name,
            object_path=obj_path,
            connection=self._connection,
            icon_manager=self._icon_manager,
            cancellable=self._cancellable,
        )
        proxy.connect_destroy(lambda: self._on_item_destroyed(item_id))
        self._items[item_id] = proxy

        self._emit_signal(
            "StatusNotifierItemRegistered", GLib.Variant("(s)", (item_id,)),
        )
        self._emit_property_changed(
            "RegisteredStatusNotifierItems",
            GLib.Variant("as", list(self._items.keys())),
        )

    def _on_item_destroyed(self, item_id: str) -> None:
        if item_id not in self._items:
            return
        del self._items[item_id]
        logger.info("Item removed: %s", item_id)
        self._emit_signal(
            "StatusNotifierItemUnregistered", GLib.Variant("(s)", (item_id,)),
        )
        self._emit_property_changed(
            "RegisteredStatusNotifierItems",
            GLib.Variant("as", list(self._items.keys())),
        )

    # -- Discover existing items on startup -----------------------------------

    def _discover_existing_items(self) -> bool:
        """Introspect the session bus to find pre-existing SNI items."""
        try:
            result = self._connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListNames",
                None,
                GLib.VariantType("(as)"),
                Gio.DBusCallFlags.NONE,
                -1,
                self._cancellable,
            )
            names = result.unpack()[0]
            for name in names:
                if "StatusNotifierItem" in name:
                    self._try_register_by_name(name)
        except GLib.Error as exc:
            logger.warning("Failed to discover existing items: %s", exc.message)
        return GLib.SOURCE_REMOVE

    def _try_register_by_name(self, name: str) -> None:
        """Attempt to register a bus name that looks like an SNI item."""
        item_id = f"{name}{DEFAULT_ITEM_OBJECT_PATH}"
        if item_id in self._items:
            return
        try:
            self._register_item(name, name)
        except Exception:  # noqa: BLE001
            logger.debug("Could not register %s", name, exc_info=True)

    # -- Bus name ownership callbacks -----------------------------------------

    def _on_name_acquired(self, _conn: Gio.DBusConnection, _name: str) -> None:
        logger.info("Acquired bus name %s", WATCHER_BUS_NAME)

    def _on_name_lost(self, _conn: Gio.DBusConnection, _name: str) -> None:
        logger.warning("Lost bus name %s", WATCHER_BUS_NAME)

    # -- Signal / property helpers --------------------------------------------

    def _emit_signal(self, signal_name: str, parameters: GLib.Variant | None) -> None:
        try:
            self._connection.emit_signal(
                None,
                WATCHER_OBJECT_PATH,
                "org.kde.StatusNotifierWatcher",
                signal_name,
                parameters,
            )
        except GLib.Error as exc:
            logger.warning("Failed to emit %s: %s", signal_name, exc.message)

    def _emit_property_changed(self, prop: str, value: GLib.Variant) -> None:
        changed = GLib.Variant("a{sv}", {prop: value})
        invalidated = GLib.Variant("as", [])
        params = GLib.Variant(
            "(sa{sv}as)", ("org.kde.StatusNotifierWatcher", changed.unpack(), []),
        )
        try:
            self._connection.emit_signal(
                None,
                WATCHER_OBJECT_PATH,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                params,
            )
        except GLib.Error as exc:
            logger.warning("Failed to emit PropertiesChanged: %s", exc.message)

    # -- Cleanup --------------------------------------------------------------

    def destroy(self) -> None:
        self._cancellable.cancel()
        for proxy in list(self._items.values()):
            proxy.destroy()
        self._items.clear()
        if self._registration_id:
            try:
                self._connection.unregister_object(self._registration_id)
            except GLib.Error:
                pass
            self._registration_id = 0
        if self._name_owner_id:
            Gio.bus_unown_name(self._name_owner_id)
            self._name_owner_id = 0
        logger.debug("StatusNotifierWatcher destroyed")
