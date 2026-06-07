import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { CityTwin } from "./components/CityTwin";
import { PatientDetail } from "./components/PatientDetail";
import { PatientList } from "./components/PatientList";
import { useLiveVitals } from "./hooks/useLiveVitals";
import { useBleHeartRate } from "./hooks/useBleHeartRate";
import { assessLive } from "./lib/liveAssessment";
import { STATUS, STATUS_ORDER } from "./city";
import type { LiveVitals, Meta, Patient, PatientStatus, PatientStatusEvent } from "./types";

// Heart rate the "Demo" button pins the featured patient at (stage demo).
const DEMO_BPM = 85;

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<Set<PatientStatus>>(new Set());
  const [demo, setDemo] = useState(false);
  const [manualHr, setManualHr] = useState<number | null>(null); // demo: operator-pinned HR
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // Roster drawer: floats as glass over the full-screen twin; collapsible.
  const [sidebarOpen, setSidebarOpen] = useState(true);

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
        <button
          className={`sidebar-toggle ${sidebarOpen ? "on" : ""}`}
          onClick={() => setSidebarOpen((o) => !o)}
          aria-pressed={sidebarOpen}
          aria-label={sidebarOpen ? "Hide roster" : "Show roster"}
          title={sidebarOpen ? "Hide roster" : "Show roster"}
        >
          <PanelIcon />
        </button>

        <div className="brand">
          <img className="brand-logo" src="/careloop-wordmark-light.png" alt="Careloop" />
          <span className="brand-sub">
            Elderly care · monitored live
            <span className="brand-live" aria-hidden />
          </span>
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
          onClick={() => {
            const next = !demo;
            setDemo(next);
            // Demo jumps the featured patient's heart rate straight to a pinned
            // value; clicking again returns to live device data.
            setManualHr(next ? DEMO_BPM : null);
          }}
          title={
            demo
              ? `Holding the featured patient at ${DEMO_BPM} bpm (not live device data). Click to return to live.`
              : `Pin the featured patient's heart rate at ${DEMO_BPM} bpm (stage demo)`
          }
          disabled={featuredId == null}
        >
          <span className="demo-dot" aria-hidden />
          {demo ? "Simulating" : "Demo"}
        </button>

        <Clock />
      </header>

      {error && (
        <div className="banner-error">
          Backend unreachable on :8000 ({error}). Is the API running?
        </div>
      )}

      <div className="layout">
        <div className="stage">
          {displayPatients.length > 0 && (
            <CityTwin
              patients={displayPatients}
              selectedId={selectedId}
              statusFilter={activeFilter}
              onSelect={setSelectedId}
            />
          )}

          {loaded && displayPatients.length === 0 && !error && (
            <div className="stage-empty">
              <div>
                <h2>No patients yet</h2>
                <p>Patients will light up across the city as they join the care grid.</p>
              </div>
            </div>
          )}

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

        <aside
          className={`roster-drawer ${sidebarOpen ? "open" : ""}`}
          aria-hidden={!sidebarOpen}
        >
          <PatientList
            patients={displayPatients}
            selectedId={selectedId}
            featuredId={featuredId}
            statusFilter={activeFilter}
            onSelect={setSelectedId}
          />
        </aside>
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

function PanelIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M9 4v16" />
    </svg>
  );
}

