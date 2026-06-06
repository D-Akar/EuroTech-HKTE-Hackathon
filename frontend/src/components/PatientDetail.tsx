import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Alert, CheckIn, LiveVitals, Patient, Summary, WearableReading } from "../types";
import { AlertList } from "./AlertList";
import { CallPanel } from "./CallPanel";
import { HealthTimeline } from "./HealthTimeline";
import { LivePanel } from "./LivePanel";
import { StatusBadge } from "./StatusBadge";
import { TrendsPanel } from "./TrendsPanel";

interface Props {
  patient: Patient;
  onClose: () => void;
  featuredId: number | null;
  live: LiveVitals | null;
  liveLoading: boolean;
}

export function PatientDetail({ patient, onClose, featuredId, live, liveLoading }: Props) {
  const isFeatured = featuredId != null && patient.id === featuredId;

  const [checkins, setCheckins] = useState<CheckIn[]>([]);
  const [wearables, setWearables] = useState<WearableReading[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [callBusy, setCallBusy] = useState(false);
  const [callMessage, setCallMessage] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setLoading(true);
    setCallMessage(null);
    const requests = Promise.all([
      api.getCheckins(patient.id),
      api.getWearables(patient.id),
      api.getAlerts(patient.id),
      isFeatured ? api.getSummary(patient.id) : Promise.resolve(null),
    ]);
    requests
      .then(([c, w, a, s]) => {
        if (cancelled) return;
        setCheckins(c);
        setWearables(w);
        setAlerts(a);
        setSummary(s);
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patient.id, isFeatured]);

  async function handleEscalateCall() {
    setCallBusy(true);
    setCallMessage(null);
    try {
      const record = await api.triggerCall(patient.id, {});
      setCallMessage(
        record.status === "initiated"
          ? { text: "Check-in call initiated.", error: false }
          : { text: record.error ?? "Call failed.", error: true },
      );
    } catch (e) {
      setCallMessage({ text: String(e), error: true });
    } finally {
      setCallBusy(false);
    }
  }

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
            <div className="detail-tags">
              <StatusBadge status={patient.status} />
              {isFeatured && <span className="you-tag">You · live device</span>}
              <a
                className="report-link"
                href={api.reportUrl(patient.id)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Download clinician report
              </a>
            </div>
          </div>
          <button className="detail-close" onClick={onClose} aria-label="Close patient detail">
            X
          </button>
        </div>

        {error && <p className="call-error">Failed to load: {error}</p>}

        {isFeatured ? (
          <>
            <LivePanel
              live={live}
              loading={liveLoading}
              onEscalateCall={handleEscalateCall}
              callBusy={callBusy}
              callMessage={callMessage}
            />
            <div className="section-label">Care alerts</div>
            {loading ? <div className="skeleton skeleton-row" /> : <AlertList alerts={alerts} />}
            <TrendsPanel summary={summary} wearables={wearables} />
          </>
        ) : (
          <>
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
                  <Vital value={latest.steps.toLocaleString()} label="Steps" />
                  <Vital value={latest.sleep_hours} unit="h" label="Sleep" />
                </>
              ) : (
                <p className="muted">No wearable data.</p>
              )}
            </div>
            <div className="section-label">Care alerts</div>
            {loading ? <div className="skeleton skeleton-row" /> : <AlertList alerts={alerts} />}
          </>
        )}

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
