"""External integrations - ElevenLabs server-tool callbacks."""

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import audit, consent_store, data
from ..config import settings
from ..models import (
    AgentConsentRequest,
    AgentEscalationRequest,
    ConsentRecord,
    EscalationRecord,
    PatientContextResponse,
)
from ..routers.escalations import perform_escalation
from ..security import consent_guard
from ..services.patient_context import build_patient_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/elevenlabs", tags=["integrations"])


def verify_tool_api_key(x_api_key: str = Header(default="")) -> str:
    """Authenticate a server-tool callback and return the calling client's name.

    Accepts any key in the per-client keyset (``CARELOOP_TOOL_API_KEYS``), which
    folds in the legacy single ``ELEVENLABS_TOOL_API_KEY`` as client ``"shared"``.
    Constant-time comparison; no keys configured -> all callers rejected.
    """
    keys = settings.tool_api_keys
    if not keys or not x_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    for key, client in keys.items():
        if hmac.compare_digest(x_api_key, key):
            return client
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.get("/health")
def integration_health() -> dict:
    """Public reachability probe for the ElevenLabs server-tool callbacks.

    Hit this from your **public** host (e.g. the ngrok URL) to confirm the cloud
    agent can actually reach this backend - the single most common reason the
    escalate/consent tools never fire. Reports whether a tool API key is
    configured **without revealing it**. No auth (it exposes nothing sensitive).
    """
    return {
        "ok": True,
        "service": "careloop-integrations",
        "tool_key_configured": bool(settings.tool_api_keys),
        "tool_clients": sorted(settings.tool_api_keys.values()),
    }


@router.get(
    "/patient-context",
    response_model=PatientContextResponse,
)
def get_patient_context(
    phone_number: str, client: str = Depends(verify_tool_api_key)
) -> PatientContextResponse:
    """Look up a patient by phone number and return their full health context."""
    patient = data.get_patient_by_phone(phone_number)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    # Releasing special-category data to the voice agent is a data *use*; gate it on
    # an active consent when enforcement is on (no-op otherwise).
    consent_guard.enforce(patient.id)
    audit.record(f"tool:{client}", "context.read", "patient", patient.id)
    return build_patient_context(patient)


@router.post(
    "/escalate",
    response_model=EscalationRecord,
)
async def escalate_from_agent(
    body: AgentEscalationRequest, client: str = Depends(verify_tool_api_key)
) -> EscalationRecord:
    """Escalate the patient the outbound agent is on a call with.

    Mirrors ``POST /patients/{id}/escalate`` but identifies the patient by the
    ``patient_id`` dynamic variable injected at dial time, and is guarded by the
    same X-API-Key as the other ElevenLabs tools. Flips status -> urgent,
    recolors every dashboard over SSE, and places the nurse alert call.
    """
    logger.info(
        "escalate_emergency webhook HIT: client=%s patient_id=%s reason=%r",
        client, body.patient_id, body.reason,
    )
    # resolve_patient (not get_patient): the agent posts the {{patient_id}} dynamic
    # variable, but in practice often sends the patient's NAME or a numeric string
    # ("3") instead of the int slot id. Resolve all three so a real mid-call
    # escalation is never lost to a type mismatch (and the nurse always gets dialled).
    patient = data.resolve_patient(body.patient_id)
    if patient is None:
        logger.warning("escalate webhook: patient_id=%s not found", body.patient_id)
        raise HTTPException(status_code=404, detail="Patient not found")
    return await perform_escalation(patient, reason=body.reason, source=body.source)


@router.post(
    "/consent",
    response_model=ConsentRecord,
)
def record_consent_from_agent(
    body: AgentConsentRequest, client: str = Depends(verify_tool_api_key)
) -> ConsentRecord:
    """Persist the patient's spoken consent decision captured by the voice gate.

    The agent calls this once the patient answers the opening consent question, so
    the verbal grant becomes a durable, policy-versioned :class:`ConsentRecord`
    (``method="voice"``) - the missing link between the live consent gate and the
    consent store. Guarded by the same X-API-Key as the other tools.
    """
    # Same permissive resolution as the escalate webhook: the agent may send a
    # name or numeric string rather than the int slot id.
    patient = data.resolve_patient(body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    rec = consent_store.record(
        patient.id,
        body.granted,
        scope=body.scope,
        method="voice",
        actor=f"patient(voice via {client})",
        note=body.note,
    )
    audit.record(
        f"tool:{client}",
        "consent.granted" if body.granted else "consent.revoked",
        "patient",
        body.patient_id,
        detail=f"scope={body.scope} method=voice",
    )
    return rec
