"""Import processed FHIR patient records into MongoDB.

Each JSON file in the source directory is a single patient record whose top-level
``_id`` is the patient UUID (matching the filename). Records are upserted by ``_id``
so re-running the importer is idempotent - no duplicates, latest file wins.

The collection's primary key is ``_id``, which MongoDB always indexes, so lookups by
patient UUID are O(log n) without any extra index.

Defaults mirror the project's garmin pipeline config (see backend/garmin_pipeline/config.py):
    MONGODB_URI         mongodb://localhost:27017
    MONGODB_DB          careloop
    FHIR collection     fhir_patients

Usage:
    python -m scripts.import_fhir_to_mongo                      # from backend/, all defaults
    python scripts/import_fhir_to_mongo.py --src ../data/fhir_processed
    python scripts/import_fhir_to_mongo.py --uri mongodb://host:27017 --drop
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient, ReplaceOne
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

# Repo root = two levels up from this file (backend/scripts/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "data" / "fhir_processed"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import processed FHIR patient JSON into MongoDB.")
    p.add_argument(
        "--src",
        default=str(DEFAULT_SRC),
        help=f"Directory of *.json patient records (default: {DEFAULT_SRC}).",
    )
    p.add_argument(
        "--uri",
        default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"),
        help="MongoDB connection URI (default: $MONGODB_URI or mongodb://localhost:27017).",
    )
    p.add_argument(
        "--db",
        default=os.environ.get("MONGODB_DB", "careloop"),
        help="Database name (default: $MONGODB_DB or 'careloop').",
    )
    p.add_argument(
        "--collection",
        default=os.environ.get("FHIR_COLLECTION", "fhir_patients"),
        help="Collection name (default: $FHIR_COLLECTION or 'fhir_patients').",
    )
    p.add_argument(
        "--drop",
        action="store_true",
        help="Drop the collection before importing (clean reload).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of upserts per bulk_write (default: 500).",
    )
    return p.parse_args(argv)


def load_records(src: Path) -> tuple[list[dict], list[str]]:
    """Load every *.json file in src. Returns (records, errors)."""
    records: list[dict] = []
    errors: list[str] = []
    for path in sorted(src.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{path.name}: unreadable ({exc})")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{path.name}: top-level JSON is {type(doc).__name__}, expected object")
            continue
        # Trust the embedded _id; fall back to the filename stem if it's missing.
        if "_id" not in doc or not doc["_id"]:
            doc["_id"] = path.stem
        elif doc["_id"] != path.stem:
            errors.append(f"{path.name}: _id '{doc['_id']}' != filename stem (using embedded _id)")
        records.append(doc)
    return records, errors


def upsert_records(col, records: list[dict], batch_size: int) -> int:
    """Idempotently upsert records by _id. Returns number of documents written."""
    written = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        ops = [ReplaceOne({"_id": r["_id"]}, r, upsert=True) for r in batch]
        result = col.bulk_write(ops, ordered=False)
        written += result.upserted_count + result.modified_count + result.matched_count
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = Path(args.src).resolve()
    if not src.is_dir():
        print(f"ERROR: source directory not found: {src}", file=sys.stderr)
        return 2

    records, errors = load_records(src)
    for e in errors:
        print(f"  warn: {e}", file=sys.stderr)
    if not records:
        print(f"ERROR: no valid records loaded from {src}", file=sys.stderr)
        return 1

    print(f"Loaded {len(records)} records from {src}")
    print(f"Target: {args.uri}/{args.db}.{args.collection}")

    client = MongoClient(args.uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")  # fail fast with a clear message if unreachable
    except ServerSelectionTimeoutError:
        print(
            f"ERROR: could not reach MongoDB at {args.uri} (is the server running?).",
            file=sys.stderr,
        )
        return 3

    col = client[args.db][args.collection]
    try:
        if args.drop:
            col.drop()
            print(f"Dropped existing collection {args.db}.{args.collection}")
        written = upsert_records(col, records, args.batch_size)
        total = col.count_documents({})
    except PyMongoError as exc:
        print(f"ERROR during import: {exc}", file=sys.stderr)
        return 4
    finally:
        client.close()

    print(f"Upserted {written} documents. Collection now holds {total} patient records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
