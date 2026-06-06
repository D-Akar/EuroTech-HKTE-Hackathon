"""In-process pub/sub for Server-Sent Events.

A lightweight fan-out so a state change (e.g. a patient escalation) can be pushed
to every connected dashboard in real time. In-memory only — resets on restart,
like the other wireframe stores. Each connected client owns one queue;
``broadcast`` puts the same payload onto all of them.
"""

from __future__ import annotations

import asyncio
import json

# Every connected SSE client registers a queue here; broadcast() fans out to all.
_subscribers: set[asyncio.Queue[str]] = set()

# Cap per-client backlog so one slow/stalled tab can't grow memory unbounded.
_MAX_QUEUE = 100


def register() -> asyncio.Queue[str]:
    """Create and track a queue for one SSE connection."""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_MAX_QUEUE)
    _subscribers.add(queue)
    return queue


def unregister(queue: asyncio.Queue[str]) -> None:
    """Stop tracking a connection's queue (on disconnect)."""
    _subscribers.discard(queue)


def broadcast(event: str, data: dict) -> None:
    """Fan a named event out to every connected client (best-effort, non-blocking).

    Formats one SSE frame (``event:`` + ``data:``) and enqueues it for each
    subscriber. A full queue (slow client) drops the frame rather than blocking
    the broadcaster — live state is the source of truth, not the event log.
    """
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for queue in list(_subscribers):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def subscriber_count() -> int:
    return len(_subscribers)
