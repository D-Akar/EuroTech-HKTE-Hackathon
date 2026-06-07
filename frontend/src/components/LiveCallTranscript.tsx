import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ConversationTurn } from "../types";

/** Streams a live call's transcript over SSE, rendering turns as they are spoken.
 *
 * Opens one EventSource to the backend's `/live` proxy of the ElevenLabs monitor
 * socket. Appends a turn on each `turn` event; on `end` (call finished) it closes
 * the stream and calls `onEnded`, so the parent can swap in the post-call view. */
export function LiveCallTranscript({
  patientId,
  callId,
  onEnded,
}: {
  patientId: number;
  callId: number;
  onEnded?: () => void;
}) {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [live, setLive] = useState(true);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const es = new EventSource(api.liveCallUrl(patientId, callId));

    es.addEventListener("turn", (e) => {
      try {
        const turn = JSON.parse((e as MessageEvent).data) as ConversationTurn;
        setTurns((prev) => [...prev, turn]);
      } catch {
        /* ignore malformed frame */
      }
    });

    const finish = () => {
      es.close();
      setLive(false);
      onEnded?.();
    };
    es.addEventListener("end", finish);
    // A transport-level error after the stream is open also means it's over;
    // EventSource would otherwise keep retrying, so close it ourselves.
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) finish();
    };

    return () => es.close();
    // callId/patientId identify the stream; onEnded is stable enough for a demo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, callId]);

  // Keep the newest turn in view as they stream in.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [turns.length]);

  return (
    <div className="conv-detail">
      <div className="conv-detail-head">
        {live ? (
          <span className="live-tag">
            <span className="analysing-dot" aria-hidden /> Live transcript
          </span>
        ) : (
          <span className="tag tag-missed">Ended</span>
        )}
      </div>

      {turns.length === 0 ? (
        <p className="muted">
          {live ? "Waiting for the call to connect…" : "No transcript was captured."}
        </p>
      ) : (
        <div className="conv-transcript">
          {turns
            .filter((t) => t.message)
            .map((t, i) => (
              <div key={i} className={`conv-turn conv-turn-${t.role}`}>
                <span className="conv-turn-role">
                  {t.role === "agent" ? "Agent" : "Patient"}
                </span>
                <span className="conv-turn-msg">{t.message}</span>
              </div>
            ))}
          <div ref={endRef} />
        </div>
      )}
    </div>
  );
}
