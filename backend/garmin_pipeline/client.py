"""Authenticated, rate-limited pull of Garmin vitals into Samples."""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Optional

from . import extractors as ex
from .config import Config
from .models import Sample, get_tz
from .ratelimit import RateLimiter, RateLimitPolicy

log = logging.getLogger(__name__)


def _is_rate_limit(err: Exception) -> bool:
    return "toomanyrequests" in type(err).__name__.lower() or "429" in str(err)


class GarminClient:
    """Pulls a day's vitals from Garmin Connect and returns normalized Samples.

    `garmin` and `rate_limiter` are injectable for testing without the live library.
    """

    def __init__(
        self,
        config: Config,
        garmin=None,
        rate_limiter: Optional[RateLimiter] = None,
        mfa_prompt: Optional[Callable[[], str]] = None,
    ) -> None:
        self.config = config
        self.tz = get_tz(config.local_tz)
        self._garmin = garmin
        self._mfa_prompt = mfa_prompt or (lambda: input("MFA one-time code (email/SMS): ").strip())
        self.rl = rate_limiter or RateLimiter(
            RateLimitPolicy(
                min_call_interval_seconds=config.min_call_interval_seconds,
                backoff_seconds=config.backoff_seconds,
                max_retries=config.max_retries,
            )
        )

    def login(self) -> "GarminClient":
        from garminconnect import Garmin  # lazy heavy import (needs `pip install .[live]`)

        # 1) Reuse a cached token if present - avoids a fresh login (and its 429 risk).
        try:
            g = Garmin()
            g.login(self.config.token_store)
            log.info("Logged in via cached token (%s)", self.config.token_store)
            self._garmin = g
            return self
        except Exception as err:  # noqa: BLE001 - any failure here means "do a full login"
            log.info("No usable cached token (%s); performing full login", err)

        # 2) Full login with credentials. May prompt for an emailed MFA code even without 2FA.
        if not (self.config.garmin_email and self.config.garmin_password):
            raise RuntimeError("Set GARMIN_EMAIL and GARMIN_PASSWORD (no cached token found).")
        g = Garmin(
            email=self.config.garmin_email,
            password=self.config.garmin_password,
            is_cn=self.config.is_cn,
            prompt_mfa=self._mfa_prompt,
        )
        g.login(self.config.token_store)
        log.info("Logged in; cached token to %s", self.config.token_store)
        self._garmin = g
        return self

    @property
    def garmin(self):
        if self._garmin is None:
            raise RuntimeError("Not logged in. Call login() first.")
        return self._garmin

    def _call(self, fn, *args):
        attempt = 0
        while True:
            attempt += 1
            self.rl.throttle()
            try:
                return fn(*args)
            except Exception as err:  # noqa: BLE001
                if _is_rate_limit(err) and attempt <= self.rl.policy.max_retries:
                    wait = self.rl.backoff(attempt)
                    log.warning("429 rate-limited; backed off %.0fs (attempt %d)", wait, attempt)
                    continue
                raise

    def _safe(self, fn, *args) -> dict:
        """Call a getter; tolerate a single metric failing so the rest of the day still loads."""
        try:
            return self._call(fn, *args) or {}
        except Exception as err:  # noqa: BLE001
            log.warning("metric fetch failed (%s): %s", getattr(fn, "__name__", fn), err)
            return {}

    def fetch_day(self, day: date) -> list[Sample]:
        g = self.garmin
        d = day.isoformat()
        samples: list[Sample] = []
        samples += ex.extract_heart_rate(self._safe(g.get_heart_rates, d), self.tz)
        samples += ex.extract_daily_stats(self._safe(g.get_stats, d), self.tz)
        stress = self._safe(g.get_stress_data, d)
        samples += ex.extract_stress(stress, self.tz)
        samples += ex.extract_body_battery(stress, self.tz)
        samples += ex.extract_sleep(self._safe(g.get_sleep_data, d), self.tz)
        samples += ex.extract_spo2_allday(self._safe(g.get_spo2_data, d), self.tz)
        # Blood pressure is a date-range call and is usually EMPTY (watches don't measure BP).
        samples += ex.extract_blood_pressure(self._safe(g.get_blood_pressure, d, d), self.tz)
        return samples
