"""Backfill and live polling loops."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Callable, Optional

from .client import GarminClient
from .store import SampleStore

log = logging.getLogger(__name__)


def backfill(client: GarminClient, store: SampleStore, days: int, end: Optional[date] = None) -> int:
    end = end or date.today()
    total = 0
    for i in range(days):
        day = end - timedelta(days=i)
        n = store.upsert(client.fetch_day(day))
        total += n
        log.info("backfill %s: %d samples", day.isoformat(), n)
    return total


def poll_once(client: GarminClient, store: SampleStore, day: Optional[date] = None) -> int:
    return store.upsert(client.fetch_day(day or date.today()))


def poll_loop(
    client: GarminClient,
    store: SampleStore,
    interval: float,
    *,
    max_iterations: Optional[int] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    i = 0
    while max_iterations is None or i < max_iterations:
        i += 1
        try:
            n = poll_once(client, store)
            log.info("poll #%d: upserted %d (store total=%d)", i, n, store.count())
        except Exception as err:  # noqa: BLE001 - keep the loop alive across transient errors
            log.error("poll #%d failed: %s", i, err)
        if max_iterations is not None and i >= max_iterations:
            break
        sleep_fn(interval)
    return i
