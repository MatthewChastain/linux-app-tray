"""Gtk.Application subclass that manages the tray lifetime."""

from __future__ import annotations

import logging
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from src.icon_manager import IconManager
from src.tray_window import TrayWindow
from src.dbus.sni_watcher import StatusNotifierWatcher

logger = logging.getLogger(__name__)

APP_ID = "org.linuxapptray.App"
CSS_PATH = Path(__file__).resolve().parent.parent / "data" / "style.css"


class TrayApplication(Adw.Application):
    """Single-instance application that hosts the tray bar."""

    def __init__(self, *, position: str = "bottom", monitor: str = "primary") -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._position = position
        self._monitor = monitor
        self._window: TrayWindow | None = None
        self._icon_manager: IconManager | None = None
        self._sni_watcher: StatusNotifierWatcher | None = None

    # -- Gtk.Application overrides -------------------------------------------

    def do_startup(self) -> None:  # noqa: D401
        """Called once before any windows are shown."""
        Adw.Application.do_startup(self)
        self._load_css()
        logger.debug("Application startup complete")

    def do_activate(self) -> None:  # noqa: D401
        """Called on first activation and when a second instance is launched."""
        if self._window is not None:
            self._window.present()
            return

        self._icon_manager = IconManager()

        self._sni_watcher = StatusNotifierWatcher(icon_manager=self._icon_manager)

        self._window = TrayWindow(
            application=self,
            icon_manager=self._icon_manager,
            position=self._position,
            monitor_name=self._monitor,
        )
        self._window.present()
        logger.info("Tray window presented")

    def do_shutdown(self) -> None:  # noqa: D401
        """Clean up resources before the process exits."""
        logger.info("Shutting down")
        if self._sni_watcher is not None:
            self._sni_watcher.destroy()
            self._sni_watcher = None
        if self._icon_manager is not None:
            self._icon_manager.destroy()
            self._icon_manager = None
        Adw.Application.do_shutdown(self)

    # -- internal helpers ----------------------------------------------------

    def _load_css(self) -> None:
        if not CSS_PATH.is_file():
            logger.warning("CSS file not found at %s", CSS_PATH)
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(CSS_PATH))
        Gtk.StyleContext.add_provider_for_display(
            self.get_default().get_style_manager().get_display()
            if hasattr(Adw.Application, "get_default")
            else self.get_active_window().get_display()
            if self.get_active_window()
            else None,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        logger.debug("Loaded CSS from %s", CSS_PATH)
