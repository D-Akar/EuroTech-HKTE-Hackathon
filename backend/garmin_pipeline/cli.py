"""Command-line entrypoint for the Garmin pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import handoff, poller, synthetic
from .config import Config, load_env_file
from .models import Sample, get_tz
from .store import SampleStore


def _load_config() -> Config:
    load_env_file(".env")
    load_env_file("../.env")  # repo root when run from backend/
    return Config.from_env()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def cmd_login(args, cfg: Config) -> None:
    from .client import GarminClient

    GarminClient(cfg).login()
    print(f"Logged in. Token cached at {cfg.token_store}")


def cmd_backfill(args, cfg: Config) -> None:
    from .client import GarminClient

    days = args.days if args.days is not None else cfg.fetch_days
    client = GarminClient(cfg).login()
    store = SampleStore.from_config(cfg)
    n = poller.backfill(client, store, days)
    print(f"Backfilled {n} samples over {days} days -> {store.target}")
    print(f"  kinds: {store.kinds()}")


def cmd_poll(args, cfg: Config) -> None:
    from .client import GarminClient

    interval = args.interval if args.interval is not None else cfg.poll_interval_seconds
    client = GarminClient(cfg).login()
    store = SampleStore.from_config(cfg)
    print(f"Polling every {interval}s into {store.target} (Ctrl-C to stop)...")
    poller.poll_loop(client, store, interval, max_iterations=args.max_iterations)


def cmd_export(args, cfg: Config) -> None:
    store = SampleStore.from_config(cfg)
    n = handoff.export_json(store, args.out, kind=args.kind)
    print(f"Exported {n} sample dicts -> {args.out}")


def cmd_load(args, cfg: Config) -> None:
    """Ingest a JSON file of sample dicts into MongoDB (migration / seed path)."""
    store = SampleStore.from_config(cfg)
    rows = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    samples = [
        Sample(
            kind=r["kind"],
            value=r["value"],
            unit=r.get("unit", ""),
            recorded_at=datetime.fromisoformat(r["recorded_at"]),
            source=r.get("source", "garmin"),
            sample_id=r.get("sample_id", ""),
            meta=r.get("meta"),
        )
        for r in rows
        if isinstance(r, dict) and r.get("recorded_at")
    ]
    n = store.upsert(samples)
    print(f"Loaded {n} sample dicts from {args.inp} -> {store.target}")
    print(f"  kinds: {store.kinds()}")


def cmd_synth(args, cfg: Config) -> None:
    store = SampleStore.from_config(cfg)
    samples = synthetic.generate(days=args.days, tz=get_tz(cfg.local_tz))
    n = store.upsert(samples)
    print(f"Generated + stored {n} synthetic samples ({args.days} days, source=synthetic)")
    print(f"  kinds: {store.kinds()}")
    if args.out:
        m = handoff.export_json(store, args.out)
        print(f"Exported {m} sample dicts -> {args.out}")


def cmd_ingest_activities(args, cfg: Config) -> None:
    from datetime import date as _date

    from . import activity_import

    store = SampleStore.from_config(cfg)
    since = _date.fromisoformat(args.since) if args.since else None
    samples = activity_import.import_dir(
        args.dir, tz=get_tz(cfg.local_tz), downsample=args.downsample, since=since
    )
    n = store.upsert(samples)
    print(f"Ingested {n} in-workout HR samples from {args.dir}")
    print(f"  kinds: {store.kinds()}")
    if args.out:
        m = handoff.export_json(store, args.out)
        print(f"Exported {m} sample dicts -> {args.out}")


def cmd_serve(args, cfg: Config) -> None:
    import uvicorn

    store = SampleStore.from_config(cfg)
    uvicorn.run(handoff.create_app(store), host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="garmin-pipeline", description="CareLoop Garmin vitals extraction")
    p.add_argument("-v", "--verbose", action="store_true", help="info-level logging")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="log in and cache the token")
    sp.set_defaults(fn=cmd_login)

    sp = sub.add_parser("backfill", help="pull past N days of vitals into MongoDB")
    sp.add_argument("--days", type=int, default=None)
    sp.set_defaults(fn=cmd_backfill)

    sp = sub.add_parser("poll", help="live polling loop into MongoDB")
    sp.add_argument("--interval", type=float, default=None)
    sp.add_argument("--max-iterations", type=int, default=None, dest="max_iterations")
    sp.set_defaults(fn=cmd_poll)

    sp = sub.add_parser("export", help="write sample dicts from MongoDB for the FHIR teammate")
    sp.add_argument("--out", default="./data/samples.json")
    sp.add_argument("--kind", default=None)
    sp.set_defaults(fn=cmd_export)

    sp = sub.add_parser("load", help="ingest a JSON file of sample dicts into MongoDB")
    sp.add_argument("--in", dest="inp", required=True, help="path to a sample-dict JSON file")
    sp.set_defaults(fn=cmd_load)

    sp = sub.add_parser("synth", help="generate offline synthetic data into MongoDB (no Garmin)")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_synth)

    sp = sub.add_parser("ingest-activities", help="parse garminexport activity files (in-workout HR)")
    sp.add_argument("--dir", default="./data/garmindata")
    sp.add_argument("--downsample", type=int, default=1, help="keep 1 of every N samples")
    sp.add_argument("--since", default=None, help="only keep samples on/after YYYY-MM-DD")
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_ingest_activities)

    sp = sub.add_parser("serve", help="read-only HTTP API over MongoDB")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)
    return p


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    cfg = _load_config()
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
