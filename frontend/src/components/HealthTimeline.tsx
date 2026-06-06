import type { CheckIn, WearableReading } from "../types";

interface Props {
  checkins: CheckIn[];
  wearables: WearableReading[];
}

type TimelineEvent =
  | { kind: "checkin"; at: number; data: CheckIn }
  | { kind: "wearable"; at: number; data: WearableReading };

const fmtDate = (ms: number) =>
  new Date(ms).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function HealthTimeline({ checkins, wearables }: Props) {
  const events: TimelineEvent[] = [
    ...checkins.map((c) => ({ kind: "checkin" as const, at: new Date(c.date).getTime(), data: c })),
    ...wearables.map((w) => ({
      kind: "wearable" as const,
      at: new Date(w.timestamp).getTime(),
      data: w,
    })),
  ].sort((a, b) => b.at - a.at);

  if (events.length === 0) {
    return <p className="muted">No timeline data yet.</p>;
  }

  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={`${e.kind}-${e.data.id}`} className="timeline-item">
          <div className="timeline-rail">
            <span className={`timeline-node ${e.kind}`} />
            <span className="timeline-line" />
          </div>
          <div className="timeline-body">
            {e.kind === "checkin" ? (
              <>
                <div className="timeline-row1">
                  <span className="timeline-kind">Phone check-in</span>
                  {e.data.answered ? (
                    <span className="tag tag-ok">Answered</span>
                  ) : (
                    <span className="tag tag-missed">No answer</span>
                  )}
                  <span className="timeline-date">{fmtDate(e.at)}</span>
                </div>
                <div className="timeline-detail">
                  Mood {e.data.mood} · pain {e.data.pain_level}/10
                </div>
                {e.data.notes && <div className="timeline-note">{e.data.notes}</div>}
              </>
            ) : (
              <>
                <div className="timeline-row1">
                  <span className="timeline-kind">Wearable reading</span>
                  <span className="timeline-date">{fmtDate(e.at)}</span>
                </div>
                <div className="timeline-detail num">
                  {e.data.heart_rate} bpm · {e.data.steps.toLocaleString()} steps ·{" "}
                  {e.data.sleep_hours}h sleep
                </div>
              </>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
