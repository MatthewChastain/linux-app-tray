"""Overflow chevron + popup that holds non-pinned tray icons."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

GRID_COLUMNS = 4


class OverflowPopover(Gtk.Box):
    """A chevron button that toggles a popover containing hidden tray icons.

    Behaviour follows the Windows reference:
    - Stays open until: chevron re-click, click outside, Escape, focus loss.
    - Does NOT close on: hover inside, right-click (context menu stays above).
    - Closes AFTER: left-click action completes, or context menu item is selected.
    """

    def __init__(self, *, icon_manager: IconManager) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._icon_manager = icon_manager

        # -- Chevron button ---------------------------------------------------
        self._chevron = Gtk.Button()
        self._chevron.add_css_class("overflow-button")
        self._chevron.set_icon_name("pan-up-symbolic")
        self._chevron.set_focusable(True)
        self._chevron.set_tooltip_text("Show hidden icons")
        self._chevron.connect("clicked", self._on_chevron_clicked)
        self.append(self._chevron)

        # -- Popover containing the icon grid ---------------------------------
        self._popover = Gtk.Popover()
        self._popover.set_parent(self._chevron)
        self._popover.set_autohide(True)
        self._popover.set_has_arrow(True)
        self._popover.add_css_class("overflow-popup")

        self._grid = Gtk.FlowBox()
        self._grid.set_max_children_per_line(GRID_COLUMNS)
        self._grid.set_min_children_per_line(1)
        self._grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self._grid.set_homogeneous(True)
        self._popover.set_child(self._grid)

        # Track open state.
        self._popover.connect("closed", self._on_popover_closed)

        # Drop target for pinning/unpinning via drag.
        drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.MOVE,
            formats=Gdk.ContentFormats.new(["text/plain"]),
        )
        drop_target.connect("drop", self._on_drop)
        self._grid.add_controller(drop_target)

    # -- Public API -----------------------------------------------------------

    def add_overflow_icon(self, widget: Gtk.Widget) -> None:
        """Add an icon widget to the overflow popup grid."""
        self._grid.insert(widget, -1)

    def clear_overflow_icons(self) -> None:
        """Remove all icon widgets from the overflow popup grid."""
        while True:
            child = self._grid.get_first_child()
            if child is None:
                break
            self._grid.remove(child)

    def has_icons(self) -> bool:
        """Return True if there is at least one icon in the overflow."""
        return self._grid.get_first_child() is not None

    def close(self) -> None:
        """Programmatically close the overflow popup."""
        self._popover.popdown()

    # -- Callbacks ------------------------------------------------------------

    def _on_chevron_clicked(self, _btn: Gtk.Button) -> None:
        if self._popover.get_visible():
            self._popover.popdown()
        else:
            self._popover.popup()
            logger.debug("Overflow popup opened")

    def _on_popover_closed(self, _popover: Gtk.Popover) -> None:
        logger.debug("Overflow popup closed")

    # -- Drag & Drop: drop into overflow to unpin ----------------------------

    def _on_drop(
        self,
        _target: Gtk.DropTarget,
        value: object,
        _x: float,
        _y: float,
    ) -> bool:
        icon_id = str(value)
        if icon_id:
            self._icon_manager.set_pinned(icon_id, False)
            return True
        return False
