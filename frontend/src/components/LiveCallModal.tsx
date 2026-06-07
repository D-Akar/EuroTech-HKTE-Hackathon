import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LiveCallTranscript } from "./LiveCallTranscript";

/** Centered dialog that watches a check-in call's transcript stream in real time.
 *
 * A live call is a focused, transient activity, so it earns a dialog: the busy
 * dashboard recedes behind a scrim while the coordinator listens in. Standard
 * dialog behaviour throughout (Escape + backdrop to close, focus restored to the
 * trigger, body scroll locked, reduced-motion respected). The stream itself lives
 * in `LiveCallTranscript`; this owns only the chrome and the live/ended state. */
export function LiveCallModal({
  patientId,
  callId,
  patientName,
  onClose,
  onEnded,
}: {
  patientId: number;
  callId: number;
  patientName: string;
  onClose: () => void;
  onEnded?: () => void;
}) {
  const [ended, setEnded] = useState(false);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  // Escape to close; restore focus to whatever opened the dialog; lock body scroll.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, [onClose]);

  const handleEnded = () => {
    setEnded(true);
    onEnded?.();
  };

  return createPortal(
    <div className="live-scrim" onMouseDown={onClose}>
      {/* Stop propagation so clicks inside the panel don't dismiss it. */}
      <div
        className="live-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="live-dialog-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="live-dialog-head">
          <div className="live-dialog-titles">
            <span className={`live-state ${ended ? "is-ended" : "is-live"}`}>
              <span className="live-state-dot" aria-hidden />
              {ended ? "Call ended" : "Live"}
            </span>
            <h2 id="live-dialog-title">Check-in call</h2>
            <p className="live-dialog-sub">{patientName}</p>
          </div>
          <button
            ref={closeRef}
            className="live-dialog-close"
            onClick={onClose}
            aria-label="Close live call"
          >
            <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="live-dialog-body">
          <LiveCallTranscript patientId={patientId} callId={callId} onEnded={handleEnded} />
        </div>

        <footer className="live-dialog-foot">
          {ended ? (
            <button className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
          ) : (
            <span className="live-dialog-hint">Streaming as the call happens. No audio is played.</span>
          )}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
