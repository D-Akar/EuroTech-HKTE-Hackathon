"""Clean the `chronic_conditions` field of the FHIR patient JSON files.

The extracted records mix genuine chronic diseases with SNOMED social-determinant
and lifestyle "findings" (employment, education, stress, housing, ...). This script
asks the LLM to classify every *distinct* condition label once, then applies the
keep/drop decision to all patient files.

Run from the repo root:

    # 1. (dry run) classify + preview what would be removed, write a decision report
    python -m llm.clean_chronic_conditions

    # 2. apply the cleanup in place (files are git-tracked, so this is reversible)
    python -m llm.clean_chronic_conditions --apply

Useful flags:
    --data-dir PATH     override the FHIR directory
    --batch-size N       labels per LLM request (default 60)
    --report PATH        where to write the decision JSON (default llm/chronic_conditions_decisions.json)
    --decisions PATH     skip the LLM and reuse a previous report (apply only)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import config
from .client import VLLMClient

DEFAULT_REPORT = config.REPO_ROOT / "llm" / "chronic_conditions_decisions.json"


# --------------------------------------------------------------------------
# Data helpers
# --------------------------------------------------------------------------
def iter_files(data_dir: Path) -> list[Path]:
    files = sorted(data_dir.glob("*.json"))
    if not files:
        sys.exit(f"No JSON files found in {data_dir}")
    return files


def collect_unique_names(files: list[Path]) -> Counter:
    counts: Counter = Counter()
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        for cc in doc.get("chronic_conditions", []) or []:
            name = (cc or {}).get("name")
            if name:
                counts[name] += 1
    return counts


def chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
def classify(names: list[str], client: VLLMClient, batch_size: int) -> dict[str, dict]:
    """Return {name: {"keep": bool, "reason": str}} for every input name."""
    decisions: dict[str, dict] = {}
    batches = list(chunked(names, batch_size))
    for i, batch in enumerate(batches, 1):
        print(f"  classifying batch {i}/{len(batches)} ({len(batch)} labels)...", flush=True)
        user = (
            "Classify each of the following condition labels. Return the JSON object "
            "described in your instructions, including EVERY label exactly as written.\n\n"
            + json.dumps(batch, ensure_ascii=False, indent=2)
        )
        obj = client.chat_json(user)
        for d in obj.get("decisions", []):
            name = d.get("name")
            if name is not None:
                decisions[name] = {"keep": bool(d.get("keep")), "reason": d.get("reason", "")}

    # Safety net: any label the model dropped from its reply is kept (conservative).
    missing = [n for n in names if n not in decisions]
    for n in missing:
        decisions[n] = {"keep": True, "reason": "MISSING from model reply — kept by default"}
    if missing:
        print(f"  warning: {len(missing)} label(s) missing from replies, kept by default")
    return decisions


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------
def apply_cleanup(files: list[Path], decisions: dict[str, dict], *, apply: bool) -> dict:
    keep = {n for n, d in decisions.items() if d["keep"]}
    removed_counter: Counter = Counter()
    files_changed = 0
    total_removed = 0

    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        conditions = doc.get("chronic_conditions", []) or []
        kept = [c for c in conditions if (c or {}).get("name") in keep]
        removed = [c for c in conditions if (c or {}).get("name") not in keep]
        if removed:
            files_changed += 1
            total_removed += len(removed)
            for c in removed:
                removed_counter[(c or {}).get("name")] += 1
            if apply:
                doc["chronic_conditions"] = kept
                f.write_text(
                    json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
    return {
        "files_changed": files_changed,
        "total_entries_removed": total_removed,
        "removed_by_name": dict(removed_counter.most_common()),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--decisions", type=Path, help="reuse an existing decision report (skip LLM)")
    args = ap.parse_args()

    files = iter_files(args.data_dir)
    counts = collect_unique_names(files)
    names = sorted(counts)
    print(f"Found {len(files)} files, {len(names)} distinct condition labels.")

    # 1. get decisions (from cache or the LLM)
    if args.decisions and args.decisions.exists():
        print(f"Reusing decisions from {args.decisions}")
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))["decisions"]
    else:
        client = VLLMClient()
        if not client.health():
            sys.exit(
                f"Cannot reach vLLM at {client.base_url}. Start it first:\n"
                f"  bash llm/serve_vllm.sh\n"
                f"(model: {client.model})"
            )
        print(f"Querying model '{client.model}' at {client.base_url}")
        decisions = classify(names, client, args.batch_size)

    # 2. write report (sorted: drops first, by frequency)
    report = {
        "model": config.VLLM_MODEL,
        "prompt_file": str(config.resolve_prompt_path()),
        "decisions": decisions,
        "summary": {
            "distinct_labels": len(names),
            "kept": sum(1 for d in decisions.values() if d["keep"]),
            "dropped": sum(1 for d in decisions.values() if not d["keep"]),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDecision report -> {args.report}")

    # 3. preview the drops
    dropped = sorted(
        (n for n, d in decisions.items() if not d["keep"]), key=lambda n: -counts[n]
    )
    print(f"\nWould DROP {len(dropped)} distinct labels (count = patients affected):")
    for n in dropped:
        print(f"  {counts[n]:4d}  {n}   — {decisions[n]['reason']}")

    # 4. apply / dry-run
    result = apply_cleanup(files, decisions, apply=args.apply)
    verb = "Removed" if args.apply else "Would remove"
    print(
        f"\n{verb} {result['total_entries_removed']} entries across "
        f"{result['files_changed']} files."
    )
    if not args.apply:
        print("\nDry run — no files changed. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
