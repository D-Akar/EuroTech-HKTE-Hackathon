import type { CheckIn, WearableReading } from "../types";

interface Props {
  checkins: CheckIn[];
  wearables: WearableReading[];
}

type TimelineEvent =
  | { kind: "checkin"; at: number; data: CheckIn }
  | { kind: "wearable"; at: number; data: WearableReading };

export function HealthTimeline({ checkins, wearables }: Props) {
  const events: TimelineEvent[] = [
    ...checkins.map((c) => ({
      kind: "checkin" as const,
      at: new Date(c.date).getTime(),
      data: c,
    })),
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
      {events.map((e) =>
        e.kind === "checkin" ? (
          <li key={`c-${e.data.id}`} className="timeline-item checkin">
            <div className="timeline-date">{e.data.date}</div>
            <div className="timeline-body">
              <strong>Phone check-in</strong>
              {!e.data.answered && <span className="tag tag-missed">No answer</span>}
              <div>
                Mood: {e.data.mood} · Pain {e.data.pain_level}/10
              </div>
              <div className="muted">{e.data.notes}</div>
            </div>
          </li>
        ) : (
          <li key={`w-${e.data.id}`} className="timeline-item wearable">
            <div className="timeline-date">
              {new Date(e.data.timestamp).toLocaleDateString()}
            </div>
            <div className="timeline-body">
              <strong>Wearable reading</strong>
              <div>
                {e.data.heart_rate} bpm · {e.data.steps} steps ·{" "}
                {e.data.sleep_hours}h sleep
              </div>
            </div>
          </li>
        )
      )}
    </ol>
  );
}
