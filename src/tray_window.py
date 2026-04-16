"""Main tray bar window that lives at a screen edge."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

from src.overflow_popover import OverflowPopover
from src.tray_icon import TrayIcon

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

# Try to load gtk4-layer-shell for Wayland positioning.
try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell  # type: ignore[attr-defined]

    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False
    logger.info("gtk4-layer-shell not available; falling back to plain window")


class TrayWindow(Gtk.Window):
    """A thin bar anchored to a screen edge containing tray icons."""

    def __init__(
        self,
        *,
        application: Gtk.Application,
        icon_manager: IconManager,
        position: str = "bottom",
        monitor_name: str = "primary",
    ) -> None:
        super().__init__(application=application)
        self.set_title("Linux App Tray")
        self.add_css_class("tray-window")

        self._icon_manager = icon_manager
        self._position = position
        self._monitor_name = monitor_name
        self._icon_widgets: dict[str, TrayIcon] = {}

        # -- Layer-shell setup (Wayland) or fallback hints --------------------
        if HAS_LAYER_SHELL and Gtk4LayerShell.is_supported():
            self._setup_layer_shell()
        else:
            self._setup_fallback_window()

        # -- Layout: [icons …] [chevron] -------------------------------------
        self._outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._outer_box.set_halign(Gtk.Align.CENTER)
        self._outer_box.set_valign(Gtk.Align.CENTER)

        self._icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._outer_box.append(self._icon_box)

        # Overflow chevron
        self._overflow = OverflowPopover(icon_manager=icon_manager)
        self._outer_box.append(self._overflow)

        self.set_child(self._outer_box)

        # -- React to icon changes -------------------------------------------
        icon_manager.connect("icon-added", self._on_icon_added)
        icon_manager.connect("icon-removed", self._on_icon_removed)
        icon_manager.connect("layout-changed", self._on_layout_changed)

        # -- Keyboard controller for tray-level navigation -------------------
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    # -- Layer-shell vs fallback window hints --------------------------------

    def _setup_layer_shell(self) -> None:
        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.auto_exclusive_zone_enable(self)

        if self._position == "top":
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        else:
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, True)

        # Centre horizontally.
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)

        logger.debug("Layer-shell configured (position=%s)", self._position)

    def _setup_fallback_window(self) -> None:
        """Plain X11 / fallback: keep on top, skip taskbar."""
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(300, 40)

    # -- Icon add/remove callbacks -------------------------------------------

    def _on_icon_added(self, _mgr: IconManager, icon_id: str) -> None:
        if icon_id in self._icon_widgets:
            return
        info = self._icon_manager.get_icon_info(icon_id)
        if info is None:
            return
        widget = TrayIcon(icon_id=icon_id, icon_manager=self._icon_manager)
        self._icon_widgets[icon_id] = widget
        if info.get("pinned", True):
            self._icon_box.append(widget)
        else:
            self._overflow.add_overflow_icon(widget)
        self._update_overflow_visibility()
        logger.debug("Icon widget added: %s", icon_id)

    def _on_icon_removed(self, _mgr: IconManager, icon_id: str) -> None:
        widget = self._icon_widgets.pop(icon_id, None)
        if widget is None:
            return
        parent = widget.get_parent()
        if parent is not None:
            parent.remove(widget)
        self._update_overflow_visibility()
        logger.debug("Icon widget removed: %s", icon_id)

    def _on_layout_changed(self, _mgr: IconManager) -> None:
        """Re-sort visible icons and reassign overflow."""
        # Remove all icon children and re-add in order.
        while True:
            child = self._icon_box.get_first_child()
            if child is None:
                break
            self._icon_box.remove(child)

        self._overflow.clear_overflow_icons()

        for icon_id in self._icon_manager.ordered_ids():
            widget = self._icon_widgets.get(icon_id)
            if widget is None:
                continue
            info = self._icon_manager.get_icon_info(icon_id)
            if info and info.get("pinned", True):
                self._icon_box.append(widget)
            else:
                self._overflow.add_overflow_icon(widget)

        self._update_overflow_visibility()

    def _update_overflow_visibility(self) -> None:
        has_hidden = self._overflow.has_icons()
        self._overflow.set_visible(has_hidden)

    # -- Keyboard handling ---------------------------------------------------

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._overflow.close()
            return True
        return False
