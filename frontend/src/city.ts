// The stylized Hong Kong "digital twin" geometry, plus the colorblind-safe status
// system. The backend gives each patient a district; we map that district onto a
// position in the 3D scene and scatter patients deterministically within it so the
// city looks the same every load.
//
// Coordinate convention (Three.js): X right, Z toward the viewer, Y up.
// Kowloon sits to the north (negative Z), Victoria Harbour runs across the middle,
// Hong Kong Island's dense north shore sits just south of it, and the hills (The
// Peak) and southern districts rise further south (positive Z).

import type { Patient, PatientStatus } from "./types";

export interface District {
  name: string;
  x: number;
  z: number;
  /** Ground height: the southern hills sit higher than the reclaimed waterfront. */
  y: number;
  /** Rough tower height multiplier — the dense cores spike, the suburbs stay low. */
  density: number;
  side: "kowloon" | "island" | "hills";
}

export const DISTRICTS: Record<string, District> = {
  // --- Kowloon (north of the harbour) ---
  "Sham Shui Po": { name: "Sham Shui Po", x: -6.5, z: -8.2, y: 0, density: 0.8, side: "kowloon" },
  "Mong Kok": { name: "Mong Kok", x: -2.2, z: -8.6, y: 0, density: 1.0, side: "kowloon" },
  "Yau Ma Tei": { name: "Yau Ma Tei", x: -3.6, z: -6.8, y: 0, density: 0.85, side: "kowloon" },
  "Kowloon City": { name: "Kowloon City", x: 3.2, z: -8.0, y: 0, density: 0.7, side: "kowloon" },
  "Tsim Sha Tsui": { name: "Tsim Sha Tsui", x: 0.2, z: -5.2, y: 0, density: 0.95, side: "kowloon" },
  // --- Hong Kong Island, north shore (just south of the harbour) ---
  "Sheung Wan": { name: "Sheung Wan", x: -6.4, z: 0.8, y: 0, density: 0.8, side: "island" },
  "Central": { name: "Central", x: -3.0, z: 0.4, y: 0, density: 1.0, side: "island" },
  "Wan Chai": { name: "Wan Chai", x: 0.4, z: 0.9, y: 0, density: 0.95, side: "island" },
  "Causeway Bay": { name: "Causeway Bay", x: 3.4, z: 1.2, y: 0, density: 0.9, side: "island" },
  "North Point": { name: "North Point", x: 6.4, z: 1.6, y: 0, density: 0.75, side: "island" },
  "Quarry Bay": { name: "Quarry Bay", x: 8.8, z: 2.2, y: 0, density: 0.7, side: "island" },
  // --- The hills and southern side ---
  "The Peak": { name: "The Peak", x: -2.4, z: 5.2, y: 1.9, density: 0.3, side: "hills" },
  "Aberdeen": { name: "Aberdeen", x: -4.6, z: 7.4, y: 0.5, density: 0.5, side: "hills" },
  "Stanley": { name: "Stanley", x: 5.4, z: 8.2, y: 0.4, density: 0.4, side: "hills" },
};

/** Fallback so an unknown district still lands somewhere sensible. */
const DEFAULT_DISTRICT: District = DISTRICTS["Central"];

export function districtFor(patient: Patient): District {
  return DISTRICTS[patient.district] ?? DEFAULT_DISTRICT;
}

/** Tiny deterministic PRNG so a given patient always lands in the same spot. */
function seeded(n: number): () => number {
  let s = (n * 2654435761) % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export interface PlacedPatient {
  patient: Patient;
  x: number;
  y: number;
  z: number;
}

/** Scatter a patient within their district with a stable jitter. */
export function placePatient(patient: Patient): PlacedPatient {
  const d = districtFor(patient);
  const rng = seeded(patient.id);
  const spread = 1.5;
  const angle = rng() * Math.PI * 2;
  const radius = Math.sqrt(rng()) * spread;
  return {
    patient,
    x: d.x + Math.cos(angle) * radius,
    y: d.y,
    z: d.z + Math.sin(angle) * radius,
  };
}

// --- Status system (colorblind-safe: hue + glyph + label + marker shape) ------

export interface StatusMeta {
  key: PatientStatus;
  label: string;
  short: string;
  /** Hex for Three.js materials. CSS uses the matching --status-* tokens. */
  color: string;
  glyph: string;
  /** Marker silhouette so status survives any color-vision deficiency. */
  shape: "dot" | "ring" | "beacon";
  /** Triage weight; higher sorts to the top of the roster. */
  severity: number;
}

export const STATUS: Record<PatientStatus, StatusMeta> = {
  stable: {
    key: "stable",
    label: "Stable",
    short: "Stable",
    color: "#1bb39a",
    glyph: "✓",
    shape: "dot",
    severity: 0,
  },
  attention: {
    key: "attention",
    label: "Needs attention",
    short: "Attention",
    color: "#e0a020",
    glyph: "!",
    shape: "ring",
    severity: 1,
  },
  urgent: {
    key: "urgent",
    label: "Urgent",
    short: "Urgent",
    color: "#e8503a",
    glyph: "✚",
    shape: "beacon",
    severity: 2,
  },
};

export const STATUS_ORDER: PatientStatus[] = ["urgent", "attention", "stable"];
