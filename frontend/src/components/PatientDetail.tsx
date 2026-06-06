import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CheckIn, Patient, WearableReading } from "../types";
import { CallPanel } from "./CallPanel";
import { HealthTimeline } from "./HealthTimeline";
import { StatusBadge } from "./StatusBadge";

export function PatientDetail({ patient, onClose }: { patient: Patient; onClose: () => void }) {
  const [checkins, setCheckins] = useState<CheckIn[]>([]);
  const [wearables, setWearables] = useState<WearableReading[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoading(true);
    Promise.all([api.getCheckins(patient.id), api.getWearables(patient.id)])
      .then(([c, w]) => {
        if (cancelled) return;
        setCheckins(c);
        setWearables(w);
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  const latest = wearables[0];

  return (
    <section className="detail" aria-label={`${patient.name} detail`}>
      <div className="detail-scroll">
        <div className="detail-header">
          <div>
            <h2>{patient.name}</h2>
            <div className="detail-meta">
              {patient.district} · Age {patient.age} · {patient.practice}
            </div>
            <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 12 }}>
              <StatusBadge status={patient.status} />
              <a
                className="report-link"
                href={api.reportUrl(patient.id)}
                target="_blank"
                rel="noopener noreferrer"
              >
                ↓ Download clinician report
              </a>
            </div>
          </div>
          <button className="detail-close" onClick={onClose} aria-label="Close patient detail">
            ✕
          </button>
        </div>

        {error && <p className="call-error">Failed to load: {error}</p>}

        <div className="vitals">
          {loading ? (
            <>
              <div className="vital-card skeleton" style={{ height: 78 }} />
              <div className="vital-card skeleton" style={{ height: 78 }} />
              <div className="vital-card skeleton" style={{ height: 78 }} />
            </>
          ) : latest ? (
            <>
              <Vital value={latest.heart_rate} unit="bpm" label="Heart rate" />
              <Vital value={latest.steps.toLocaleString()} label="Steps today" />
              <Vital value={latest.sleep_hours} unit="h" label="Sleep" />
            </>
          ) : (
            <p className="muted">No wearable data.</p>
          )}
        </div>

        <CallPanel patient={patient} />

        <div className="section-label">Health timeline</div>
        <HealthTimeline checkins={checkins} wearables={wearables} />
      </div>
    </section>
  );
}

function Vital({ value, unit, label }: { value: number | string; unit?: string; label: string }) {
  return (
    <div className="vital-card">
      <div>
        <span className="vital-value num">{value}</span>
        {unit && <span className="vital-unit">{unit}</span>}
      </div>
      <span className="vital-label">{label}</span>
    </div>
  );
}
