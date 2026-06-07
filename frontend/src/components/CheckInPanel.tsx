import type { CheckIn } from "../types";

// Stored phone check-ins, shown as a conversation history: when the AI companion
// called, whether the patient picked up, and what was discussed (mood, pain, notes).
// Most recent first.

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

export function CheckInPanel({
  checkins,
  loading,
}: {
  checkins: CheckIn[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="convo-list">
        {[0, 1, 2].map((i) => (
          <div key={i} className="convo-card skeleton" style={{ height: 96 }} />
        ))}
      </div>
    );
  }

  // Newest first. Several calls land on the same day and CheckIn carries only a
  // date (no time), so ties on date are broken by id - call-derived ids increment
  // in creation order, so the most recent check-in sorts to the top.
  const sorted = [...checkins].sort((a, b) => {
    const byDate = new Date(b.date).getTime() - new Date(a.date).getTime();
    return byDate !== 0 ? byDate : b.id - a.id;
  });

  if (sorted.length === 0) {
    return <p className="muted convo-empty">No phone check-ins recorded yet.</p>;
  }

  return (
    <div className="convo-list">
      {sorted.map((c) => (
        <ConversationCard key={c.id} checkin={c} />
      ))}
    </div>
  );
}

function ConversationCard({ checkin }: { checkin: CheckIn }) {
  const painTone =
    checkin.pain_level >= 6 ? "hot" : checkin.pain_level >= 3 ? "warm" : "";
  return (
    <article className={`convo-card ${checkin.answered ? "" : "convo-missed"}`}>
      <div className="convo-head">
        <span className="convo-date num">{fmtDate(checkin.date)}</span>
        <span className={`tag ${checkin.answered ? "tag-ok" : "tag-missed"}`}>
          {checkin.answered ? "Answered" : "No answer"}
        </span>
      </div>

      {checkin.answered ? (
        <>
          <div className="convo-chips">
            <span className="convo-chip">Mood · {checkin.mood}</span>
            <span className={`convo-chip ${painTone}`}>
              Pain · {checkin.pain_level}/10
            </span>
          </div>
          {checkin.notes && (
            <p className="convo-note">
              <span className="convo-label">Discussed</span>
              {checkin.notes}
            </p>
          )}
        </>
      ) : (
        <p className="convo-note muted">
          {checkin.notes || "No answer - voicemail left."}
        </p>
      )}
    </article>
  );
}
