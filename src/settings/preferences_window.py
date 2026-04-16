"""GTK4 / libadwaita preferences window for Linux App Tray."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

if TYPE_CHECKING:
    from src.settings.settings_manager import SettingsManager


class PreferencesWindow(Adw.PreferencesWindow):
    """A settings dialog with grouped rows for all configurable options."""

    def __init__(self, *, settings: SettingsManager, **kwargs: object) -> None:
        super().__init__(title="Linux App Tray — Preferences", **kwargs)
        self._settings = settings

        self._build_general_page()
        self._build_appearance_page()

    # -- General page ---------------------------------------------------------

    def _build_general_page(self) -> None:
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        group = Adw.PreferencesGroup(title="Behaviour")

        # Position.
        pos_row = Adw.ComboRow(title="Tray position")
        pos_model = Gtk.StringList.new(["bottom", "top"])
        pos_row.set_model(pos_model)
        current_pos = self._settings.get_string("position")
        pos_row.set_selected(0 if current_pos == "bottom" else 1)
        pos_row.connect("notify::selected", lambda r, _p: self._settings.set_value(
            "position", "top" if r.get_selected() == 1 else "bottom",
        ))
        group.add(pos_row)

        # Max visible icons.
        max_row = Adw.SpinRow.new_with_range(1, 30, 1)
        max_row.set_title("Max visible icons")
        max_row.set_value(self._settings.get_int("max_visible_icons"))
        max_row.connect("notify::value", lambda r, _p: self._settings.set_value(
            "max_visible_icons", int(r.get_value()),
        ))
        group.add(max_row)

        # Always show all.
        all_row = Adw.SwitchRow(title="Always show all icons")
        all_row.set_active(self._settings.get_bool("always_show_all_icons"))
        all_row.connect("notify::active", lambda r, _p: self._settings.set_value(
            "always_show_all_icons", r.get_active(),
        ))
        group.add(all_row)

        # Legacy XEmbed.
        legacy_row = Adw.SwitchRow(title="Legacy tray icon support (X11)")
        legacy_row.set_active(self._settings.get_bool("legacy_xembed"))
        legacy_row.connect("notify::active", lambda r, _p: self._settings.set_value(
            "legacy_xembed", r.get_active(),
        ))
        group.add(legacy_row)

        page.add(group)
        self.add(page)

    # -- Appearance page ------------------------------------------------------

    def _build_appearance_page(self) -> None:
        page = Adw.PreferencesPage(title="Appearance", icon_name="applications-graphics-symbolic")
        group = Adw.PreferencesGroup(title="Icons")

        # Icon size.
        size_row = Adw.ComboRow(title="Icon size")
        size_model = Gtk.StringList.new(["16", "20", "24", "32"])
        size_row.set_model(size_model)
        current_size = self._settings.get_int("icon_size")
        size_map = {16: 0, 20: 1, 24: 2, 32: 3}
        size_row.set_selected(size_map.get(current_size, 1))
        size_row.connect("notify::selected", lambda r, _p: self._settings.set_value(
            "icon_size", [16, 20, 24, 32][r.get_selected()],
        ))
        group.add(size_row)

        # Theme.
        theme_row = Adw.ComboRow(title="Theme")
        theme_model = Gtk.StringList.new(["system", "dark", "light"])
        theme_row.set_model(theme_model)
        current_theme = self._settings.get_string("theme")
        theme_map = {"system": 0, "dark": 1, "light": 2}
        theme_row.set_selected(theme_map.get(current_theme, 0))
        theme_row.connect("notify::selected", lambda r, _p: self._settings.set_value(
            "theme", ["system", "dark", "light"][r.get_selected()],
        ))
        group.add(theme_row)

        page.add(group)
        self.add(page)
