import type { PatientStatus } from "../types";
import { STATUS } from "../city";

// Status is always carried by THREE channels at once — color, glyph, and the
// pip's silhouette — so it survives any color-vision deficiency or mono screen.

export function StatusBadge({ status }: { status: PatientStatus }) {
  const meta = STATUS[status];
  return (
    <span className={`badge ${status}`}>
      <span className="badge-glyph" aria-hidden>
        {meta.glyph}
      </span>
      {meta.label}
    </span>
  );
}

/** Compact indicator for dense lists: a status-shaped pip with its glyph. */
export function StatusPip({ status }: { status: PatientStatus }) {
  const meta = STATUS[status];
  return (
    <span className={`status-pip ${status}`} role="img" aria-label={meta.label} title={meta.label}>
      <span aria-hidden>{meta.glyph}</span>
    </span>
  );
}
