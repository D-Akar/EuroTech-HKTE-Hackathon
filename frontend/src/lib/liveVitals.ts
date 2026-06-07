import type { LiveVitals } from "../types";

// Compact live-wearable payload sent to the backend when a call is placed, so the
// voice agent can speak to the patient's current vitals (connected watch / demo /
// Garmin live), not just stored history. Mirrors backend `LiveVitalsInput`.
export interface LiveVitalsInput {
  heart_rate?: number;
  spo2?: number;
  steps?: number;
  source?: string;
}

/** Build the request payload from the current live snapshot, or undefined if there
 *  is no usable reading (e.g. no watch connected and not in demo). */
export function toLiveVitalsInput(
  live: LiveVitals | null | undefined,
): LiveVitalsInput | undefined {
  if (!live?.heart_rate) return undefined;
  return {
    heart_rate: Math.round(live.heart_rate.value),
    spo2: live.spo2 ? Math.round(live.spo2.value) : undefined,
    steps: live.steps ? Math.round(live.steps.value) : undefined,
    source: live.source,
  };
}
