import type { PatientStatus } from "../types";

const LABELS: Record<PatientStatus, string> = {
  stable: "Stable",
  attention: "Needs attention",
  urgent: "Urgent",
};

export function StatusBadge({ status }: { status: PatientStatus }) {
  return <span className={`badge badge-${status}`}>{LABELS[status]}</span>;
}
