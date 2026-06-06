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

interface LiveState {
  data: LiveVitals | null;
  loading: boolean;
  error: string | null;
}

export function useLiveVitals(patientId: number | null, demo: boolean): LiveState {
  const [state, setState] = useState<LiveState>({ data: null, loading: false, error: null });

  useEffect(() => {
    if (patientId == null) {
      setState({ data: null, loading: false, error: null });
      return;
    }

    if (demo) {
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
  }, [patientId, demo]);

  return state;
}
