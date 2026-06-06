import { useEffect, useState } from "react";
import { api } from "../api/client";
import { SAMPLE_CARE_PLAN } from "../sampleCarePlan";
import type { CarePlanContext, Patient } from "../types";

export function CarePlanPanel({ patient }: { patient: Patient }) {
  const [plan, setPlan] = useState<CarePlanContext | null>(null);
  const [pasted, setPasted] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPlan(null);
    setStatus(null);
    setError(null);
    setPasted("");
    setShowPaste(false);
    api
      .getCarePlan(patient.id)
      .then((p) => !cancelled && setPlan(p))
      .catch(() => {
        /* 404 = no plan yet */
      });
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  async function upload(document: string) {
    if (!document.trim()) {
      setError("Paste or choose a FHIR care plan first.");
      return;
    }
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const ctx = await api.uploadCarePlan(patient.id, document);
      setPlan(ctx);
      setPasted("");
      setShowPaste(false);
      setStatus("Care plan attached. The check-in agent will use it on the next call.");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    await upload(text);
    e.target.value = ""; // allow re-uploading the same file
  }

  async function handleRemove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteCarePlan(patient.id);
      setPlan(null);
      setStatus("Care plan removed.");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  const summaryParts = plan
    ? [
        plan.goals.length > 0 &&
          `${plan.goals.length} goal${plan.goals.length === 1 ? "" : "s"}`,
        plan.activities.length > 0 &&
          `${plan.activities.length} activit${plan.activities.length === 1 ? "y" : "ies"}`,
        plan.addresses.length > 0 &&
          `${plan.addresses.length} condition${plan.addresses.length === 1 ? "" : "s"}`,
      ].filter(Boolean)
    : [];

  return (
    <section className="care-plan-panel">
      <div className="call-panel-head">
        <ClipboardIcon />
        <h3>Care plan</h3>
      </div>
      <p className="care-plan-sub">
        The check-in agent reads this before every call, so it knows the patient's
        goals, conditions, and daily routine.
      </p>

      {status && <p className="call-status">{status}</p>}
      {error && <p className="call-error">{error}</p>}

      {plan ? (
        <div className="care-plan-current">
          <div className="care-plan-current-head">
            <CheckIcon />
            <div>
              <div className="care-plan-title">{plan.title ?? "Care plan attached"}</div>
              {summaryParts.length > 0 && (
                <div className="care-plan-counts">{summaryParts.join(" · ")}</div>
              )}
            </div>
            {plan.status && (
              <span className="tag tag-ok care-plan-status">{plan.status}</span>
            )}
          </div>
          <button className="btn btn-ghost" onClick={handleRemove} disabled={busy}>
            Remove plan
          </button>
        </div>
      ) : (
        <div className="care-plan-upload">
          <label className="care-plan-drop">
            <UploadIcon />
            <span className="care-plan-drop-title">Upload a FHIR care plan</span>
            <span className="care-plan-drop-hint">Choose a .json or .xml file</span>
            <input
              type="file"
              accept=".json,.xml,application/json,text/xml"
              onChange={handleFile}
              disabled={busy}
            />
          </label>

          {showPaste ? (
            <div className="care-plan-paste">
              <textarea
                className="input"
                rows={5}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                placeholder='{"resourceType": "CarePlan", ...}'
              />
              <div className="care-plan-paste-actions">
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => setPasted(SAMPLE_CARE_PLAN)}
                  disabled={busy}
                >
                  Load sample plan
                </button>
                <button className="btn" onClick={() => upload(pasted)} disabled={busy}>
                  Attach plan
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="link-btn care-plan-paste-toggle"
              onClick={() => setShowPaste(true)}
            >
              or paste FHIR JSON / XML
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function ClipboardIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="5" y="4" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M9 4.5h6V7H9z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path
        d="M8.5 12h7M8.5 16h4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5 12.5l4 4 10-10"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 16V5m0 0L8 9m4-4 4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M5 16v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
