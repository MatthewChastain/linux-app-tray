"""Tests for the SettingsManager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from src.settings.settings_manager import SettingsManager


@pytest.fixture()
def settings(tmp_path: Path) -> SettingsManager:
    with mock.patch("src.settings.settings_manager.CONFIG_DIR", tmp_path), \
         mock.patch("src.settings.settings_manager.CONFIG_FILE", tmp_path / "config.json"):
        return SettingsManager()


def test_defaults(settings: SettingsManager) -> None:
    assert settings.get_string("position") == "bottom"
    assert settings.get_int("icon_size") == 20
    assert settings.get_bool("always_show_all_icons") is False


def test_set_value(settings: SettingsManager) -> None:
    settings.set_value("position", "top")
    assert settings.get_string("position") == "top"


def test_persistence(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    with mock.patch("src.settings.settings_manager.CONFIG_DIR", tmp_path), \
         mock.patch("src.settings.settings_manager.CONFIG_FILE", cfg):
        s1 = SettingsManager()
        s1.set_value("icon_size", 32)

    assert cfg.is_file()
    data = json.loads(cfg.read_text())
    assert data["icon_size"] == 32

    with mock.patch("src.settings.settings_manager.CONFIG_DIR", tmp_path), \
         mock.patch("src.settings.settings_manager.CONFIG_FILE", cfg):
        s2 = SettingsManager()
        assert s2.get_int("icon_size") == 32


def test_per_app_settings(settings: SettingsManager) -> None:
    settings.set_app_setting("discord", "notifications", False)
    assert settings.get_app_setting("discord", "notifications") is False
    assert settings.get_app_setting("unknown", "notifications", True) is True


def test_changed_signal(settings: SettingsManager) -> None:
    changed_keys: list[str] = []
    settings.connect("changed", lambda _s, key: changed_keys.append(key))
    settings.set_value("theme", "dark")
    assert "theme" in changed_keys
