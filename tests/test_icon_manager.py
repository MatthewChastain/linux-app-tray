"""Tests for the IconManager (no GUI required)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Patch the config paths before importing IconManager.
_tmp = tempfile.mkdtemp()
_state_file = Path(_tmp) / "state.json"

with mock.patch("src.icon_manager.CONFIG_DIR", Path(_tmp)), \
     mock.patch("src.icon_manager.STATE_FILE", _state_file):
    from src.icon_manager import IconManager


@pytest.fixture()
def mgr(tmp_path: Path) -> IconManager:
    """Create an IconManager with a temp state file."""
    with mock.patch("src.icon_manager.CONFIG_DIR", tmp_path), \
         mock.patch("src.icon_manager.STATE_FILE", tmp_path / "state.json"):
        return IconManager()


def test_upsert_and_get(mgr: IconManager) -> None:
    mgr.upsert_icon("test-1", {"title": "Test Icon", "status": "Active"})
    info = mgr.get_icon_info("test-1")
    assert info is not None
    assert info["title"] == "Test Icon"


def test_remove(mgr: IconManager) -> None:
    mgr.upsert_icon("test-1", {"title": "Test", "status": "Active"})
    mgr.remove_icon("test-1")
    assert mgr.get_icon_info("test-1") is None
    assert "test-1" not in mgr.ordered_ids()


def test_ordering(mgr: IconManager) -> None:
    mgr.upsert_icon("a", {"title": "A"})
    mgr.upsert_icon("b", {"title": "B"})
    mgr.upsert_icon("c", {"title": "C"})
    assert mgr.ordered_ids() == ["a", "b", "c"]


def test_reorder(mgr: IconManager) -> None:
    mgr.upsert_icon("a", {"title": "A"})
    mgr.upsert_icon("b", {"title": "B"})
    mgr.upsert_icon("c", {"title": "C"})
    mgr.reorder("c", before="a")
    assert mgr.ordered_ids() == ["c", "a", "b"]


def test_pinning(mgr: IconManager) -> None:
    mgr.upsert_icon("a", {"title": "A", "pinned": True})
    mgr.set_pinned("a", False)
    assert mgr.get_icon_info("a")["pinned"] is False


def test_state_persistence(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    with mock.patch("src.icon_manager.CONFIG_DIR", tmp_path), \
         mock.patch("src.icon_manager.STATE_FILE", state_file):
        m1 = IconManager()
        m1.upsert_icon("x", {"title": "X", "pinned": True})
        m1.upsert_icon("y", {"title": "Y", "pinned": False})
        m1.destroy()

        assert state_file.is_file()
        data = json.loads(state_file.read_text())
        assert "x" in data["icons"]

        # Load again — should restore order.
        m2 = IconManager()
        assert m2.ordered_ids() == ["x", "y"]
        m2.destroy()


def test_signals(mgr: IconManager) -> None:
    added = []
    updated = []
    removed = []
    mgr.connect("icon-added", lambda _m, icon_id: added.append(icon_id))
    mgr.connect("icon-updated", lambda _m, icon_id: updated.append(icon_id))
    mgr.connect("icon-removed", lambda _m, icon_id: removed.append(icon_id))

    mgr.upsert_icon("s1", {"title": "S1"})
    assert added == ["s1"]

    mgr.upsert_icon("s1", {"title": "S1v2"})
    assert updated == ["s1"]

    mgr.remove_icon("s1")
    assert removed == ["s1"]
