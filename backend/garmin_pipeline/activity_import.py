"""Import garminexport activity files into Samples."""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import date
from typing import Optional
from zoneinfo import ZoneInfo

from . import extractors as ex
from .models import Sample, get_tz

log = logging.getLogger(__name__)


def import_dir(
    directory: str,
    tz: Optional[ZoneInfo] = None,
    *,
    source: str = "garmin_activity",
    downsample: int = 1,
    since: Optional[date] = None,
) -> list[Sample]:
    """Parse every *_details.json in `directory` into heart-rate Samples."""
    tz = tz or get_tz()
    samples: list[Sample] = []
    files = sorted(glob.glob(os.path.join(directory, "*_details.json")))
    with_hr = without_hr = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                j = json.load(fh)
        except (OSError, ValueError) as err:
            log.warning("skip %s: %s", os.path.basename(f), err)
            continue
        s = ex.extract_activity_details(j, tz, source=source, downsample=downsample)
        if since is not None:
            s = [x for x in s if x.recorded_at.date() >= since]
        if s:
            samples.extend(s)
            with_hr += 1
        else:
            without_hr += 1
    log.info(
        "activities: %d with HR, %d without/empty; %d HR samples from %s",
        with_hr, without_hr, len(samples), directory,
    )
    return samples
