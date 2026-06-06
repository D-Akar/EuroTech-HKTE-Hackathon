import type { StatBlock, Summary, WearableReading } from "../types";
import { Sparkline } from "./Sparkline";

const TREND_POINTS = 30;

// Oldest-to-newest series for one metric, dropping zero/missing days so the line
// reflects real readings only.
function series(wearables: WearableReading[], pick: (w: WearableReading) => number): number[] {
  return [...wearables]
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map(pick)
    .filter((v) => Number.isFinite(v) && v > 0)
    .slice(-TREND_POINTS);
}

export function TrendsPanel({
  summary,
  wearables,
}: {
  summary: Summary | null;
  wearables: WearableReading[];
}) {
  if (!summary) return null;

  return (
    <section aria-label="Trends">
      <div className="section-label">Trends · {summary.days} days</div>
      <div className="trend-list">
        {summary.heart_rate && (
          <TrendRow
            label="Resting HR"
            avg={`${summary.heart_rate.avg}`}
            unit="bpm"
            range={`${summary.heart_rate.min}-${summary.heart_rate.max}`}
            values={series(wearables, (w) => w.heart_rate)}
          />
        )}
        {summary.sleep_hours && (
          <TrendRow
            label="Sleep"
            avg={`${summary.sleep_hours.avg}`}
            unit="h"
            range={`${summary.sleep_hours.min}-${summary.sleep_hours.max}`}
            values={series(wearables, (w) => w.sleep_hours)}
          />
        )}
        {summary.steps && (
          <TrendRow
            label="Steps"
            avg={Math.round(summary.steps.avg).toLocaleString()}
            unit=""
            range={`${Math.round(summary.steps.min).toLocaleString()}-${Math.round(summary.steps.max).toLocaleString()}`}
            values={series(wearables, (w) => w.steps)}
          />
        )}
        {summary.spo2 && <StatRow label="Blood oxygen" stat={summary.spo2} unit="%" eventKey="low_events" eventWord="low" />}
        {summary.stress && <StatRow label="Stress" stat={summary.stress} unit="" eventKey="high_events" eventWord="high" />}
      </div>
    </section>
  );
}

function TrendRow({
  label,
  avg,
  unit,
  range,
  values,
}: {
  label: string;
  avg: string;
  unit: string;
  range: string;
  values: number[];
}) {
  return (
    <div className="trend-row">
      <div className="trend-meta">
        <span className="trend-label">{label}</span>
        <span className="trend-avg num">
          {avg}
          {unit && <span className="trend-unit"> {unit}</span>}
        </span>
        <span className="trend-range num">{range}</span>
      </div>
      <Sparkline values={values} label={label} />
    </div>
  );
}

function StatRow({
  label,
  stat,
  unit,
  eventKey,
  eventWord,
}: {
  label: string;
  stat: StatBlock;
  unit: string;
  eventKey: "low_events" | "high_events";
  eventWord: string;
}) {
  const events = stat[eventKey] ?? 0;
  return (
    <div className="trend-row">
      <div className="trend-meta">
        <span className="trend-label">{label}</span>
        <span className="trend-avg num">
          {stat.avg}
          {unit && <span className="trend-unit">{unit}</span>}
        </span>
        <span className="trend-range num">
          {stat.min}-{stat.max}
        </span>
      </div>
      <span className={`event-chip ${events > 0 ? "warn" : "ok"}`}>
        {events > 0 ? `${events} ${eventWord} events` : "in range"}
      </span>
    </div>
  );
}
