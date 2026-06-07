"""Generate & store personalised daily check-in questions for the voice agent.

Single source of truth for per-patient question generation. It builds the context
the model needs - the last few days of phone check-ins, the patient's chronic
conditions (from their MongoDB FHIR record), and the worsening-symptom guide
(``llm/worsening_symptoms.json``) narrowed to those conditions - then asks the LLM
(Gemma 4 via the ``llm/`` package) to cross-reference them into 3 diverse, tailored
questions. Results are cached in ``llm/patient_questions.json``, keyed by FHIR id.

Used by both the offline batch CLI (``llm/generate_patient_questions.py``) and the
live "regenerate" endpoint (``app/routers/questions.py``).
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from .. import checkin_store, data, fhir_source
from ..models import GeneratedQuestion, Patient, PatientQuestions

# repo root: backend/app/services/question_gen.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
QUESTIONS_FILE = _REPO_ROOT / "llm" / "patient_questions.json"
SYMPTOMS_FILE = _REPO_ROOT / "llm" / "worsening_symptoms.json"
PROMPT_FILE = "Prompts/patient_questions_prompt.md"  # resolved against repo root by llm.config
HISTORY_DAYS = 4

# Writes to the JSON store are serialised so the batch CLI and a regenerate request
# can't interleave a read-modify-write.
_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Context building (pure helpers, shared with the CLI)
# --------------------------------------------------------------------------
def load_guide() -> dict[str, list[str]]:
    try:
        return json.loads(SYMPTOMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def render_checkins(checkins: list, *, history_days: int = HISTORY_DAYS) -> str:
    recent = sorted(checkins, key=lambda c: c.date, reverse=True)[:history_days]
    if not recent:
        return "(no recent check-ins on record)"
    lines = []
    for c in recent:
        if not c.answered:
            lines.append(f"- {c.date.isoformat()}: no answer (call not picked up).")
            continue
        lines.append(
            f'- {c.date.isoformat()}: mood "{c.mood}", pain {c.pain_level}/10. '
            f"Notes: {c.notes}"
        )
    return "\n".join(lines)


def relevant_symptoms(conditions: list[str], guide: dict[str, list[str]]) -> dict[str, list[str]]:
    by_lower = {k.lower(): k for k in guide}
    out: dict[str, list[str]] = {}
    for cond in conditions:
        key = by_lower.get(cond.lower())
        if key:
            out[cond] = guide[key]
    return out


def render_symptom_guide(symptoms: dict[str, list[str]]) -> str:
    if not symptoms:
        return "(no worsening-symptom guidance available for this patient's conditions)"
    return "\n".join(f"- {cond}: " + ", ".join(signs) for cond, signs in symptoms.items())


def build_user_message(
    *, name: str, age, conditions: list[str], checkin_text: str, symptom_text: str
) -> str:
    cond_text = ", ".join(conditions) if conditions else "(none on record)"
    return (
        f"Patient: {name}, age {age}.\n\n"
        f"Chronic conditions:\n{cond_text}\n\n"
        f"Recent check-in summaries (newest first):\n{checkin_text}\n\n"
        f"Worsening-symptom guide for this patient's conditions:\n{symptom_text}\n\n"
        "Write the 3 tailored check-in questions now, following your instructions and "
        "the JSON output contract. Cross-reference the recent check-ins against the "
        "worsening-symptom guide first.\n\n"
        # gemma-4-26b-a4b-it is a reasoning MoE that otherwise emits a long <thought>
        # block (60-120s/call, frequently truncated before the JSON). The /no_think
        # switch token disables that, so each call returns clean JSON in ~5s.
        "/no_think"
    )


def parse_questions(obj) -> list[GeneratedQuestion]:
    """Pull a clean list of up to 3 questions out of the model reply."""
    if not isinstance(obj, dict):
        return []
    out: list[GeneratedQuestion] = []
    for q in obj.get("questions") or []:
        if isinstance(q, str) and q.strip():
            out.append(GeneratedQuestion(text=q.strip()))
        elif isinstance(q, dict) and str(q.get("text", "")).strip():
            out.append(
                GeneratedQuestion(
                    text=str(q["text"]).strip(),
                    category=q.get("category"),
                    related_condition=q.get("related_condition"),
                    related_symptom=q.get("related_symptom"),
                )
            )
    return out[:3]


def patient_conditions(patient_id: int) -> list[str]:
    profile = fhir_source.get_profile(patient_id)
    return [c.name for c in profile.chronic_conditions] if profile else []


# --------------------------------------------------------------------------
# LLM client (lazy - only needed when actually generating)
# --------------------------------------------------------------------------
def _llm_client():
    """Construct the Gemma client, raising a clear error if it isn't usable."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    try:
        from llm import config as llm_config
        from llm.client import LLMClient
    except ImportError as e:
        raise RuntimeError(
            f"Question generation needs the 'openai' package ({e}). "
            "Install it in the backend environment (pip install openai)."
        ) from e
    if llm_config.LLM_PROVIDER != "vllm" and not llm_config.GEMINI_API_KEY:
        raise RuntimeError(
            "No GEMINI_API_KEY configured - set it in backend/.env to generate questions."
        )
    return LLMClient(prompt_file=PROMPT_FILE)


