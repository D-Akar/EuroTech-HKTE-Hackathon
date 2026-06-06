import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Alert,
  CheckIn,
  LiveVitals,
  MedicalProfile,
  Patient,
  Summary,
  WearableReading,
} from "../types";
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
  const [profile, setProfile] = useState<MedicalProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isFhirBacked = patient.fhir_id != null;

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
      // Real clinical record for MongoDB-backed slots; null (404) for mock patients.
      isFhirBacked ? api.getProfile(patient.id).catch(() => null) : Promise.resolve(null),
    ]);
    requests
      .then(([c, w, a, s, prof]) => {
        if (cancelled) return;
        setCheckins(c);
        setWearables(w);
        setAlerts(a);
        setSummary(s);
        setProfile(prof);
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patient.id, isFeatured, isFhirBacked]);

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
              {isFhirBacked && <span className="fhir-tag">Real record · FHIR</span>}
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

        {isFhirBacked && (
          <>
            <div className="section-label">Medical profile · from records</div>
            {loading ? (
              <div className="skeleton skeleton-row" />
            ) : profile ? (
              <MedicalProfileSection profile={profile} />
            ) : (
              <p className="muted">Record unavailable.</p>
            )}
          </>
        )}

        <CallPanel patient={patient} />

        <div className="section-label">Health timeline</div>
        <HealthTimeline checkins={checkins} wearables={wearables} />
      </div>
    </section>
  );
}

function MedicalProfileSection({ profile }: { profile: MedicalProfile }) {
  const meta = [
    profile.gender,
    profile.birth_date ? `b. ${profile.birth_date}` : null,
    profile.preferred_language ? `speaks ${profile.preferred_language}` : null,
  ].filter(Boolean);

  return (
    <div className="med-profile">
      {meta.length > 0 && <div className="med-meta">{meta.join(" · ")}</div>}

      <MedGroup
        title="Chronic conditions"
        empty="No recorded conditions."
        items={profile.chronic_conditions.map((c) => ({
          key: c.name + (c.onset_date ?? ""),
          label: c.name,
          sub: c.onset_date ? `since ${c.onset_date}` : null,
        }))}
      />

      <MedGroup
        title="Active medications"
        empty="No active medications."
        items={profile.active_medications.map((m, i) => ({
          key: m.name + i,
          label: m.name,
          sub: m.frequency,
        }))}
      />

      <div className="med-group">
        <div className="med-group-title">
          Allergies{profile.allergies.length > 0 && ` · ${profile.allergies.length}`}
        </div>
        {profile.allergies.length === 0 ? (
          <p className="muted">No known allergies.</p>
        ) : (
          <div className="med-chips">
            {profile.allergies.map((a, i) => (
              <span
                key={a.substance + i}
                className={`med-chip allergy ${a.criticality === "high" ? "critical" : ""}`}
                title={[a.type, a.criticality && `${a.criticality} criticality`]
                  .filter(Boolean)
                  .join(" · ")}
              >
                {a.substance}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MedGroup({
  title,
  empty,
  items,
}: {
  title: string;
  empty: string;
  items: { key: string; label: string; sub: string | null }[];
}) {
  return (
    <div className="med-group">
      <div className="med-group-title">
        {title}
        {items.length > 0 && ` · ${items.length}`}
      </div>
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="med-list">
          {items.map((it) => (
            <li key={it.key}>
              <span className="med-name">{it.label}</span>
              {it.sub && <span className="med-sub">{it.sub}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
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
