"""Notification queue — one visible at a time, auto-dismiss, click actions."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from gi.repository import GLib

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 10_000  # 10 seconds


@dataclass
class Notification:
    """A queued notification."""

    icon_id: str
    title: str
    body: str = ""
    icon_name: str | None = None
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    on_click: Callable[[], None] | None = None
    id: str = field(default_factory=lambda: str(GLib.get_monotonic_time()))


class NotificationManager:
    """Manages a queue of notifications shown one at a time.

    When the current notification is dismissed (click, X, timeout),
    the next one in the queue is shown.
    """

    def __init__(self, *, show_fn: Callable[[Notification], None], hide_fn: Callable[[], None]) -> None:
        self._show_fn = show_fn
        self._hide_fn = hide_fn
        self._queue: deque[Notification] = deque()
        self._current: Notification | None = None
        self._timer: int = 0

    def enqueue(self, notification: Notification) -> None:
        """Add a notification to the queue."""
        self._queue.append(notification)
        if self._current is None:
            self._show_next()

    def dismiss_current(self) -> None:
        """Dismiss the currently visible notification."""
        self._cancel_timer()
        self._hide_fn()
        self._current = None
        self._show_next()

    def on_click(self) -> None:
        """Handle click on the current notification."""
        if self._current and self._current.on_click:
            self._current.on_click()
        self.dismiss_current()

    def clear(self) -> None:
        """Clear all queued and current notifications."""
        self._cancel_timer()
        self._queue.clear()
        if self._current:
            self._hide_fn()
            self._current = None

    def _show_next(self) -> None:
        if not self._queue:
            return
        self._current = self._queue.popleft()
        self._show_fn(self._current)
        self._timer = GLib.timeout_add(self._current.timeout_ms, self._on_timeout)
        logger.debug("Showing notification: %s", self._current.title)

    def _on_timeout(self) -> bool:
        self._timer = 0
        self.dismiss_current()
        return GLib.SOURCE_REMOVE

    def _cancel_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
