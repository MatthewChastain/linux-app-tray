"""Settings manager — reads and writes the app's JSON configuration file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from gi.repository import GObject

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "linux-app-tray"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "position": "bottom",
    "monitor": "primary",
    "max_visible_icons": 6,
    "always_show_all_icons": False,
    "icon_size": 20,
    "theme": "system",
    "keyboard_shortcut": "Super+B",
    "legacy_xembed": True,
    "per_app": {},  # icon_id → {"notifications": bool}
}


class SettingsManager(GObject.Object):
    """Provides typed access to the application configuration.

    Emits ``changed`` whenever a setting is updated.
    """

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),  # key name
    }

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    # -- Typed getters --------------------------------------------------------

    def get_string(self, key: str) -> str:
        return str(self._data.get(key, DEFAULTS.get(key, "")))

    def get_int(self, key: str) -> int:
        return int(self._data.get(key, DEFAULTS.get(key, 0)))

    def get_bool(self, key: str) -> bool:
        return bool(self._data.get(key, DEFAULTS.get(key, False)))

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    # -- Setter ---------------------------------------------------------------

    def set_value(self, key: str, value: Any) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self._save()
        self.emit("changed", key)

    # -- Per-app settings -----------------------------------------------------

    def get_app_setting(self, icon_id: str, key: str, default: Any = None) -> Any:
        per_app = self._data.get("per_app", {})
        app_cfg = per_app.get(icon_id, {})
        return app_cfg.get(key, default)

    def set_app_setting(self, icon_id: str, key: str, value: Any) -> None:
        per_app = self._data.setdefault("per_app", {})
        app_cfg = per_app.setdefault(icon_id, {})
        app_cfg[key] = value
        self._save()
        self.emit("changed", f"per_app.{icon_id}.{key}")

    # -- Persistence ----------------------------------------------------------

    def _load(self) -> None:
        if CONFIG_FILE.is_file():
            try:
                loaded = json.loads(CONFIG_FILE.read_text())
                self._data.update(loaded)
                logger.debug("Loaded config from %s", CONFIG_FILE)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load config: %s", exc)

    def _save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            CONFIG_FILE.write_text(json.dumps(self._data, indent=2))
        except OSError as exc:
            logger.warning("Failed to save config: %s", exc)

    def reset_to_defaults(self) -> None:
        self._data = dict(DEFAULTS)
        self._save()
