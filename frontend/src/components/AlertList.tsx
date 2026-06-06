import type { Alert, AlertSeverity } from "../types";

// Severity rides on shape + label, not color alone, matching the colorblind-safe
// status system elsewhere in the app.
const SEVERITY: Record<AlertSeverity, { cls: string; label: string }> = {
  critical: { cls: "urgent", label: "Critical" },
  warning: { cls: "attention", label: "Warning" },
  info: { cls: "info", label: "Info" },
};

const fmtTime = (at: string | null): string => {
  if (!at) return "";
  const d = new Date(at);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

export function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) {
    return <p className="muted" style={{ fontSize: 13.5, margin: 0 }}>No threshold alerts in range.</p>;
  }

  return (
    <ul className="alert-list">
      {alerts.map((a, i) => {
        const sev = SEVERITY[a.severity];
        const when = fmtTime(a.at);
        return (
          <li key={`${a.kind}-${i}`} className={`alert-item ${sev.cls}`}>
            <span className={`alert-pip ${sev.cls}`} aria-hidden />
            <div className="alert-body">
              <div className="alert-msg">{a.message}</div>
              <div className="alert-meta num">
                {sev.label}
                {when && ` · ${when}`}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
