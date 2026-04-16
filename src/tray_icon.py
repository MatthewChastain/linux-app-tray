"""Individual tray icon widget — handles click / hover / scroll interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

from src.context_menu import ContextMenuBuilder
from src.tooltip_popup import TooltipPopup

if TYPE_CHECKING:
    from src.icon_manager import IconManager

logger = logging.getLogger(__name__)

TOOLTIP_DELAY_MS = 400
TOOLTIP_GRACE_MS = 200
DEFAULT_ICON_SIZE = 20


class TrayIcon(Gtk.Box):
    """A tray icon that wraps an image and reacts to user input."""

    def __init__(self, *, icon_id: str, icon_manager: IconManager) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("tray-icon")
        self.set_focusable(True)

        self._icon_id = icon_id
        self._icon_manager = icon_manager

        # Image widget for the icon.
        self._image = Gtk.Image()
        self._image.set_pixel_size(DEFAULT_ICON_SIZE)
        self.append(self._image)

        # Tooltip popup (created lazily).
        self._tooltip: TooltipPopup | None = None
        self._tooltip_timer: int = 0
        self._tooltip_grace_timer: int = 0

        # Context menu builder.
        self._context_menu: ContextMenuBuilder | None = None

        # -- Gesture controllers -----------------------------------------------

        # Left + right click.
        click = Gtk.GestureClick()
        click.set_button(0)  # all buttons
        click.connect("pressed", self._on_click_pressed)
        self.add_controller(click)

        # Hover (enter / leave).
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_enter)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

        # Scroll.
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
            | Gtk.EventControllerScrollFlags.KINETIC,
        )
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        # Keyboard (Enter / Space / Shift+F10).
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        # Drag source for reordering.
        drag_src = Gtk.DragSource()
        drag_src.connect("prepare", self._on_drag_prepare)
        drag_src.connect("drag-begin", self._on_drag_begin)
        self.add_controller(drag_src)

        # Drop target for reordering.
        drop_target = Gtk.DropTarget(
            actions=Gdk.DragAction.MOVE,
            formats=Gdk.ContentFormats.new(["text/plain"]),
        )
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)

        # Update icon image immediately.
        self._refresh_icon()

        # Listen for updates from the icon manager.
        icon_manager.connect("icon-updated", self._on_icon_updated)

    # -- Properties ----------------------------------------------------------

    @property
    def icon_id(self) -> str:
        return self._icon_id

    # -- Icon rendering ------------------------------------------------------

    def _refresh_icon(self) -> None:
        info = self._icon_manager.get_icon_info(self._icon_id)
        if info is None:
            return
        icon_name = info.get("icon_name")
        icon_pixbuf = info.get("icon_pixbuf")

        if icon_pixbuf is not None:
            self._image.set_from_pixbuf(icon_pixbuf)
        elif icon_name:
            self._image.set_from_icon_name(icon_name)
        else:
            self._image.set_from_icon_name("image-loading-symbolic")

        size = info.get("icon_size", DEFAULT_ICON_SIZE)
        self._image.set_pixel_size(size)

        # Accessibility.
        title = info.get("title", self._icon_id)
        self.set_tooltip_text(title)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL], [title],
        )

        # Attention pulsing.
        if info.get("status") == "NeedsAttention":
            self.add_css_class("needs-attention")
        else:
            self.remove_css_class("needs-attention")

    def _on_icon_updated(self, _mgr: object, icon_id: str) -> None:
        if icon_id == self._icon_id:
            self._refresh_icon()

    # -- Click handling ------------------------------------------------------

    def _on_click_pressed(
        self, gesture: Gtk.GestureClick, _n: int, x: float, y: float,
    ) -> None:
        button = gesture.get_current_button()
        abs_x, abs_y = self._get_abs_coords(x, y)

        if button == Gdk.BUTTON_PRIMARY:
            self._handle_left_click(abs_x, abs_y)
        elif button == Gdk.BUTTON_SECONDARY:
            self._handle_right_click(abs_x, abs_y)
        elif button == Gdk.BUTTON_MIDDLE:
            self._handle_middle_click(abs_x, abs_y)

    def _handle_left_click(self, x: float, y: float) -> None:
        self.add_css_class("active")
        GLib.timeout_add(150, lambda: self.remove_css_class("active") or False)
        self._icon_manager.activate(self._icon_id, int(x), int(y))
        logger.debug("Left-click: %s", self._icon_id)

    def _handle_right_click(self, x: float, y: float) -> None:
        if self._context_menu is None:
            self._context_menu = ContextMenuBuilder(
                icon_id=self._icon_id,
                icon_manager=self._icon_manager,
                parent_widget=self,
            )
        self._context_menu.popup(int(x), int(y))
        logger.debug("Right-click: %s", self._icon_id)

    def _handle_middle_click(self, x: float, y: float) -> None:
        self._icon_manager.secondary_activate(self._icon_id, int(x), int(y))
        logger.debug("Middle-click: %s", self._icon_id)

    # -- Hover / Tooltip -----------------------------------------------------

    def _on_enter(self, _ctrl: Gtk.EventControllerMotion, _x: float, _y: float) -> None:
        self._cancel_tooltip_grace()
        if self._tooltip_timer == 0:
            self._tooltip_timer = GLib.timeout_add(TOOLTIP_DELAY_MS, self._show_tooltip)

    def _on_leave(self, _ctrl: Gtk.EventControllerMotion) -> None:
        self._cancel_tooltip_timer()
        if self._tooltip is not None and self._tooltip.get_visible():
            self._tooltip_grace_timer = GLib.timeout_add(TOOLTIP_GRACE_MS, self._hide_tooltip)

    def _show_tooltip(self) -> bool:
        self._tooltip_timer = 0
        info = self._icon_manager.get_icon_info(self._icon_id)
        if info is None:
            return GLib.SOURCE_REMOVE

        if self._tooltip is None:
            self._tooltip = TooltipPopup()
            self._tooltip.set_parent(self)

        tooltip_data = info.get("tooltip")
        title = info.get("title", self._icon_id)

        if tooltip_data:
            self._tooltip.show_rich(
                title=tooltip_data.get("title", title),
                body=tooltip_data.get("body", ""),
                icon_name=tooltip_data.get("icon_name"),
            )
        else:
            self._tooltip.show_simple(title)

        return GLib.SOURCE_REMOVE

    def _hide_tooltip(self) -> bool:
        self._tooltip_grace_timer = 0
        if self._tooltip is not None:
            self._tooltip.popdown()
        return GLib.SOURCE_REMOVE

    def _cancel_tooltip_timer(self) -> None:
        if self._tooltip_timer:
            GLib.source_remove(self._tooltip_timer)
            self._tooltip_timer = 0

    def _cancel_tooltip_grace(self) -> None:
        if self._tooltip_grace_timer:
            GLib.source_remove(self._tooltip_grace_timer)
            self._tooltip_grace_timer = 0

    # -- Scroll --------------------------------------------------------------

    def _on_scroll(
        self, _ctrl: Gtk.EventControllerScroll, dx: float, dy: float,
    ) -> bool:
        self._icon_manager.scroll(self._icon_id, dx, dy)
        return True

    # -- Keyboard ------------------------------------------------------------

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._handle_left_click(0, 0)
            return True
        if keyval == Gdk.KEY_F10 and (state & Gdk.ModifierType.SHIFT_MASK):
            self._handle_right_click(0, 0)
            return True
        if keyval == Gdk.KEY_Menu:
            self._handle_right_click(0, 0)
            return True
        return False

    # -- Drag & Drop ---------------------------------------------------------

    def _on_drag_prepare(
        self, _src: Gtk.DragSource, _x: float, _y: float,
    ) -> Gdk.ContentProvider | None:
        return Gdk.ContentProvider.new_for_value(self._icon_id)

    def _on_drag_begin(self, src: Gtk.DragSource, _drag: Gdk.Drag) -> None:
        icon = Gtk.WidgetPaintable(widget=self)
        src.set_icon(icon, 0, 0)

    def _on_drop(
        self,
        _target: Gtk.DropTarget,
        value: object,
        _x: float,
        _y: float,
    ) -> bool:
        source_id = str(value)
        if source_id and source_id != self._icon_id:
            self._icon_manager.reorder(source_id, before=self._icon_id)
            return True
        return False

    # -- Helpers -------------------------------------------------------------

    def _get_abs_coords(self, local_x: float, local_y: float) -> tuple[float, float]:
        """Convert widget-local coords to absolute screen coords (best effort)."""
        # In GTK4 there is no trivial absolute-position API; return local coords
        # as a reasonable fallback for SNI Activate(x, y).
        return local_x, local_y
