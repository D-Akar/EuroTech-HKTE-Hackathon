import type { Alert, AlertSeverity, LiveVitals, PatientStatus } from "../types";

// Mirrors backend app/alerts.py so simulated demo readings escalate exactly the way
// real live readings do. Keep these thresholds in sync with the backend.
export const LIVE_THRESHOLDS = {
  hrUrgent: 85,
  hrElevated: 75,
  hrLow: 50,
  spo2Low: 90,
  spo2Watch: 94,
  stressHigh: 80,
};

const SEVERITY_RANK: Record<AlertSeverity, number> = { info: 1, warning: 2, critical: 3 };
const STATUS_BY_SEVERITY: Record<AlertSeverity, PatientStatus> = {
  info: "stable",
  warning: "attention",
  critical: "urgent",
};

type Vitals = Pick<LiveVitals, "heart_rate" | "spo2" | "stress">;

export function assessLive(
  patientId: number,
  snap: Vitals,
): { status: PatientStatus; alerts: Alert[] } {
  const out: Alert[] = [];
  const add = (
    kind: string,
    severity: AlertSeverity,
    message: string,
    value: number,
    unit: string,
    at: string | null,
  ) => out.push({ patient_id: patientId, kind, severity, message, value, unit, at });

  const hr = snap.heart_rate;
  if (hr) {
    const v = Math.round(hr.value);
    if (v >= LIVE_THRESHOLDS.hrUrgent) {
      add("high_heart_rate", "critical", `Heart rate ${v} bpm is critically high`, v, "bpm", hr.at);
    } else if (v >= LIVE_THRESHOLDS.hrElevated) {
      add("elevated_heart_rate", "warning", `Heart rate ${v} bpm is elevated`, v, "bpm", hr.at);
    } else if (v < LIVE_THRESHOLDS.hrLow) {
      add("bradycardia", "warning", `Heart rate ${v} bpm is below ${LIVE_THRESHOLDS.hrLow}`, v, "bpm", hr.at);
    }
  }

  const spo2 = snap.spo2;
  if (spo2) {
    const v = Math.round(spo2.value);
    if (v < LIVE_THRESHOLDS.spo2Low) {
      add("low_spo2", "critical", `Blood oxygen ${v}% is critically low`, v, "%", spo2.at);
    } else if (v < LIVE_THRESHOLDS.spo2Watch) {
      add("low_spo2", "warning", `Blood oxygen ${v}% is below normal`, v, "%", spo2.at);
    }
  }

  const stress = snap.stress;
  if (stress && stress.value >= LIVE_THRESHOLDS.stressHigh) {
    const v = Math.round(stress.value);
    add("high_stress", "warning", `High stress reading (${v})`, v, "score", stress.at);
  }

  const worst = out.reduce<AlertSeverity | null>(
    (acc, a) => (acc && SEVERITY_RANK[acc] >= SEVERITY_RANK[a.severity] ? acc : a.severity),
    null,
  );
  return { status: worst ? STATUS_BY_SEVERITY[worst] : "stable", alerts: out };
}
