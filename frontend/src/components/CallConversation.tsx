import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConversationDataPoint, ConversationDetail } from "../types";

const FIELD_LABELS: Record<string, string> = {
  mood: "Mood",
  pain_level: "Pain",
  medication_taken: "Medication",
  new_symptoms: "New symptoms",
  sleep_quality: "Sleep",
  needs_followup: "Follow-up",
};

function label(id: string): string {
  return FIELD_LABELS[id] ?? id.replace(/_/g, " ");
}

function formatValue(p: ConversationDataPoint): string {
  if (p.value === null || p.value === "") return "—";
  if (typeof p.value === "boolean") return p.value ? "Yes" : "No";
  if (p.id === "pain_level" && typeof p.value === "number") return `${p.value}/10`;
  return String(p.value);
}

function formatDuration(secs: number | null): string | null {
  if (secs == null) return null;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function CallConversation({
  patientId,
  callId,
}: {
  patientId: number;
  callId: number;
}) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTranscript, setShowTranscript] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getCallConversation(patientId, callId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(String(e instanceof Error ? e.message : e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patientId, callId, reloadKey]);

  if (loading) {
    return (
      <div className="conv-detail">
        <p className="muted">Loading conversation…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="conv-detail">
        <p className="muted">No conversation data for this call.</p>
      </div>
    );
  }
  if (!detail) return null;

  if (!detail.ready) {
    return (
      <div className="conv-detail">
        <p className="muted">
          ElevenLabs is still analysing this call ({detail.status}).
        </p>
        <button className="link-btn" onClick={() => setReloadKey((k) => k + 1)}>
          Check again
        </button>
      </div>
    );
  }

  const followup = detail.data_collection.find((p) => p.id === "needs_followup");
  const followupReason = detail.data_collection.find(
    (p) => p.id === "followup_reason",
  )?.value;
  const chips = detail.data_collection.filter(
    (p) => p.id !== "followup_reason" && !(p.value === null || p.value === ""),
  );
  const duration = formatDuration(detail.call_duration_secs);

  return (
    <div className="conv-detail">
      <div className="conv-detail-head">
        {detail.call_successful && (
          <span className={`tag ${detail.call_successful === "success" ? "tag-ok" : "tag-missed"}`}>
            {detail.call_successful}
          </span>
        )}
        {duration && <span className="conv-duration">{duration}</span>}
      </div>

      {detail.transcript_summary && (
        <p className="conv-summary">{detail.transcript_summary}</p>
      )}

      {chips.length > 0 && (
        <div className="conv-chips">
          {chips.map((p) => {
            const flagged = p.id === "needs_followup" && p.value === true;
            return (
              <span
                key={p.id}
                className={`conv-chip ${flagged ? "conv-chip-flag" : ""}`}
                title={p.rationale ?? undefined}
              >
                <span className="conv-chip-label">{label(p.id)}</span>
                <span className="conv-chip-value">{formatValue(p)}</span>
              </span>
            );
          })}
        </div>
      )}

      {followup?.value === true && typeof followupReason === "string" && followupReason && (
        <p className="conv-followup-reason">Follow-up: {followupReason}</p>
      )}

      {detail.transcript.length > 0 && (
        <>
          <button
            className="link-btn"
            onClick={() => setShowTranscript((s) => !s)}
          >
            {showTranscript ? "Hide transcript" : "Show transcript"}
          </button>
          {showTranscript && (
            <div className="conv-transcript">
              {detail.transcript
                .filter((t) => t.message)
                .map((t, i) => (
                  <div key={i} className={`conv-turn conv-turn-${t.role}`}>
                    <span className="conv-turn-role">
                      {t.role === "agent" ? "Agent" : "Patient"}
                    </span>
                    <span className="conv-turn-msg">{t.message}</span>
                  </div>
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
