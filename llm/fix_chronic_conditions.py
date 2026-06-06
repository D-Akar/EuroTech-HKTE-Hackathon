"""Fix the `chronic_conditions` field of the FHIR patient JSON files.

The extracted records mix genuine chronic diseases with SNOMED social-determinant
and lifestyle "findings" (employment, education, stress, housing, ...). This task
does the full fix in one pass:

1. **Drop** the garbage. Every *distinct* condition label is classified keep/drop
   (reusing the report from `clean_chronic_conditions.py`, or re-classifying with
   the model). Social/lifestyle/acute findings are removed; genuine diseases stay.
2. **Inject** realistic replacements. A model-curated catalogue of chronic diseases
   common in **Hong Kong / Asia** is sampled randomly so each affected patient ends
   up with INJECT_MIN..INJECT_MAX (default 2-3) genuine chronic conditions.

The LLM (Gemma 4 via the Gemini API by default - see `config.py`) does the two
judgement calls: classifying the noisy labels and curating the HK/Asia catalogue.
The random assignment itself is done in Python and is reproducible with `--seed`.

NOTE: `data/fhir_processed/` is **gitignored** (not tracked), so `--apply` is NOT
reversible with git. The first `--apply` snapshots the pre-edit `chronic_conditions`
of every patient to a backup JSON (default `llm/original_chronic_conditions_backup.json`)
unless one already exists; `--restore` writes that backup back into the files.

Run from the repo root (with `GEMINI_API_KEY` set for the Gemma backend):

    # 1. dry run - preview drops + injected diseases, write the catalogue + report
    python -m llm.fix_chronic_conditions

    # 2. apply in place (snapshots originals to the backup first)
    python -m llm.fix_chronic_conditions --apply

    # undo: restore the original chronic_conditions from the backup
    python -m llm.fix_chronic_conditions --restore

Useful flags:
    --apply            write changes (default: dry run)
    --seed N           RNG seed for the random disease assignment (default 42)
    --min N / --max N  conditions per affected patient (default 2 / 3)
    --reclassify       re-run keep/drop with the model (else reuse the report)
    --rebuild-catalog  re-query the model for the HK/Asia catalogue
    --offline          skip the model entirely: reuse the saved report + a built-in
                       fallback catalogue (handy with no key / no network)
    --fill-empty       also give 2-3 diseases to patients who had no conditions
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from . import config
from .client import LLMClient
from .clean_chronic_conditions import classify, collect_unique_names, iter_files

DEFAULT_REPORT = config.REPO_ROOT / "llm" / "chronic_conditions_decisions.json"
DEFAULT_BACKUP = config.REPO_ROOT / "llm" / "original_chronic_conditions_backup.json"

# Used only with --offline (or as a last resort if the model reply is unusable).
# The canonical catalogue is curated by the model into config.CATALOG_FILE.
FALLBACK_CATALOG = [
    {"name": "Essential hypertension", "weight": 100},
    {"name": "Type 2 diabetes mellitus", "weight": 90},
    {"name": "Hyperlipidemia", "weight": 80},
    {"name": "Osteoarthritis of knee", "weight": 55},
    {"name": "Chronic kidney disease", "weight": 35},
    {"name": "Coronary heart disease", "weight": 35},
    {"name": "Chronic hepatitis B", "weight": 30},
    {"name": "Gout", "weight": 30},
    {"name": "Osteoporosis", "weight": 30},
    {"name": "Asthma", "weight": 25},
    {"name": "Chronic obstructive pulmonary disease", "weight": 22},
    {"name": "Atrial fibrillation", "weight": 20},
    {"name": "Cerebrovascular accident (history of stroke)", "weight": 20},
    {"name": "Hypothyroidism", "weight": 18},
    {"name": "Benign prostatic hyperplasia", "weight": 18},
    {"name": "Cataract", "weight": 18},
    {"name": "Chronic gastritis", "weight": 16},
    {"name": "Allergic rhinitis", "weight": 16},
    {"name": "Non-alcoholic fatty liver disease", "weight": 15},
    {"name": "Glaucoma", "weight": 12},
    {"name": "Chronic low back pain", "weight": 12},
    {"name": "Generalized anxiety disorder", "weight": 10},
    {"name": "Major depressive disorder", "weight": 10},
    {"name": "Parkinson's disease", "weight": 7},
    {"name": "Dementia (Alzheimer type)", "weight": 7},
]


# --------------------------------------------------------------------------
# Decisions (keep/drop) + catalogue (model-curated)
# --------------------------------------------------------------------------
def load_decisions(
    files: list[Path], names: list[str], *, report_path: Path, offline: bool, reclassify: bool
) -> dict[str, dict]:
    """Return {name: {"keep": bool, "reason": str}} from cache or the model."""
    if not reclassify and report_path.exists():
        print(f"Reusing keep/drop decisions from {report_path}")
        return json.loads(report_path.read_text(encoding="utf-8"))["decisions"]
    if offline:
        sys.exit(
            f"--offline needs an existing decision report at {report_path}.\n"
            "Run `python -m llm.clean_chronic_conditions` (with the model) once first."
        )
    _ensure_credentials()
    client = LLMClient(prompt_file=config.PROMPT_FILE)
    _require_model(client)
    print(f"Classifying {len(names)} distinct labels with '{client.model}'...")
    return classify(names, client, batch_size=40)


def build_catalog(*, catalog_path: Path, offline: bool, rebuild: bool) -> list[dict]:
    """Return [{"name", "weight"}] curated by the model (cached), or fallback."""
    if not rebuild and catalog_path.exists():
        print(f"Reusing HK/Asia catalogue from {catalog_path}")
        return json.loads(catalog_path.read_text(encoding="utf-8"))["conditions"]
    if offline:
        print("Offline: using the built-in fallback HK/Asia catalogue.")
        return FALLBACK_CATALOG
    _ensure_credentials()
    client = LLMClient(prompt_file=config.INJECT_PROMPT_FILE)
    _require_model(client)
    print(f"Building HK/Asia chronic-disease catalogue with '{client.model}'...")
    obj = client.chat_json("Build the catalogue now, following your instructions.")
    conditions = [
        {"name": c["name"], "weight": int(c.get("weight", 1))}
        for c in obj.get("conditions", [])
        if c.get("name")
    ]
    if not conditions:
        print("  model returned no usable conditions - using the fallback catalogue.")
        conditions = FALLBACK_CATALOG
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps({"model": client.model, "conditions": conditions}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  catalogue ({len(conditions)} conditions) -> {catalog_path}")
    return conditions


def _ensure_credentials() -> None:
    """Exit with a helpful message before constructing a keyless OpenAI client."""
    if config.LLM_PROVIDER != "vllm" and not config.GEMINI_API_KEY:
        sys.exit(
            "No API key for the Gemma backend. Set GEMINI_API_KEY (or GOOGLE_API_KEY),\n"
            "or run with --offline, or LLM_PROVIDER=vllm against a local server.\n"
            "Get a key at https://aistudio.google.com/apikey"
        )


def _require_model(client: LLMClient) -> None:
    if not client.health():
        sys.exit(
            f"Cannot reach the model at {client.base_url} (model: {client.model}).\n"
            "Check the key/network, or use --offline."
        )


# --------------------------------------------------------------------------
# Random assignment
# --------------------------------------------------------------------------
def random_onset(rng: random.Random, *, max_years: int = 15) -> str:
    """A plausible onset date between ~1 and `max_years` ago."""
    days = rng.randint(365, max_years * 365)
    return (date.today() - timedelta(days=days)).isoformat()


def fix_patient(
    doc: dict,
    keep: set[str],
    catalog: list[dict],
    rng: random.Random,
    *,
    target_min: int,
    target_max: int,
    fill_empty: bool,
) -> tuple[list[dict], list[str], list[str]]:
    """Return (new_conditions, dropped_names, injected_names) for one patient."""
    conditions = doc.get("chronic_conditions") or []
    genuine = [c for c in conditions if (c or {}).get("name") in keep]
    dropped = [(c or {}).get("name") for c in conditions if (c or {}).get("name") not in keep]

    # Skip untouched patients: no conditions and we are not filling empties.
    if not conditions and not fill_empty:
        return conditions, [], []

    have = {(c or {}).get("name") for c in genuine}
    target = rng.randint(target_min, target_max)
    pool = [c for c in catalog if c["name"] not in have]
    injected: list[str] = []
    while len(genuine) + len(injected) < target and pool:
        weights = [c["weight"] for c in pool]
        pick = rng.choices(pool, weights=weights, k=1)[0]
        injected.append(pick["name"])
        pool = [c for c in pool if c["name"] != pick["name"]]

    new_conditions = genuine + [
        {"name": name, "onset_date": random_onset(rng)} for name in injected
    ]
    return new_conditions, dropped, injected


# --------------------------------------------------------------------------
# Backup / restore (data/fhir_processed is gitignored - provide our own undo)
# --------------------------------------------------------------------------
def snapshot_originals(files: list[Path], backup_path: Path) -> None:
    """Save each patient's current chronic_conditions, keyed by _id, once."""
    if backup_path.exists():
        return  # never overwrite an existing snapshot of the originals
    snapshot = {}
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        snapshot[doc.get("_id", f.stem)] = doc.get("chronic_conditions") or []
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshotted originals -> {backup_path}")


