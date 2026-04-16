"""Tests for the NotificationManager queue logic."""

from __future__ import annotations

from src.notifications.notification_manager import Notification, NotificationManager


def test_enqueue_shows_first() -> None:
    shown: list[Notification] = []
    hidden: list[bool] = []

    mgr = NotificationManager(
        show_fn=lambda n: shown.append(n),
        hide_fn=lambda: hidden.append(True),
    )

    n1 = Notification(icon_id="a", title="Hello")
    mgr.enqueue(n1)
    assert len(shown) == 1
    assert shown[0].title == "Hello"


def test_dismiss_shows_next() -> None:
    shown: list[Notification] = []
    hidden: list[bool] = []

    mgr = NotificationManager(
        show_fn=lambda n: shown.append(n),
        hide_fn=lambda: hidden.append(True),
    )

    n1 = Notification(icon_id="a", title="First")
    n2 = Notification(icon_id="b", title="Second")
    mgr.enqueue(n1)
    mgr.enqueue(n2)
    # Only first should be showing.
    assert len(shown) == 1

    mgr.dismiss_current()
    assert len(hidden) == 1
    assert len(shown) == 2
    assert shown[1].title == "Second"


def test_click_triggers_callback() -> None:
    clicked = []

    mgr = NotificationManager(
        show_fn=lambda _n: None,
        hide_fn=lambda: None,
    )

    n = Notification(icon_id="a", title="Click me", on_click=lambda: clicked.append(True))
    mgr.enqueue(n)
    mgr.on_click()
    assert clicked == [True]


def test_clear() -> None:
    shown: list[Notification] = []

    mgr = NotificationManager(
        show_fn=lambda n: shown.append(n),
        hide_fn=lambda: None,
    )

    mgr.enqueue(Notification(icon_id="a", title="A"))
    mgr.enqueue(Notification(icon_id="b", title="B"))
    mgr.clear()
    # After clear, enqueueing again should show immediately.
    mgr.enqueue(Notification(icon_id="c", title="C"))
    assert shown[-1].title == "C"
