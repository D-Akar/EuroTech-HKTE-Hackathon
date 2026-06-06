import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CarePlanContext, Patient } from "../types";

export function CarePlanPanel({ patient }: { patient: Patient }) {
  const [plan, setPlan] = useState<CarePlanContext | null>(null);
  const [pasted, setPasted] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPlan(null);
    setStatus(null);
    setError(null);
    setPasted("");
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
      setStatus("Care plan uploaded.");
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

  return (
    <section className="care-plan-panel">
      <div className="section-label">Care plan</div>

      {status && <p className="call-status">{status}</p>}
      {error && <p className="call-error">{error}</p>}

      {plan ? (
        <div className="care-plan-current">
          <p>
            <strong>Attached:</strong> {plan.title ?? "Care plan"}
            {plan.status ? ` (${plan.status})` : ""}
          </p>
          {plan.goals.length > 0 && (
            <p className="muted" style={{ fontSize: 13.5 }}>
              {plan.goals.length} goal{plan.goals.length === 1 ? "" : "s"},{" "}
              {plan.activities.length} activit
              {plan.activities.length === 1 ? "y" : "ies"}
            </p>
          )}
          <button className="btn btn-ghost" onClick={handleRemove} disabled={busy}>
            Remove
          </button>
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 13.5 }}>
          No care plan attached.
        </p>
      )}

      <div className="call-block">
        <label className="field">
          <span className="field-label">Upload FHIR file (.json / .xml)</span>
          <input type="file" accept=".json,.xml,application/json,text/xml"
                 onChange={handleFile} disabled={busy} />
        </label>
        <span className="field-label" style={{ marginTop: 8 }}>
          …or paste FHIR JSON / XML
        </span>
        <textarea
          className="input"
          rows={4}
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder='{"resourceType": "CarePlan", ...}'
        />
        <button className="btn" onClick={() => upload(pasted)} disabled={busy}
                style={{ marginTop: 6 }}>
          Upload pasted plan
        </button>
      </div>
    </section>
  );
}
