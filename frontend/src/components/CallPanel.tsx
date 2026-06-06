import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CallRecord, Patient, ScheduledCall } from "../types";

export function CallPanel({ patient }: { patient: Patient }) {
  const [toNumber, setToNumber] = useState(patient.phone_number);
  const [questions, setQuestions] = useState<string[]>([]);
  const [schedules, setSchedules] = useState<ScheduledCall[]>([]);
  const [history, setHistory] = useState<CallRecord[]>([]);

  const [scheduleAt, setScheduleAt] = useState("");
  const [recurring, setRecurring] = useState(false);

  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // (Re)load everything when the selected patient changes.
  useEffect(() => {
    let cancelled = false;
    setToNumber(patient.phone_number);
    setStatus(null);
    setError(null);
    Promise.all([
      api.getCallConfig(patient.id),
      api.listSchedules(patient.id),
      api.getCallHistory(patient.id),
    ])
      .then(([config, sched, hist]) => {
        if (cancelled) return;
        setQuestions(config.questions);
        setSchedules(sched);
        setHistory(hist);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [patient.id, patient.phone_number]);

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
        setStatus(`Call initiated (conversation ${record.conversation_id ?? "—"}).`);
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

  async function handleSaveQuestions() {
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const cleaned = questions.map((q) => q.trim()).filter(Boolean);
      const config = await api.saveCallConfig(patient.id, {
        questions: cleaned,
        greeting: null,
      });
      setQuestions(config.questions);
      setStatus("Questions saved.");
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
      <h3>Check-in call</h3>

      {status && <p className="call-status">{status}</p>}
      {error && <p className="error call-error">{error}</p>}

      {/* Call now */}
      <div className="call-row">
        <label className="field">
          <span className="field-label">To number</span>
          <input
            className="input"
            value={toNumber}
            onChange={(e) => setToNumber(e.target.value)}
            placeholder="+1..."
          />
        </label>
        <button className="btn" onClick={handleCallNow} disabled={busy}>
          Call now
        </button>
      </div>

      {/* Questions */}
      <div className="call-block">
        <div className="call-block-head">
          <span className="field-label">Questions to ask</span>
          <button
            className="btn btn-ghost"
            onClick={() => setQuestions((q) => [...q, ""])}
          >
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
              className="btn btn-ghost btn-remove"
              onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}
              aria-label="Remove question"
            >
              ×
            </button>
          </div>
        ))}
        <button className="btn" onClick={handleSaveQuestions} disabled={busy}>
          Save questions
        </button>
      </div>

      {/* Scheduling */}
      <div className="call-block">
        <span className="field-label">Schedule a call</span>
        <div className="call-row">
          <input
            className="input"
            type="datetime-local"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={recurring}
              onChange={(e) => setRecurring(e.target.checked)}
            />
            Repeat daily
          </label>
          <button className="btn" onClick={handleSchedule} disabled={busy}>
            Schedule
          </button>
        </div>

        {schedules.length > 0 && (
          <ul className="schedule-list">
            {schedules.map((s) => (
              <li key={s.id} className="schedule-item">
                <span>
                  {new Date(s.scheduled_at).toLocaleString()}
                  {s.recurring && <span className="tag tag-daily">daily</span>}
                </span>
                <button
                  className="btn btn-ghost"
                  onClick={() => handleCancel(s.id)}
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* History */}
      <div className="call-block">
        <span className="field-label">Recent calls</span>
        {history.length === 0 ? (
          <p className="muted">No calls yet.</p>
        ) : (
          <ul className="schedule-list">
            {history.slice(0, 5).map((r) => (
              <li key={r.id} className="schedule-item">
                <span>
                  {new Date(r.triggered_at).toLocaleString()} · {r.kind}
                </span>
                <span
                  className={`tag ${
                    r.status === "initiated" ? "tag-ok" : "tag-missed"
                  }`}
                >
                  {r.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
