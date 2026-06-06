import { useEffect, useState } from "react";
import type { LiveSource, LiveVitals } from "../types";

const SOURCE_META: Record<LiveSource, { label: string; cls: string; live: boolean }> = {
  live: { label: "Live", cls: "live", live: true },
  ble: { label: "Watch live", cls: "live", live: true },
  demo: { label: "Simulated", cls: "demo", live: true },
  "export-fallback": { label: "Recent export", cls: "fallback", live: false },
  none: { label: "Offline", cls: "fallback", live: false },
};

// Re-render once a second so the "updated Ns ago" readout ticks up between polls.
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

// Relative age of the freshest reading. Timezone-proof: it never shows a clock, so a
// Hong Kong-stamped sample reads correctly no matter where the operator is.
function ago(at: string | null, now: number): string {
  if (!at) return "";
  const ms = now - new Date(at).getTime();
  if (!Number.isFinite(ms)) return "";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

interface Props {
  live: LiveVitals | null;
  loading: boolean;
  onEscalateCall: () => void;
  callBusy: boolean;
  callMessage: { text: string; error: boolean } | null;
}

export function LivePanel({ live, loading, onEscalateCall, callBusy, callMessage }: Props) {
  // Hook stays above the early returns so its call order is stable across renders.
  const now = useNow(live?.source === "live" || live?.source === "ble");

  if (loading && !live) {
    return (
      <section className="live" aria-label="Live vitals">
        <div className="live-head">
          <span className="section-label" style={{ margin: 0 }}>Live vitals</span>
        </div>
        <div className="live-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="live-tile skeleton" style={{ height: 70 }} />
          ))}
        </div>
      </section>
    );
  }

  if (!live || live.source === "none") return null;

  const src = SOURCE_META[live.source];
  const urgent = live.status === "urgent";
  const isDemo = live.source === "demo";
  const syncedAt = live.heart_rate?.at ?? live.steps?.at ?? null;
  const freshness = isDemo
    ? "scripted ramp"
    : live.source === "live" || live.source === "ble"
      ? `updated ${ago(syncedAt, now)}`
      : "last export";
  const criticalMsg =
    live.alerts.find((a) => a.severity === "critical")?.message ?? live.alerts[0]?.message;

  return (
    <section className={`live ${urgent ? "live-urgent" : ""}`} aria-label="Live vitals">
      <div className="live-head">
        <span className="section-label" style={{ margin: 0 }}>Live vitals</span>
        <span className={`source-pill ${src.cls}`}>
          {src.live && <span className="source-dot" aria-hidden />}
          {src.label}
        </span>
        <span className="live-synced num">{freshness}</span>
      </div>

      {isDemo && (
        <p className="live-sim-note" role="note">
          Simulated exertion ramp for the stage demo. This is not live device data.
        </p>
      )}

      <div className="live-grid">
        <LiveTile
          label="Heart rate"
          value={live.heart_rate?.value}
          unit="bpm"
          beat={src.live}
          urgent={urgent}
        />
        <LiveTile label="Steps today" value={live.steps?.value} thousands />
        <LiveTile label="Blood oxygen" value={live.spo2?.value} unit="%" />
        <LiveTile label="Stress" value={live.stress?.value} />
      </div>

      {urgent && criticalMsg && (
        <div className="escalation" role="alert">
          <div className="escalation-body">
            <span className="escalation-title">Escalation</span>
            <span className="escalation-msg">{criticalMsg}</span>
            {callMessage && (
              <span className={`escalation-result ${callMessage.error ? "error" : "ok"}`}>
                {callMessage.text}
              </span>
            )}
          </div>
          <button
            className="btn btn-call escalation-btn"
            onClick={onEscalateCall}
            disabled={callBusy}
          >
            {callBusy ? "Calling..." : "Place check-in call"}
          </button>
        </div>
      )}
    </section>
  );
}

function LiveTile({
  label,
  value,
  unit,
  thousands,
  beat,
  urgent,
}: {
  label: string;
  value: number | null | undefined;
  unit?: string;
  thousands?: boolean;
  beat?: boolean;
  urgent?: boolean;
}) {
  const display =
    value == null ? "--" : thousands ? Math.round(value).toLocaleString() : Math.round(value);
  return (
    <div className={`live-tile ${urgent ? "tone-urgent" : ""}`}>
      <div className="live-tile-value">
        {beat && <span className="beat" aria-hidden />}
        <span className="num">{display}</span>
        {unit && <span className="live-tile-unit">{unit}</span>}
      </div>
      <span className="live-tile-label">{label}</span>
    </div>
  );
}
