import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { CallRecord, Patient, ScheduledCall } from "../types";
import { CallConversation } from "./CallConversation";
import { LiveCallTranscript } from "./LiveCallTranscript";

// A call is worth watching live only if it was just placed: an "initiated" call
// triggered within this window. Older "initiated" records are stale (no webhook
// updates the status), so we go straight to the post-call view instead of opening
// a monitor socket that would immediately fall through.
const LIVE_WINDOW_MS = 15 * 60 * 1000;

function isPotentiallyLive(r: CallRecord): boolean {
  return (
    r.status === "initiated" &&
    Date.now() - new Date(r.triggered_at).getTime() < LIVE_WINDOW_MS
  );
}

// How often we re-check for a finished call's analysis while a patient is open.
const POLL_MS = 6000;

export function CallPanel({
  patient,
  onPatientUpdate,
  onCallCompleted,
}: {
  patient: Patient;
  onPatientUpdate?: (patient: Patient) => void;
  onCallCompleted?: () => void;
}) {
  const [toNumber, setToNumber] = useState(patient.phone_number);
  const [questions, setQuestions] = useState<string[]>([]);
  const [greeting, setGreeting] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [schedules, setSchedules] = useState<ScheduledCall[]>([]);
  const [history, setHistory] = useState<CallRecord[]>([]);

  const [scheduleAt, setScheduleAt] = useState("");
  const [recurring, setRecurring] = useState(false);

  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openCallId, setOpenCallId] = useState<number | null>(null);
  const [analysing, setAnalysing] = useState(false);

  // Calls whose analysis we've already surfaced - so reopening a patient never
  // auto-expands an old, already-finished call, only ones that finish live.
  const settledRef = useRef<Set<number>>(new Set());

  const onCallCompletedRef = useRef(onCallCompleted);
  onCallCompletedRef.current = onCallCompleted;

  // Call ids whose live stream has ended this session - flip them to the
  // post-call view even though their record still reads "initiated".
  const [liveEnded, setLiveEnded] = useState<Set<number>>(new Set());

  // Success messages surface as a transient glassy toast at the top of the screen
  // that fades itself out after a few seconds, rather than a persistent box.
  useEffect(() => {
    if (!status) return;
    const t = window.setTimeout(() => setStatus(null), 5000);
    return () => window.clearTimeout(t);
  }, [status]);

  // (Re)load everything when the selected patient changes.
  useEffect(() => {
    let cancelled = false;
    setToNumber(patient.phone_number);
    setStatus(null);
    setError(null);
    setOpenCallId(null);
    setAnalysing(false);
    Promise.all([
      api.getCallConfig(patient.id),
      api.listSchedules(patient.id),
      api.getCallHistory(patient.id),
    ])
      .then(([config, sched, hist]) => {
        if (cancelled) return;
        setQuestions(config.questions);
        setGreeting(config.greeting ?? "");
        setSystemPrompt(config.system_prompt ?? "");
        setSchedules(sched);
        setHistory(hist);
        // Treat everything already on record as settled; only calls that finish
        // while we're watching should auto-surface.
        settledRef.current = new Set(hist.map((r) => r.id));
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [patient.id, patient.phone_number]);

  // Poll while a patient is open: pick up newly-placed calls (manual, scheduled,
  // or auto-escalated) and wait for ElevenLabs to finish analysing the newest
  // one. The moment it's ready we expand it and refresh the check-in summary at
  // the top - no manual clicking or page reload.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      let hist: CallRecord[];
      try {
        hist = await api.getCallHistory(patient.id);
      } catch {
        return;
      }
      if (cancelled) return;
      setHistory(hist);
      const newest = hist.find((r) => r.conversation_id);
      if (!newest || settledRef.current.has(newest.id)) {
        setAnalysing(false);
        return;
      }
      setAnalysing(true);
      const detail = await api
        .getCallConversation(patient.id, newest.id)
        .catch(() => null);
      if (cancelled || !detail?.ready) return;
      settledRef.current.add(newest.id);
      setAnalysing(false);
      setOpenCallId(newest.id);
      onCallCompletedRef.current?.();
    };
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [patient.id]);

  const refreshHistory = () =>
    api.getCallHistory(patient.id).then(setHistory).catch(() => {});
  const refreshSchedules = () =>
    api.listSchedules(patient.id).then(setSchedules).catch(() => {});

  async function handleCallNow() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const record = await api.triggerCall(patient.id, { to_number: toNumber });
      if (record.status === "initiated") {
        setStatus(`Check-in call initiated (conversation ${record.conversation_id ?? "-"}).`);
        setAnalysing(true); // poll will surface the summary once analysis lands
        // Open the row straight away so the live transcript streams in without the
        // coordinator having to hunt for the just-placed call (it's within the live
        // window by definition). Falls back to the post-call view when the stream ends.
        if (record.conversation_id) setOpenCallId(record.id);
      } else {
        setError(record.error ?? "Call failed.");
      }
      await refreshHistory();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveNumber() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const updated = await api.updatePatientPhone(patient.id, toNumber);
      setToNumber(updated.phone_number);
      onPatientUpdate?.(updated);
      setStatus("Phone number saved.");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveConfig() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const cleaned = questions.map((q) => q.trim()).filter(Boolean);
      const config = await api.saveCallConfig(patient.id, {
        questions: cleaned,
        greeting: greeting.trim() || null,
        system_prompt: systemPrompt.trim() || null,
      });
      setQuestions(config.questions);
      setGreeting(config.greeting ?? "");
      setSystemPrompt(config.system_prompt ?? "");
      setStatus("Call settings saved.");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSchedule() {
    if (!scheduleAt) {
      setError("Pick a date and time first.");
      return;
    }
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      // datetime-local has no timezone; send it as local ISO.
      await api.createSchedule(patient.id, {
        scheduled_at: new Date(scheduleAt).toISOString(),
        recurring,
      });
      setScheduleAt("");
      setRecurring(false);
      setStatus("Call scheduled.");
      await refreshSchedules();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(id: number) {
    setError(null);
    try {
      await api.cancelSchedule(patient.id, id);
      await refreshSchedules();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <section className="call-panel">
      <div className="call-panel-head">
        <PhoneIcon />
        <h3>Check-in call</h3>
      </div>

      {status &&
        createPortal(
          <div className="toast-success" role="status" aria-live="polite">
            {status}
          </div>,
          document.body,
        )}
      {error && <p className="call-error">{error}</p>}

      {/* Call now */}
      <div className="call-row">
        <label className="field">
          <span className="field-label">Dispatch to number</span>
          <input
            className="input"
            value={toNumber}
            onChange={(e) => setToNumber(e.target.value)}
            placeholder="+852..."
          />
        </label>
        <button
          className="btn btn-ghost"
          onClick={handleSaveNumber}
          disabled={busy || !toNumber.trim()}
          title="Save this number as the patient's check-in number"
        >
          Save
        </button>
        <button className="btn btn-call" onClick={handleCallNow} disabled={busy}>
          <PhoneIcon small /> Call now
        </button>
      </div>

      {/* Questions */}
      <div className="call-block">
        <div className="call-block-head">
          <span className="field-label">Questions to ask</span>
          <button className="btn btn-ghost" onClick={() => setQuestions((q) => [...q, ""])}>
            + Add
          </button>
        </div>
        {questions.map((q, i) => (
          <div className="question-row" key={i}>
            <input
              className="input"
              value={q}
              onChange={(e) =>
                setQuestions((qs) => qs.map((v, j) => (j === i ? e.target.value : v)))
              }
            />
            <button
              className="btn btn-remove"
              onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}
              aria-label="Remove question"
            >
              ✕
            </button>
          </div>
        ))}

        <label className="field" style={{ marginTop: 12 }}>
          <span className="field-label">Greeting (opening line)</span>
          <input
            className="input"
            value={greeting}
            onChange={(e) => setGreeting(e.target.value)}
            placeholder="e.g. Good morning, this is your daily check-in."
          />
        </label>

        <label className="field" style={{ marginTop: 10 }}>
          <span className="field-label">Agent system prompt</span>
          <textarea
            className="input"
            rows={5}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Override the agent's instructions for this patient (tone, focus, what to watch for)."
          />
        </label>
        <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
          Greeting and system prompt require the matching overrides to be enabled in the
          agent's Security settings on ElevenLabs.
        </p>

        <button className="btn btn-ghost" onClick={handleSaveConfig} disabled={busy} style={{ marginTop: 8 }}>
          Save call settings
        </button>
      </div>

      {/* Scheduling */}
      <div className="call-block">
        <span className="field-label">Schedule a call</span>
        <div className="call-row" style={{ marginTop: 8 }}>
          <input
            className="input"
            type="datetime-local"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
            style={{ flex: "1 1 180px" }}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={recurring}
              onChange={(e) => setRecurring(e.target.checked)}
            />
            Daily
          </label>
          <button className="btn" onClick={handleSchedule} disabled={busy}>
            Schedule
          </button>
        </div>

        {schedules.length > 0 && (
          <ul className="schedule-list">
            {schedules.map((s) => (
              <li key={s.id} className="schedule-item">
                <span className="num">
                  {new Date(s.scheduled_at).toLocaleString()}
                  {s.recurring && <span className="tag tag-daily" style={{ marginLeft: 8 }}>daily</span>}
                </span>
                <button className="btn btn-ghost" onClick={() => handleCancel(s.id)}>
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* History */}
      <div className="call-block">
        <div className="call-block-head">
          <span className="field-label">Recent calls</span>
          {analysing && (
            <span className="analysing-tag">
              <span className="analysing-dot" aria-hidden /> Analysing latest call…
            </span>
          )}
        </div>
        {history.length === 0 ? (
          <p className="muted" style={{ fontSize: 13.5, margin: "8px 0 0" }}>
            No calls yet.
          </p>
        ) : (
          <ul className="schedule-list">
            {history.slice(0, 5).map((r) => {
              const hasConversation = Boolean(r.conversation_id);
              const open = openCallId === r.id;
              return (
                <li key={r.id} className="call-history-item">
                  <div
                    className={`schedule-item ${hasConversation ? "call-history-row" : ""}`}
                    role={hasConversation ? "button" : undefined}
                    tabIndex={hasConversation ? 0 : undefined}
                    onClick={
                      hasConversation
                        ? () => setOpenCallId(open ? null : r.id)
                        : undefined
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
                      {new Date(r.triggered_at).toLocaleString()} · {r.kind}
                    </span>
                    <span className={`tag ${r.status === "initiated" ? "tag-ok" : "tag-missed"}`}>
                      {r.status}
                    </span>
                  </div>
                  {open && hasConversation &&
                    (isPotentiallyLive(r) && !liveEnded.has(r.id) ? (
                      <LiveCallTranscript
                        patientId={patient.id}
                        callId={r.id}
                        onEnded={() =>
                          setLiveEnded((prev) => new Set(prev).add(r.id))
                        }
                      />
                    ) : (
                      <CallConversation patientId={patient.id} callId={r.id} />
                    ))}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function PhoneIcon({ small }: { small?: boolean }) {
  const s = small ? 15 : 18;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6.5 4h3l1.5 4-2 1.5a11 11 0 0 0 5 5l1.5-2 4 1.5v3a2 2 0 0 1-2 2A15 15 0 0 1 4.5 6a2 2 0 0 1 2-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
