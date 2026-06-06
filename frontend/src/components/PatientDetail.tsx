import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CheckIn, Patient, WearableReading } from "../types";
import { CallPanel } from "./CallPanel";
import { HealthTimeline } from "./HealthTimeline";
import { StatusBadge } from "./StatusBadge";

export function PatientDetail({ patient }: { patient: Patient }) {
  const [checkins, setCheckins] = useState<CheckIn[]>([]);
  const [wearables, setWearables] = useState<WearableReading[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([api.getCheckins(patient.id), api.getWearables(patient.id)])
      .then(([c, w]) => {
        if (!cancelled) {
          setCheckins(c);
          setWearables(w);
        }
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  const latest = wearables[0];

  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{patient.name}</h2>
          <div className="muted">
            Age {patient.age} · {patient.practice}
          </div>
        </div>
        <StatusBadge status={patient.status} />
      </div>

      {error && <p className="error">Failed to load: {error}</p>}

      {latest && (
        <div className="vitals">
          <div className="vital-card">
            <span className="vital-value">{latest.heart_rate}</span>
            <span className="vital-label">bpm</span>
          </div>
          <div className="vital-card">
            <span className="vital-value">{latest.steps}</span>
            <span className="vital-label">steps today</span>
          </div>
          <div className="vital-card">
            <span className="vital-value">{latest.sleep_hours}h</span>
            <span className="vital-label">sleep</span>
          </div>
        </div>
      )}

      <CallPanel patient={patient} />

      <h3>Health timeline</h3>
      <HealthTimeline checkins={checkins} wearables={wearables} />
    </div>
  );
}
