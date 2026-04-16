"""Tooltip popup for tray icons — supports simple text and rich (title + body + icon)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


class TooltipPopup(Gtk.Popover):
    """A small popover tooltip that appears above a tray icon on hover."""

    def __init__(self) -> None:
        super().__init__()
        self.add_css_class("tooltip-popup")
        self.set_autohide(False)
        self.set_has_arrow(True)
        self.set_can_focus(False)

        # Content box.
        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._icon = Gtk.Image()
        self._icon.set_pixel_size(16)
        self._icon.set_visible(False)

        self._text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.add_css_class("heading")
        self._body_label = Gtk.Label(xalign=0, wrap=True, max_width_chars=40)
        self._body_label.set_visible(False)

        self._text_box.append(self._title_label)
        self._text_box.append(self._body_label)
        self._box.append(self._icon)
        self._box.append(self._text_box)

        self.set_child(self._box)

    def show_simple(self, text: str) -> None:
        """Show a single-line tooltip."""
        self._title_label.set_text(text)
        self._body_label.set_visible(False)
        self._icon.set_visible(False)
        self.popup()

    def show_rich(
        self,
        *,
        title: str,
        body: str = "",
        icon_name: str | None = None,
    ) -> None:
        """Show a rich tooltip with title, body, and optional icon."""
        self._title_label.set_text(title)

        if body:
            self._body_label.set_text(body)
            self._body_label.set_visible(True)
        else:
            self._body_label.set_visible(False)

        if icon_name:
            self._icon.set_from_icon_name(icon_name)
            self._icon.set_visible(True)
        else:
            self._icon.set_visible(False)

        self.popup()
