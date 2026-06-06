import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CallRecord, Patient } from "../types";
import { CallConversation } from "./CallConversation";

/**
 * Cognitive screening: places a call via the dedicated dementia voice-biomarker
 * agent (Mini-Cog recall, orientation, verbal fluency) and surfaces past screening
 * calls. Each result row expands to the extracted biomarkers and pass/fail markers.
 */
export function ScreeningPanel({ patient }: { patient: Patient }) {
  const [history, setHistory] = useState<CallRecord[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openCallId, setOpenCallId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus(null);
    setError(null);
    setOpenCallId(null);
    api
      .getCallHistory(patient.id)
      .then((h) => !cancelled && setHistory(h))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  const screenings = history.filter((r) => r.kind === "screening");

  async function handleScreen() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const record = await api.screeningCall(patient.id, patient.phone_number);
      if (record.status === "initiated") {
        setStatus("Screening call initiated. Results appear here once analysed.");
      } else {
        setError(record.error ?? "Screening call failed.");
      }
      const fresh = await api.getCallHistory(patient.id);
      setHistory(fresh);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screening-panel">
      <div className="screening-head">
        <BrainIcon />
        <div>
          <h3>Cognitive screening</h3>
          <p className="screening-sub">
            Voice biomarker check · Mini-Cog recall, orientation &amp; verbal fluency
          </p>
        </div>
        <button className="btn btn-screen" onClick={handleScreen} disabled={busy}>
          <BrainIcon small /> Run screening
        </button>
      </div>

      {status && <p className="call-status">{status}</p>}
      {error && <p className="call-error">{error}</p>}

      {screenings.length === 0 ? (
        <p className="muted" style={{ fontSize: 13.5, margin: "10px 0 0" }}>
          No screening calls yet. Run one to capture cognitive markers.
        </p>
      ) : (
        <ul className="schedule-list" style={{ marginTop: 10 }}>
          {screenings.slice(0, 5).map((r) => {
            const hasConversation = Boolean(r.conversation_id);
            const open = openCallId === r.id;
            return (
              <li key={r.id} className="call-history-item">
                <div
                  className={`schedule-item ${hasConversation ? "call-history-row" : ""}`}
                  role={hasConversation ? "button" : undefined}
                  tabIndex={hasConversation ? 0 : undefined}
                  onClick={
                    hasConversation ? () => setOpenCallId(open ? null : r.id) : undefined
                  }
                  onKeyDown={
                    hasConversation
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setOpenCallId(open ? null : r.id);
                          }
                        }
                      : undefined
                  }
                >
                  <span className="num">
                    {hasConversation && (
                      <span className={`disclosure ${open ? "on" : ""}`} aria-hidden>
                        ▸
                      </span>
                    )}
                    {new Date(r.triggered_at).toLocaleString()}
                  </span>
                  <span
                    className={`tag ${r.status === "initiated" ? "tag-ok" : "tag-missed"}`}
                  >
                    {r.status}
                  </span>
                </div>
                {open && hasConversation && (
                  <CallConversation patientId={patient.id} callId={r.id} />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function BrainIcon({ small }: { small?: boolean }) {
  const s = small ? 15 : 20;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 4.5a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0-1 4.8A2.5 2.5 0 0 0 7 16.5a2.5 2.5 0 0 0 5 .2V5.8A2.5 2.5 0 0 0 9 4.5ZM15 4.5A2.5 2.5 0 0 1 17.5 7a2.5 2.5 0 0 1 1 4.8 2.5 2.5 0 0 1-1.5 4.7 2.5 2.5 0 0 1-5 .2V5.8A2.5 2.5 0 0 1 15 4.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}
