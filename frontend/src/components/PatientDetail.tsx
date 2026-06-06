import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Alert, CheckIn, LiveVitals, Patient, Summary, WearableReading } from "../types";
import { CallPanel } from "./CallPanel";
import { CheckInPanel } from "./CheckInPanel";
import { DevicePanel } from "./DevicePanel";
import { StatusBadge } from "./StatusBadge";

interface Props {
  patient: Patient;
  onClose: () => void;
  featuredId: number | null;
  live: LiveVitals | null;
  liveLoading: boolean;
}

type DetailTab = "checkins" | "device";

export function PatientDetail({ patient, onClose, featuredId, live, liveLoading }: Props) {
  const isFeatured = featuredId != null && patient.id === featuredId;

  const [tab, setTab] = useState<DetailTab>("checkins");
  const [checkins, setCheckins] = useState<CheckIn[]>([]);
  const [wearables, setWearables] = useState<WearableReading[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [callBusy, setCallBusy] = useState(false);
  const [callMessage, setCallMessage] = useState<{ text: string; error: boolean } | null>(null);

  // Reset to the conversation tab whenever a different patient is opened.
  useEffect(() => setTab("checkins"), [patient.id]);

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

        <div className="detail-tabs" role="tablist" aria-label="Patient data">
          <button
            role="tab"
            aria-selected={tab === "checkins"}
            className={`detail-tab ${tab === "checkins" ? "on" : ""}`}
            onClick={() => setTab("checkins")}
          >
            <PhoneGlyph /> Check-in data
          </button>
          <button
            role="tab"
            aria-selected={tab === "device"}
            className={`detail-tab ${tab === "device" ? "on" : ""}`}
            onClick={() => setTab("device")}
          >
            <PulseGlyph /> Device data
          </button>
        </div>

        {tab === "checkins" ? (
          <>
            <CheckInPanel checkins={checkins} loading={loading} />
            <CallPanel patient={patient} />
          </>
        ) : (
          <DevicePanel
            isFeatured={isFeatured}
            live={live}
            liveLoading={liveLoading}
            summary={summary}
            wearables={wearables}
            alerts={alerts}
            loading={loading}
            onEscalateCall={handleEscalateCall}
            callBusy={callBusy}
            callMessage={callMessage}
          />
        )}
      </div>
    </section>
  );
}

function PhoneGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6.5 4h3l1.5 4-2 1.5a11 11 0 0 0 5 5l1.5-2 4 1.5v3a2 2 0 0 1-2 2A15 15 0 0 1 4.5 6a2 2 0 0 1 2-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PulseGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M3 12h4l2-5 4 10 2-5h6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