# --------------------------------------------------------------------------
# JSON store (llm/patient_questions.json, keyed by FHIR id or slot-<id>)
# --------------------------------------------------------------------------
def _store_key(patient: Patient) -> str:
    return patient.fhir_id or f"slot-{patient.id}"


def load_store() -> dict[str, dict]:
    try:
        return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_entry(key: str, entry: dict) -> None:
    with _LOCK:
        store = load_store()
        store[key] = entry
        QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUESTIONS_FILE.write_text(
            json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _entry_to_model(patient: Patient, entry: dict | None) -> PatientQuestions:
    if not entry:
        return PatientQuestions(
            patient_id=patient.id,
            fhir_id=patient.fhir_id,
            patient_name=patient.name,
            chronic_conditions=patient_conditions(patient.id),
            questions=[],
            generated=False,
        )
    return PatientQuestions(
        patient_id=patient.id,
        fhir_id=patient.fhir_id,
        patient_name=entry.get("patient_name") or patient.name,
        chronic_conditions=entry.get("chronic_conditions") or [],
        questions=[GeneratedQuestion(**q) if isinstance(q, dict) else GeneratedQuestion(text=str(q))
                   for q in (entry.get("questions") or [])],
        generated=bool(entry.get("questions")),
    )


def get_for_patient(patient: Patient) -> PatientQuestions:
    """Return the stored question set for a patient (generated=False if none yet)."""
    store = load_store()
    entry = store.get(_store_key(patient))
    return _entry_to_model(patient, entry)


def delete_for_patient(patient: Patient) -> bool:
    """Remove a patient's stored questions (right to erasure). True if one existed."""
    with _LOCK:
        store = load_store()
        if _store_key(patient) not in store:
            return False
        del store[_store_key(patient)]
        QUESTIONS_FILE.write_text(
            json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return True


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
def generate_for_patient(patient: Patient, *, client=None, persist: bool = True) -> PatientQuestions:
    """Generate (and by default persist) the tailored questions for one patient.

    Raises RuntimeError if the LLM backend is unusable (no key / openai missing).
    Pass ``persist=False`` for a dry run that doesn't touch the JSON store.
    """
    conditions = patient_conditions(patient.id)
    # Merge call-derived check-ins (materialized the instant a call finishes
    # analysing) with the synthetic daily history, exactly like the /checkins
    # endpoint. Putting the derived ones first means a summary generated moments
    # before "Regenerate" wins the newest-first slice in render_checkins, so the
    # model always reasons over the very latest days.
    checkins = checkin_store.list_for_patient(patient.id) + data.get_checkins(patient.id)
    guide = load_guide()
    symptom_text = render_symptom_guide(relevant_symptoms(conditions, guide))
    user = build_user_message(
        name=patient.name,
        age=patient.age,
        conditions=conditions,
        checkin_text=render_checkins(checkins),
        symptom_text=symptom_text,
    )

    client = client or _llm_client()
    # The reply is small (3 questions) and the prompt forbids a <thought> block, so a
    # tight token cap keeps each call fast (~5s) and guards against a runaway thought.
    questions = parse_questions(client.chat_json(user, max_tokens=2048))

    entry = {
        "fhir_id": patient.fhir_id,
        "patient_slot": patient.id,
        "patient_name": patient.name,
        "age": patient.age,
        "chronic_conditions": conditions,
        "questions": [q.model_dump() for q in questions],
    }
    if persist:
        _save_entry(_store_key(patient), entry)
    return _entry_to_model(patient, entry)
