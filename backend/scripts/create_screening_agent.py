"""Create the Careloop cognitive-screening agent on ElevenLabs via the API.

This is a one-shot bootstrap: it creates a *separate* Conversational AI agent
dedicated to periodic dementia voice-biomarker screening, distinct from the
patient check-in / emergency agent. The agent's prompt, Data Collection fields,
and Evaluation Criteria (the cognitive markers) are all defined here and pushed
in the create call - no dashboard clicking required.

The biomarkers are grounded in real instruments: the Mini-Cog (3-word
registration + delayed recall), orientation questions, and semantic verbal
fluency (animal naming), plus connected-speech markers (word-finding difficulty,
repetition/perseveration, lexical diversity) drawn from the dementia
speech-biomarker literature.

Usage (from backend/, with the venv active)::

    python -m scripts.create_screening_agent            # create it
    python -m scripts.create_screening_agent --dry-run  # print payload, don't POST

On success it prints the new agent_id. Add it to backend/.env::

    ELEVENLABS_SCREENING_AGENT_ID=<printed id>

Creating an agent is safe and reversible: it places NO calls and can be deleted
again (DELETE /v1/convai/agents/{id}).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

# Make `app` importable when run as a plain script from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

# Derive the create-agent endpoint from the configured EU-residency base so this
# tracks whatever region the rest of the backend uses.
_BASE = settings.elevenlabs_outbound_url.split("/v1/")[0]
CREATE_AGENT_URL = f"{_BASE}/v1/convai/agents/create"

AGENT_NAME = "Careloop Cognitive Screening"

# --- The screening protocol the agent administers -------------------------------
# Scripted but warm. The flow mirrors the Mini-Cog plus a semantic-fluency task so
# the post-call analysis LLM has clean, well-delimited evidence to extract from.
SYSTEM_PROMPT = """\
You are Careloop, a warm and patient voice assistant from an elderly-care service \
running a short, routine memory and wellbeing check with {{patient_name}}, age \
{{patient_age}}. This is a friendly check-in, NOT a medical diagnosis. Never use the \
words "dementia", "test", "exam", or "screening" with the patient - call it a "quick \
memory and wellbeing check". Speak slowly and clearly, one instruction at a time, and \
give the patient time to answer. If they are confused or distressed, reassure them and \
move on gently. Do not coach or give away answers.

Administer these steps IN ORDER, exactly once:

1. GREETING. Greet {{patient_name}} by name, say you'd like to do a quick two-minute \
memory and wellbeing check, and ask if now is a good time. If clearly no, thank them and \
end.

2. WORD REGISTRATION. Say: "I'm going to say three words. Please repeat them back, and \
try to remember them - I'll ask for them again later." Then say the three words clearly, \
one second apart: APPLE, PENNY, TABLE. Ask them to repeat the three words back. Note how \
many they repeated correctly, but do not correct them.

3. ORIENTATION. Ask, one at a time and warmly: (a) "What day of the week is it today?" \
(b) "What is today's date, as best you know?" (c) "What season are we in?" (d) "Where are \
you right now - what kind of place?" Accept reasonable answers; do not give the answer.

4. VERBAL FLUENCY. Say: "Now, for one minute, please name as many different animals as \
you can - any animals at all. Ready? Go." Let them list animals for about 60 seconds. \
Gently encourage if they pause ("any others?") but don't name any yourself. Keep a count \
of the distinct animals they name.

5. DELAYED RECALL. Say: "Earlier I asked you to remember three words. Can you tell me \
those three words now?" Note how many of APPLE, PENNY, TABLE they recall. Do not remind \
them of the words.

6. CLOSE. Thank {{patient_name}} warmly, tell them they did well and that this was just a \
routine check, and wish them a good day. End the call.

Throughout, pay attention to the patient's speech for your own notes: word-finding \
trouble (long pauses, "that thing", "you know"), repeating questions or stories already \
covered, and whether their speech is fluent and on-topic. Stay kind and unhurried."""

FIRST_MESSAGE = (
    "Hello {{patient_name}}, this is Careloop calling for your quick two-minute memory "
    "and wellbeing check. Is now a good time?"
)

