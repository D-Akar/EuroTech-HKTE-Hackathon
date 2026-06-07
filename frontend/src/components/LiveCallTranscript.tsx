import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ConversationTurn } from "../types";

/** Streams a live call's transcript over SSE, rendering turns as they are spoken.
 *
 * Body only: the surrounding chrome (live indicator, title, close) belongs to the
 * `LiveCallModal` that hosts this. Opens one EventSource to the backend's `/live`
 * proxy of the ElevenLabs monitor socket, appends a turn on each `turn` event, and
 * on `end` (call finished) closes the stream and calls `onEnded`. */
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
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns.length]);

  const visible = turns.filter((t) => t.message || t.role === "tool");

  if (visible.length === 0) {
    return (
      <div className="live-empty">
        {live ? (
          <>
            <span className="live-empty-dot" aria-hidden />
            <p>Connecting to the call. The transcript appears as soon as anyone speaks.</p>
          </>
        ) : (
          <p>No transcript was captured for this call.</p>
        )}
      </div>
    );
  }

  return (
    <div className="live-stream">
      {visible.map((t, i) =>
        t.role === "tool" ? (
          <ToolRow key={i} name={t.tool_name} detail={t.message} />
        ) : (
          <div key={i} className={`conv-turn conv-turn-${t.role}`}>
            <span className="conv-turn-role">
              {t.role === "agent" ? "Agent" : "Patient"}
            </span>
            <span className="conv-turn-msg">{t.message}</span>
          </div>
        ),
      )}
      <div ref={endRef} />
    </div>
  );
}

/** An agent action (tool call) rendered as a quiet, discrete row, distinct from
 *  speech. Genuine escalations carry the urgent accent; routine lookups stay calm. */
function ToolRow({ name, detail }: { name?: string | null; detail?: string | null }) {
  const urgent = isUrgentTool(name);
  return (
    <div className={`conv-tool${urgent ? " is-urgent" : ""}`} title={detail ?? undefined}>
      {urgent ? <AlertIcon /> : <ToolIcon />}
      <span className="conv-tool-name">{formatToolName(name)}</span>
      {detail && <span className="conv-tool-detail">{detail}</span>}
    </div>
  );
}

/** Escalations are the one tool call that warrants visual weight. */
function isUrgentTool(name?: string | null): boolean {
  return /escalat|emergency|urgent|nurse/i.test(name ?? "");
}

/** "escalate_emergency" -> "Escalate emergency" for a human-readable action label. */
function formatToolName(name?: string | null): string {
  if (!name) return "Action taken";
  const spaced = name.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function ToolIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14.5 5.5a3.5 3.5 0 0 1-4.6 4.3L5 14.7a1.7 1.7 0 1 0 2.4 2.4l4.9-4.9a3.5 3.5 0 0 0 4.3-4.6l-2 2-2-2 2-2.1Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3.5 21 19H3L12 3.5Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M12 10v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="12" cy="16.6" r="0.95" fill="currentColor" />
    </svg>
  );
}
