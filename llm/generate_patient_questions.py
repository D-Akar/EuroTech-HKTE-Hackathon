"""Offline batch: generate personalised daily check-in questions for the featured patients.

For each patient listed in ``featured_patients.md`` this builds the 3 tailored
questions the ElevenLabs voice agent should ask next, by cross-referencing three
inputs: the last few days of phone check-ins, the patient's chronic conditions (from
their MongoDB FHIR record), and the worsening-symptom guide
(``llm/worsening_symptoms.json``).

This is a thin wrapper around the backend service ``app.services.question_gen`` — the
same code the live "regenerate" button uses — so the offline batch and the dashboard
stay in lockstep. Results are written to ``llm/patient_questions.json`` keyed by FHIR id.

Run from the repo root with an interpreter that has ``openai`` + ``pymongo`` +
``pydantic``, with the Gemma key available (e.g. via ``backend/.env``), and MongoDB up:

    # dry run — print the questions, do not write
    python -m llm.generate_patient_questions --limit 3

    # generate for every featured patient and write the dataset
    python -m llm.generate_patient_questions --apply

Flags:
    --apply       write the dataset to llm/patient_questions.json (default: dry run)
    --limit N     only process the first N featured patients (handy for testing)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the backend app package importable (it owns the data layer + the service).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true", help="write the dataset (default: dry run)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N patients")
    args = ap.parse_args()

    try:
        from app import data, fhir_source
        from app.services import question_gen
    except Exception as e:  # noqa: BLE001
        sys.exit(
            f"Could not import the backend app ({e}).\n"
            "Run from the repo root with an interpreter that has pydantic/pymongo/openai, "
            "and make sure MongoDB is up (docker compose up -d) so the FHIR overlays bind."
        )

    featured_ids = fhir_source.read_featured_ids()
    by_fhir = {p.fhir_id: p for p in data.get_patients() if getattr(p, "fhir_id", None)}
    bound = [(fid, by_fhir[fid]) for fid in featured_ids if fid in by_fhir]
    if not bound:
        sys.exit(
            "No featured patients are bound to FHIR records. Is MongoDB up and populated "
            "(docker compose up -d), and does featured_patients.md list ids in Mongo?"
        )
    if args.limit is not None:
        bound = bound[: args.limit]

    try:
        client = question_gen._llm_client()
    except RuntimeError as e:
        sys.exit(str(e))
    if not client.health():
        sys.exit(f"Cannot reach the model at {client.base_url} (model: {client.model}).")
    print(f"Generating questions for {len(bound)} patients with '{client.model}'...\n")

    ok = 0
    for fhir_id, patient in bound:
        print(f"=== {patient.name} (slot {patient.id}, {fhir_id}) ===")
        try:
            pq = question_gen.generate_for_patient(patient, client=client, persist=args.apply)
        except Exception as e:  # noqa: BLE001 — one bad patient shouldn't sink the batch
            print(f"  ! generation failed ({e})\n")
            continue
        print(f"  conditions: {', '.join(pq.chronic_conditions) or '(none)'}")
        for q in pq.questions:
            tag = f" [{q.category}]" if q.category else ""
            print(f"  - {q.text}{tag}")
        if pq.questions:
            ok += 1
        else:
            print("  (no questions returned)")
        print()

    print(f"Generated questions for {ok}/{len(bound)} patients.")
    if args.apply:
        print(f"Wrote {question_gen.QUESTIONS_FILE}")
    else:
        print("Dry run — nothing written. Re-run with --apply to save.")


if __name__ == "__main__":
    main()
