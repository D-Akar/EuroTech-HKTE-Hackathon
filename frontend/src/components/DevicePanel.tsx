import type { Alert, LiveVitals, Summary, WearableReading } from "../types";
import { AlertList } from "./AlertList";
import { LivePanel } from "./LivePanel";
import { TrendsPanel } from "./TrendsPanel";

// The wearable side of a patient: real-time vitals (featured patient), care alerts,
// trend sparklines, and the recent device-reading history.

interface Props {
  isFeatured: boolean;
  live: LiveVitals | null;
  liveLoading: boolean;
  summary: Summary | null;
  wearables: WearableReading[];
  alerts: Alert[];
  loading: boolean;
  onEscalateCall: () => void;
  callBusy: boolean;
  callMessage: { text: string; error: boolean } | null;
}

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function DevicePanel({
  isFeatured,
  live,
  liveLoading,
  summary,
  wearables,
  alerts,
  loading,
  onEscalateCall,
  callBusy,
  callMessage,
}: Props) {
  const latest = wearables[0];

  return (
    <>
      {isFeatured ? (
        <LivePanel
          live={live}
          loading={liveLoading}
          onEscalateCall={onEscalateCall}
          callBusy={callBusy}
          callMessage={callMessage}
        />
      ) : (
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
      )}

      <div className="section-label">Care alerts</div>
      {loading ? <div className="skeleton skeleton-row" /> : <AlertList alerts={alerts} />}

      {isFeatured && <TrendsPanel summary={summary} wearables={wearables} />}

      <div className="section-label">Recent device readings</div>
      <DeviceReadings wearables={wearables} loading={loading} />
    </>
  );
}

function DeviceReadings({
  wearables,
  loading,
}: {
  wearables: WearableReading[];
  loading: boolean;
}) {
  if (loading) return <div className="skeleton skeleton-row" />;

  const rows = [...wearables]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 14);

  if (rows.length === 0) return <p className="muted">No device readings yet.</p>;

  return (
    <ol className="reading-list">
      {rows.map((w) => (
        <li key={w.id} className="reading-row">
          <span className="reading-date num">{fmtDate(w.timestamp)}</span>
          <span className="reading-vals num">
            {w.heart_rate > 0 ? `${w.heart_rate} bpm` : "-"} ·{" "}
            {w.steps > 0 ? `${w.steps.toLocaleString()} steps` : "-"} ·{" "}
            {w.sleep_hours > 0 ? `${w.sleep_hours}h` : "-"}
          </span>
        </li>
      ))}
    </ol>
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