def restore_originals(files: list[Path], backup_path: Path) -> None:
    if not backup_path.exists():
        sys.exit(f"No backup at {backup_path} - nothing to restore.")
    snapshot = json.loads(backup_path.read_text(encoding="utf-8"))
    restored = 0
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        key = doc.get("_id", f.stem)
        if key in snapshot:
            doc["chronic_conditions"] = snapshot[key]
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            restored += 1
    print(f"Restored original chronic_conditions into {restored} files from {backup_path}.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min", type=int, default=config.INJECT_MIN, dest="target_min")
    ap.add_argument("--max", type=int, default=config.INJECT_MAX, dest="target_max")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--catalog", type=Path, default=config.CATALOG_FILE)
    ap.add_argument("--reclassify", action="store_true", help="re-run keep/drop with the model")
    ap.add_argument("--rebuild-catalog", action="store_true", help="re-query the HK/Asia catalogue")
    ap.add_argument("--offline", action="store_true", help="skip the model (cached report + fallback)")
    ap.add_argument("--fill-empty", action="store_true", help="also seed patients with no conditions")
    ap.add_argument("--backup", type=Path, default=DEFAULT_BACKUP, help="originals snapshot path")
    ap.add_argument("--restore", action="store_true", help="undo: write the backup back into files")
    args = ap.parse_args()

    files = iter_files(args.data_dir)

    if args.restore:
        restore_originals(files, args.backup)
        return

    counts = collect_unique_names(files)
    names = sorted(counts)
    print(f"Found {len(files)} files, {len(names)} distinct condition labels.")

    decisions = load_decisions(
        files, names, report_path=args.report, offline=args.offline, reclassify=args.reclassify
    )
    keep = {n for n, d in decisions.items() if d.get("keep")}
    catalog = build_catalog(
        catalog_path=args.catalog, offline=args.offline, rebuild=args.rebuild_catalog
    )

    if args.apply:
        snapshot_originals(files, args.backup)

    rng = random.Random(args.seed)
    dropped_counter: Counter = Counter()
    injected_counter: Counter = Counter()
    files_changed = 0

    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        new_conditions, dropped, injected = fix_patient(
            doc, keep, catalog, rng,
            target_min=args.target_min, target_max=args.target_max, fill_empty=args.fill_empty,
        )
        if not dropped and not injected:
            continue
        files_changed += 1
        dropped_counter.update(dropped)
        injected_counter.update(injected)
        if args.apply:
            doc["chronic_conditions"] = new_conditions
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # -- summary -----------------------------------------------------------
    print(f"\nDropped {len(dropped_counter)} distinct garbage labels "
          f"({sum(dropped_counter.values())} entries). Top:")
    for name, n in dropped_counter.most_common(10):
        print(f"  {n:4d}  {name}")
    print(f"\nInjected {len(injected_counter)} distinct HK/Asia diseases "
          f"({sum(injected_counter.values())} entries). Distribution:")
    for name, n in injected_counter.most_common():
        print(f"  {n:4d}  {name}")

    verb = "Updated" if args.apply else "Would update"
    print(f"\n{verb} {files_changed} patient files.")
    if not args.apply:
        print("Dry run - no files changed. Re-run with --apply to write.")
    else:
        print(f"Undo with: python -m llm.fix_chronic_conditions --restore  (backup: {args.backup})")


if __name__ == "__main__":
    main()
