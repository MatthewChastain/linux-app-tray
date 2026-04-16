"""Right-click context menu builder backed by DBusMenu."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk

from src.dbus.dbus_menu_proxy import DBusMenuClient

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)


class ContextMenuBuilder:
    """Builds and shows a ``Gtk.PopoverMenu`` from a remote DBusMenu."""

    def __init__(
        self,
        *,
        icon_id: str,
        icon_manager: IconManager,
        parent_widget: Gtk.Widget,
    ) -> None:
        self._icon_id = icon_id
        self._icon_manager = icon_manager
        self._parent = parent_widget
        self._popover: Gtk.PopoverMenu | None = None
        self._dbus_client: DBusMenuClient | None = None
        self._action_group = Gio.SimpleActionGroup()

    def popup(self, x: int, y: int) -> None:
        """Show the context menu at (x, y) relative to the parent widget."""
        info = self._icon_manager.get_icon_info(self._icon_id)
        if info is None:
            return

        menu_path = info.get("menu_path")
        bus_name = self._icon_id.split("/")[0] if "/" in self._icon_id else self._icon_id

        if not menu_path or menu_path == "/NO_DBUSMENU":
            logger.debug("No DBusMenu for %s", self._icon_id)
            return

        # Extract the bus name from the icon_id (format: "bus_name/object_path").
        bus_name_part = self._icon_id
        if "/" in self._icon_id:
            bus_name_part = self._icon_id[: self._icon_id.index("/")]

        connection = self._icon_manager.get_connection()
        if connection is None:
            return

        if self._dbus_client is None:
            self._dbus_client = DBusMenuClient(
                bus_name=bus_name_part,
                menu_object_path=menu_path,
                connection=connection,
                on_menu_changed=self._on_menu_ready,
            )
        else:
            self._dbus_client.refresh()

    def _on_menu_ready(self, menu: Gio.Menu) -> None:
        """Called when the DBusMenu layout is fetched/updated."""
        # Install action group for menu items.
        self._action_group = Gio.SimpleActionGroup()
        self._install_actions(menu)
        self._parent.insert_action_group("dbusmenu", self._action_group)

        if self._popover is not None:
            self._popover.unparent()

        self._popover = Gtk.PopoverMenu.new_from_model(menu)
        self._popover.set_parent(self._parent)
        self._popover.set_has_arrow(False)
        self._popover.popup()
        logger.debug("Context menu shown for %s", self._icon_id)

    def _install_actions(self, menu: Gio.Menu) -> None:
        """Create a SimpleAction for each item-N action referenced in *menu*."""
        n = menu.get_n_items()
        for i in range(n):
            action_name = None
            target = menu.get_item_attribute_value(i, "action", GLib.VariantType("s"))
            if target:
                action_name = target.get_string()

            if action_name and action_name.startswith("dbusmenu."):
                short = action_name.removeprefix("dbusmenu.")
                # Extract item id from "item-<id>".
                m = re.match(r"item-(\d+)", short)
                if m:
                    item_id = int(m.group(1))
                    action = Gio.SimpleAction.new(short, None)
                    action.connect("activate", self._on_action_activated, item_id)
                    self._action_group.add_action(action)

            submenu = menu.get_item_link(i, Gio.MENU_LINK_SUBMENU)
            if submenu:
                self._install_actions(submenu)

            section = menu.get_item_link(i, Gio.MENU_LINK_SECTION)
            if section:
                self._install_actions(section)

    def _on_action_activated(
        self, _action: Gio.SimpleAction, _param: GLib.Variant | None, item_id: int,
    ) -> None:
        logger.debug("Menu action activated: item %d for %s", item_id, self._icon_id)
        if self._dbus_client:
            self._dbus_client.send_event(item_id)
        if self._popover:
            self._popover.popdown()

    def destroy(self) -> None:
        if self._dbus_client:
            self._dbus_client.destroy()
            self._dbus_client = None
        if self._popover:
            self._popover.unparent()
            self._popover = None
