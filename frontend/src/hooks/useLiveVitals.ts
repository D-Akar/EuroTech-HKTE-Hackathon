import { useEffect, useState } from "react";
import { api } from "../api/client";
import { assessLive } from "../lib/liveAssessment";
import type { LiveVitals } from "../types";

const POLL_MS = 8_000; // Server caches each live fetch (~10s), so this stays close without hammering Garmin.
const DEMO_TICK_MS = 1_500;
const DEMO_RAMP_SECONDS = 45; // resting -> exertion peak; ~24s to elevated, ~30s to urgent

// A deterministic "running around" ramp: heart rate and steps climb, blood oxygen
// dips, stress rises. Used only in demo mode so the escalation story plays on cue
// when a live watch sync would be too slow for a stage demo.
function demoSnapshot(elapsedSeconds: number): LiveVitals {
  const p = Math.min(1, elapsedSeconds / DEMO_RAMP_SECONDS);
  const ease = p * p * (3 - 2 * p); // smoothstep
  const at = new Date().toISOString();
  const base = {
    source: "demo" as const,
    heart_rate: { value: Math.round(48 + ease * (146 - 48)), unit: "/min", at },
    steps: { value: Math.round(2400 + elapsedSeconds * 34), unit: "steps", at },
    spo2: { value: Math.round(98 - ease * 6), unit: "%", at },
    stress: { value: Math.round(18 + ease * 72), unit: "score", at },
  };
  return { ...base, ...assessLive(0, base) };
}

// A held, operator-set heart rate for demos where the scripted ramp is too slow or
// you want to land on an exact value on cue (e.g. 85 bpm to trip the urgent line and
// fire the emergency call). The caller jitters the HR and advances the step count
// between ticks; SpO2/stress shift mildly with HR so the tile stays coherent, but the
// heart rate is what drives the assessment + escalation.
function manualSnapshot(hr: number, steps: number): LiveVitals {
  const at = new Date().toISOString();
  const t = Math.max(0, Math.min(1, (hr - 50) / 100)); // 50 bpm -> 0, 150 bpm -> 1
  const base = {
    source: "demo" as const,
    heart_rate: { value: hr, unit: "/min", at },
    steps: { value: steps, unit: "steps", at },
    spo2: { value: Math.round(98 - t * 5), unit: "%", at },
    stress: { value: Math.round(18 + t * 60), unit: "score", at },
  };
  return { ...base, ...assessLive(0, base) };
}

interface LiveState {
  data: LiveVitals | null;
  loading: boolean;
  error: string | null;
}

export function useLiveVitals(
  patientId: number | null,
  demo: boolean,
  manualHr: number | null = null,
): LiveState {
  const [state, setState] = useState<LiveState>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (patientId == null) {
      setState({ data: null, loading: false, error: null });
      return;
    }

    if (demo) {
      // Operator pinned an exact heart rate -> hold it (re-emitting so the timestamp
      // stays fresh) instead of running the auto-ramp.
      if (manualHr != null) {
        // Hold the pinned heart rate with a small lifelike jitter (-3..+5 bpm) and
        // let the step count climb steadily (~+1 per tick, sometimes +2) so the tile
        // reads like a live, moving patient instead of a frozen number.
        let steps = 2400;
        const emit = () => {
          steps += Math.random() < 0.75 ? 1 : 2;
          const jitter = Math.round(-3 + Math.random() * 8); // -3..+5 bpm
          setState({
            data: manualSnapshot(manualHr + jitter, steps),
            loading: false,
            error: null,
          });
        };
        emit();
        const timer = window.setInterval(emit, DEMO_TICK_MS);
        return () => window.clearInterval(timer);
      }
      const start = Date.now();
      setState({ data: demoSnapshot(0), loading: false, error: null });
      const timer = window.setInterval(() => {
        setState({ data: demoSnapshot((Date.now() - start) / 1000), loading: false, error: null });
      }, DEMO_TICK_MS);
      return () => window.clearInterval(timer);
    }

    let cancelled = false;
    const tick = () => {
      api
        .getLive(patientId)
        .then((data) => {
          if (!cancelled) setState({ data, loading: false, error: null });
        })
        .catch((e) => {
          if (!cancelled) setState((s) => ({ ...s, loading: false, error: String(e) }));
        });
    };
    setState((s) => ({ ...s, loading: true }));
    tick();
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [patientId, demo, manualHr]);

  return state;
}
