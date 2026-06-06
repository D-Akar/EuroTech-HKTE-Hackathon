import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { CityTwin } from "./components/CityTwin";
import { PatientDetail } from "./components/PatientDetail";
import { PatientList } from "./components/PatientList";
import { useLiveVitals } from "./hooks/useLiveVitals";
import { useBleHeartRate } from "./hooks/useBleHeartRate";
import { useTheme } from "./hooks/useTheme";
import { assessLive } from "./lib/liveAssessment";
import { STATUS, STATUS_ORDER } from "./city";
import type { LiveVitals, Meta, Patient, PatientStatus, PatientStatusEvent } from "./types";

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<Set<PatientStatus>>(new Set());
  const [demo, setDemo] = useState(false);
  const [manualHr, setManualHr] = useState<number | null>(null); // demo: operator-pinned HR
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .listPatients()
      .then((p) => setPatients(p))
      .catch((e) => setError(String(e)))
      .finally(() => setLoaded(true));
    api.getMeta().then(setMeta).catch(() => {});
  }, []);

  // Real-time escalations: a `POST /patients/{id}/escalate` (e.g. triggered when
  // urgent info surfaces on a phone call) pushes a `patient_status` event over
  // SSE, recoloring that patient green/amber -> red on the twin and roster the
  // instant it lands - no refresh, no polling. EventSource auto-reconnects.
  useEffect(() => {
    const es = new EventSource(api.eventsUrl());
    es.addEventListener("patient_status", (e) => {
      try {
        const evt = JSON.parse((e as MessageEvent).data) as PatientStatusEvent;
        setPatients((prev) =>
          prev.map((p) =>
            p.id === evt.patient_id ? { ...p, status: evt.status } : p,
          ),
        );
      } catch {
        /* ignore malformed frames */
      }
    });
    return () => es.close();
  }, []);

  const [theme, toggleTheme] = useTheme();
  const featuredId = meta?.featured_patient_id ?? null;
  const live = useLiveVitals(featuredId, demo, manualHr);
  const ble = useBleHeartRate();

  // When the watch is streaming over Bluetooth (and we're not running the scripted demo),
  // its per-second heart rate becomes the featured patient's live HR. Re-running the same
  // assessment as the backend means the real heartbeat drives the status + escalation, so
  // running around recolors the patient on the twin in real time.
  const liveData = useMemo<LiveVitals | null>(() => {
    const base = live.data;
    const useBle = !demo && ble.status === "connected" && ble.bpm != null;
    if (!useBle) return base;
    const heart_rate = { value: ble.bpm as number, unit: "bpm", at: ble.at };
    const vitals = {
      heart_rate,
      steps: base?.steps ?? null,
      spo2: base?.spo2 ?? null,
      stress: base?.stress ?? null,
    };
    return { source: "ble", ...vitals, ...assessLive(featuredId ?? 0, vitals) };
  }, [live.data, ble.status, ble.bpm, ble.at, demo, featuredId]);

  // Overlay the featured patient's live-derived status so the roster and twin
  // recolor the moment a live vital crosses a threshold. Only real-time sources
  // override the baseline; stale export values keep the patient's standing status.
  const displayPatients = useMemo(() => {
    const data = liveData;
    const realtime = data?.source === "live" || data?.source === "demo" || data?.source === "ble";
    if (featuredId == null || !data || !realtime || data.status === "none") return patients;
    const status = data.status;
    return patients.map((p) => (p.id === featuredId ? { ...p, status } : p));
  }, [patients, featuredId, liveData]);

  // Opening the demo jumps to the featured patient so the escalation is on screen.
  useEffect(() => {
    if (demo && featuredId != null) setSelectedId(featuredId);
    if (!demo) setManualHr(null); // leaving demo drops any pinned heart rate
  }, [demo, featuredId]);

  const counts = useMemo(() => {
    const c: Record<PatientStatus, number> = { stable: 0, attention: 0, urgent: 0 };
    for (const p of displayPatients) c[p.status]++;
    return c;
  }, [displayPatients]);

  const selected = displayPatients.find((p) => p.id === selectedId) ?? null;
  const activeFilter = filter.size === 0 ? null : (filter as Set<string>);

  function toggleStatus(s: PatientStatus) {
    setFilter((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  return (
    <div className="app">
      <header className="command-bar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            <CareloopMark />
          </span>
          Careloop
          <span className="brand-sub">Hong Kong care grid</span>
        </div>

        <div className="command-spacer" />

        <div className="watch-strip" role="group" aria-label="Filter by status">
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              className="watch-chip"
              aria-pressed={filter.has(s)}
              onClick={() => toggleStatus(s)}
              title={`${counts[s]} ${STATUS[s].label}`}
            >
              <span
                className="watch-dot"
                style={{ background: STATUS[s].color, borderRadius: s === "stable" ? "50%" : s === "urgent" ? 2 : 3 }}
              />
              <span className="watch-label">{STATUS[s].short}</span>
              <span className="watch-count num">{counts[s]}</span>
            </button>
          ))}
        </div>

        {ble.supported && (
          <button
            className={`demo-chip watch-chip-ble ${ble.status === "connected" ? "on" : ""}`}
            aria-pressed={ble.status === "connected"}
            onClick={() => (ble.status === "connected" ? ble.disconnect() : ble.connect())}
            disabled={featuredId == null || ble.status === "connecting"}
            title={
              ble.status === "connected"
                ? `Streaming real-time heart rate from ${ble.deviceName ?? "your watch"}. Click to stop.`
                : "Stream real-time heart rate from your watch over Bluetooth (enable Broadcast Heart Rate on the watch)"
            }
          >
            <span className="demo-dot" aria-hidden />
            {ble.status === "connected"
              ? `Watch ${ble.bpm ?? "--"} bpm`
              : ble.status === "connecting"
                ? "Connecting..."
                : ble.status === "error"
                  ? "Retry watch"
                  : "Connect watch"}
          </button>
        )}

        <button
          className={`demo-chip ${demo ? "on" : ""}`}
          aria-pressed={demo}
          onClick={() => setDemo((d) => !d)}
          title={
            demo
              ? "Simulated exertion ramp is playing (not live device data). Click to return to live."
              : "Play a simulated exertion ramp for the featured patient (stage demo)"
          }
          disabled={featuredId == null}
        >
          <span className="demo-dot" aria-hidden />
          {demo ? "Simulating" : "Demo"}
        </button>

        {demo && (
          <div className="hr-presets" role="group" aria-label="Manual heart rate (demo)">
            {[
              { hr: 60, label: "Resting" },
              { hr: 90, label: "Elevated" },
              { hr: 110, label: "Urgent" },
            ].map(({ hr, label }) => (
              <button
                key={hr}
                className={`demo-chip hr-preset ${hr >= 110 ? "hr-preset-urgent" : ""} ${manualHr === hr ? "on" : ""}`}
                aria-pressed={manualHr === hr}
                onClick={() => setManualHr(hr)}
                title={`Hold the featured patient's heart rate at ${hr} bpm`}
              >
                {label} · {hr}
              </button>
            ))}
            <button
              className={`demo-chip hr-preset ${manualHr === null ? "on" : ""}`}
              aria-pressed={manualHr === null}
              onClick={() => setManualHr(null)}
              title="Resume the automatic exertion ramp"
            >
              Ramp
            </button>
          </div>
        )}

        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>

        <Clock />
      </header>

      {error && (
        <div className="banner-error">
          Backend unreachable on :8000 ({error}). Is the API running?
        </div>
      )}

      <div className="layout">
        <PatientList
          patients={displayPatients}
          selectedId={selectedId}
          featuredId={featuredId}
          statusFilter={activeFilter}
          onSelect={setSelectedId}
        />

        <div className="stage">
          {displayPatients.length > 0 && (
            <CityTwin
              patients={displayPatients}
              selectedId={selectedId}
              statusFilter={activeFilter}
              onSelect={setSelectedId}
            />
          )}

          <div className="stage-overlay">
            <div className="stage-title">
              <h2>Live care twin · Hong Kong</h2>
              <p>
                {displayPatients.length} patients monitored ·{" "}
                {counts.urgent > 0
                  ? `${counts.urgent} needing immediate care`
                  : "all under watch"}
              </p>
            </div>
            <div className="legend">
              {STATUS_ORDER.map((s) => (
                <span className="legend-item" key={s}>
                  <span className={`legend-swatch ${s}`} />
                  {STATUS[s].label}
                </span>
              ))}
            </div>
          </div>

          {loaded && displayPatients.length === 0 && !error && (
            <div className="stage-empty">
              <div>
                <h2>No patients yet</h2>
                <p>Patients will light up across the city as they join the care grid.</p>
              </div>
            </div>
          )}

          <div className="stage-hint">Drag to orbit · scroll to zoom · click a light</div>

          {selected && (
            <PatientDetail
              patient={selected}
              onClose={() => setSelectedId(null)}
              featuredId={featuredId}
              live={liveData}
              liveLoading={live.loading}
              onPatientUpdate={(updated) =>
                setPatients((prev) =>
                  prev.map((p) => (p.id === updated.id ? updated : p))
                )
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="clock num" title="Local time">
      {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </div>
  );
}

function CareloopMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="3.2" fill="white" />
      <circle cx="12" cy="12" r="7.5" stroke="white" strokeWidth="1.6" opacity="0.85" />
      <circle cx="12" cy="12" r="11" stroke="white" strokeWidth="1.2" opacity="0.45" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
