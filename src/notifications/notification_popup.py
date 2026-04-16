"""Visual notification popup widget (balloon / toast) for the tray."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

if TYPE_CHECKING:
    from src.notifications.notification_manager import Notification, NotificationManager


class NotificationPopup(Gtk.Box):
    """A popup banner shown above the tray to display a notification."""

    def __init__(self, *, notification_manager: NotificationManager) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add_css_class("notification-popup")
        self._manager = notification_manager

        # Icon.
        self._icon = Gtk.Image()
        self._icon.set_pixel_size(32)
        self._icon.set_visible(False)
        self.append(self._icon)

        # Text area.
        self._text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._text_box.set_hexpand(True)
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.add_css_class("heading")
        self._body_label = Gtk.Label(xalign=0, wrap=True, max_width_chars=50)
        self._body_label.set_visible(False)
        self._text_box.append(self._title_label)
        self._text_box.append(self._body_label)
        self.append(self._text_box)

        # Close button.
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_btn.add_css_class("flat")
        close_btn.set_valign(Gtk.Align.START)
        close_btn.connect("clicked", lambda _b: self._manager.dismiss_current())
        self.append(close_btn)

        # Click on the body triggers the action.
        click = Gtk.GestureClick()
        click.connect("pressed", lambda _g, _n, _x, _y: self._manager.on_click())
        self.add_controller(click)

        self.set_visible(False)

    def show_notification(self, notification: Notification) -> None:
        """Display *notification* in the popup."""
        self._title_label.set_text(notification.title)

        if notification.body:
            self._body_label.set_text(notification.body)
            self._body_label.set_visible(True)
        else:
            self._body_label.set_visible(False)

        if notification.icon_name:
            self._icon.set_from_icon_name(notification.icon_name)
            self._icon.set_visible(True)
        else:
            self._icon.set_visible(False)

        self.set_visible(True)

    def hide_notification(self) -> None:
        self.set_visible(False)
