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

// The twin is laid out on a fixed rectangular tile. Everything (coastlines,
// districts, patient markers) is authored in normalized map coordinates
// (nx, ny) with the origin at the top-left, nx→east, ny→south, matching how you
// read the printed Hong Kong map. `toWorld` converts to Three.js world space
// (X→east, Z→south, Kowloon north / island south).
export const MAP = { w: 25, d: 18.75 }; // 4:3 rectangle, like the map print

export function toWorld(nx: number, ny: number): { x: number; z: number } {
  return { x: (nx - 0.5) * MAP.w, z: (ny - 0.5) * MAP.d };
}

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

// (name, nx, ny, elevation, density, side) — placed to match the real map.
const _D: [string, number, number, number, number, District["side"]][] = [
  // Kowloon (top mass) — clustered toward the centre of the peninsula
  ["Sham Shui Po", 0.28, 0.2, 0, 0.8, "kowloon"],
  ["Mong Kok", 0.36, 0.28, 0, 1.0, "kowloon"],
  ["Yau Ma Tei", 0.36, 0.38, 0, 0.85, "kowloon"],
  ["Tsim Sha Tsui", 0.41, 0.45, 0, 0.95, "kowloon"],
  ["Kowloon City", 0.5, 0.25, 0, 0.7, "kowloon"],
  // Hong Kong Island, north shore (bottom mass, along the harbour)
  ["Sheung Wan", 0.2, 0.63, 0, 0.8, "island"],
  ["Central", 0.3, 0.645, 0, 1.0, "island"],
  ["Wan Chai", 0.42, 0.645, 0, 0.95, "island"],
  ["Causeway Bay", 0.52, 0.645, 0, 0.9, "island"],
  ["North Point", 0.66, 0.605, 0, 0.75, "island"],
  ["Quarry Bay", 0.78, 0.565, 0, 0.7, "island"],
  // The hills and southern side of the island. Elevation stays 0 so markers rest
  // on the map floor, not floating where the old large hills used to be.
  ["The Peak", 0.31, 0.74, 0, 0.3, "hills"],
  ["Aberdeen", 0.24, 0.86, 0, 0.5, "hills"],
  ["Stanley", 0.7, 0.88, 0, 0.4, "hills"],
];

export const DISTRICTS: Record<string, District> = Object.fromEntries(
  _D.map(([name, nx, ny, y, density, side]) => {
    const { x, z } = toWorld(nx, ny);
    return [name, { name, x, z, y, density, side }];
  }),
);

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