# --- Data Collection: the cognitive markers extracted from the transcript --------
# dict keyed by identifier; each entry is {type, description}. Allowed types:
# string | number | integer | boolean.
DATA_COLLECTION = {
    "word_registration_count": {
        "type": "integer",
        "description": (
            "Of the three registration words (APPLE, PENNY, TABLE), how many the patient "
            "correctly repeated back immediately in step 2. Integer 0 to 3. If the step "
            "was not completed, leave unknown."
        ),
    },
    "delayed_recall_count": {
        "type": "integer",
        "description": (
            "Of the three words (APPLE, PENNY, TABLE), how many the patient correctly "
            "recalled UNPROMPTED in the delayed-recall step (step 5). Integer 0 to 3. This "
            "is the key Mini-Cog memory marker - lower is more concerning."
        ),
    },
    "orientation_score": {
        "type": "integer",
        "description": (
            "Number of the four orientation questions (day of week, date, season, type of "
            "place) the patient answered correctly in step 3. Integer 0 to 4."
        ),
    },
    "animal_fluency_count": {
        "type": "integer",
        "description": (
            "Number of DISTINCT, valid animals the patient named during the one-minute "
            "verbal-fluency task (step 4). Count each unique animal once; ignore repeats and "
            "non-animals. Typical healthy adults name roughly 15 or more; below about 12 may "
            "indicate semantic-fluency impairment."
        ),
    },
    "word_finding_difficulty": {
        "type": "boolean",
        "description": (
            "True if the patient showed notable word-finding difficulty in spontaneous "
            "speech: frequent long pauses, vague fillers ('that thing', 'you know'), or word "
            "substitutions. False if speech was fluent."
        ),
    },
    "repetition_observed": {
        "type": "boolean",
        "description": (
            "True if the patient repeated questions, stories, or information already covered "
            "in the same call (perseveration), which can signal short-term memory difficulty. "
            "False otherwise."
        ),
    },
    "speech_fluency": {
        "type": "string",
        "description": (
            "Overall qualitative rating of the patient's spontaneous speech fluency and "
            "coherence. Exactly one of: 'fluent', 'mildly_impaired', or 'impaired'."
        ),
    },
    "lexical_diversity_note": {
        "type": "string",
        "description": (
            "One short sentence on the richness of the patient's vocabulary: did they use "
            "varied, specific words, or rely on vague/empty words and a narrow vocabulary "
            "(low lexical diversity)? Note any empty-speech tendency."
        ),
    },
    "screening_completed": {
        "type": "boolean",
        "description": (
            "True only if all five protocol steps (registration, orientation, fluency, "
            "delayed recall) were administered and the patient engaged with them. False if "
            "the patient declined, hung up, or the protocol could not be completed."
        ),
    },
}

# --- Evaluation Criteria: pass/fail goals scored by the analysis LLM --------------
# Each criterion is scored success / failure / unknown against its goal prompt.
EVALUATION_CRITERIA = [
    {
        "id": "completed_cognitive_screen",
        "name": "completed_cognitive_screen",
        "type": "prompt",
        "conversation_goal_prompt": (
            "Mark success if the agent administered the full protocol (three-word "
            "registration, orientation questions, the one-minute animal-naming task, and "
            "delayed recall of the three words) and the patient engaged with all parts. Mark "
            "failure if the patient declined or the protocol was not completed."
        ),
    },
    {
        "id": "recall_within_normal_range",
        "name": "recall_within_normal_range",
        "type": "prompt",
        "conversation_goal_prompt": (
            "Mark success if the patient recalled at least 2 of the 3 words (APPLE, PENNY, "
            "TABLE) unprompted in the delayed-recall step. Mark failure if they recalled 1 or "
            "0. A Mini-Cog recall below 2 is a screen-positive memory signal. Use unknown if "
            "delayed recall was not performed."
        ),
    },
    {
        "id": "fluency_within_normal_range",
        "name": "fluency_within_normal_range",
        "type": "prompt",
        "conversation_goal_prompt": (
            "Mark success if the patient named at least 12 distinct animals in the one-minute "
            "verbal-fluency task. Mark failure if fewer than 12, which can indicate "
            "semantic-fluency impairment. Use unknown if the task was not performed."
        ),
    },
    {
        "id": "no_language_red_flags",
        "name": "no_language_red_flags",
        "type": "prompt",
        "conversation_goal_prompt": (
            "Mark success if the patient's spontaneous speech was fluent and coherent with no "
            "marked word-finding difficulty, no repetition of already-covered content, and "
            "intact orientation. Mark failure if one or more of these language/memory red "
            "flags were clearly present."
        ),
    },
]


def build_payload() -> dict:
    """Assemble the create-agent request body."""
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": "gemini-2.5-flash",
                    "temperature": 0.2,
                },
            },
        },
        "platform_settings": {
            "data_collection": DATA_COLLECTION,
            "evaluation": {"criteria": EVALUATION_CRITERIA},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request payload and target URL, but do not POST.",
    )
    args = parser.parse_args()

    payload = build_payload()

    if args.dry_run:
        print(f"POST {CREATE_AGENT_URL}\n")
        print(json.dumps(payload, indent=2))
        return 0

    if not settings.elevenlabs_api_key:
        print("ERROR: ELEVENLABS_API_KEY is not set in backend/.env.", file=sys.stderr)
        return 1

    headers = {"xi-api-key": settings.elevenlabs_api_key}
    print(f"Creating agent '{AGENT_NAME}' at {CREATE_AGENT_URL} ...")
    try:
        resp = httpx.post(CREATE_AGENT_URL, json=payload, headers=headers, timeout=60)
    except httpx.HTTPError as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    body = resp.json()
    agent_id = body.get("agent_id") or body.get("agent_id".upper()) or body.get("id")
    print("\nSUCCESS - cognitive-screening agent created.")
    print(f"agent_id: {agent_id}")
    print("\nAdd this line to backend/.env:")
    print(f"    ELEVENLABS_SCREENING_AGENT_ID={agent_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
