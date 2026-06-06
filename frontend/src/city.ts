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
  /** How many towers spawn here - Mong Kok packs the most, suburbs the fewest. */
  density: number;
  /**
   * Tower height multiplier, separate from count. This is what gives the skyline
   * its HK silhouette: Central spikes (IFC), the dense Kowloon residential cores
   * stay mid-rise, and Kowloon City stays low (old Kai Tak flight-path limit).
   */
  height: number;
  side: "kowloon" | "island" | "hills";
}

// (name, nx, ny, elevation, density, height, side) - placed to match the real map.
// density = how many towers; height = how tall. Tuned for a realistic HK profile.
const _D: [string, number, number, number, number, number, District["side"]][] = [
  // Kowloon (top mass) - clustered toward the centre of the peninsula.
  // Packed with buildings but mostly mid-rise residential, except TST.
  // Northern (New Kowloon) belt across the top edge - dense public housing.
  ["Cheung Sha Wan", 0.13, 0.22, 0, 0.85, 0.6, "kowloon"], // NW, dense residential/industrial
  ["Wong Tai Sin", 0.46, 0.15, 0, 0.85, 0.6, "kowloon"], // north-central public housing
  ["Diamond Hill", 0.58, 0.14, 0, 0.8, 0.65, "kowloon"], // NE, dense mid-rise
  ["Sham Shui Po", 0.20, 0.3, 0, 0.9, 0.55, "kowloon"], // old, very dense, low-mid
  ["Mong Kok", 0.34, 0.28, 0, 1.0, 0.7, "kowloon"], // densest count, medium height
  ["Yau Ma Tei", 0.36, 0.38, 0, 0.85, 0.6, "kowloon"],
  ["Tsim Sha Tsui", 0.41, 0.45, 0, 0.95, 1.0, "kowloon"], // waterfront, tall
  ["West Kowloon", 0.29, 0.41, 0, 0.65, 1.4, "kowloon"], // ICC - tallest tower in HK
  ["Hung Hom", 0.5, 0.4, 0, 0.8, 0.72, "kowloon"], // harbour-front, east of TST
  ["Kowloon City", 0.5, 0.25, 0, 0.7, 0.4, "kowloon"], // old airport: height-restricted, low
  // Hong Kong Island, north shore (bottom mass, along the harbour). The financial
  // core: fewer, far taller towers in Central, dense and tall eastward.
  ["Kennedy Town", 0.1, 0.67, 0, 0.75, 0.7, "island"], // far-west shore, mid-rise residential
  ["Sheung Wan", 0.2, 0.66, 0, 0.8, 0.75, "island"],
  ["Central", 0.3, 0.66, 0, 1.0, 1.35, "island"], // the supertall core (IFC)
  ["Admiralty", 0.36, 0.665, 0, 0.85, 1.1, "island"], // Pacific Place / govt HQ, tall
  ["Wan Chai", 0.42, 0.68, 0, 0.95, 1.05, "island"], // Central Plaza, tall
  ["Causeway Bay", 0.52, 0.7, 0, 0.95, 0.9, "island"],
  ["North Point", 0.66, 0.605, 0, 0.8, 0.8, "island"], // dense residential, tall
  ["Quarry Bay", 0.80, 0.565, 0, 0.85, 0.85, "island"], // "Monster Building" density

  // The hills and southern side of the island. Elevation stays 0 so markers rest
  // on the map floor, not floating where the old large hills used to be.
  ["The Peak", 0.31, 0.74, 0, 0.3, 0.3, "hills"],
  ["Aberdeen", 0.24, 0.86, 0, 0.5, 0.5, "hills"],
  ["Stanley", 0.7, 0.88, 0, 0.4, 0.4, "hills"],
];

export const DISTRICTS: Record<string, District> = Object.fromEntries(
  _D.map(([name, nx, ny, y, density, height, side]) => {
    const { x, z } = toWorld(nx, ny);
    return [name, { name, x, z, y, density, height, side }];
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

// --- Real-world geography (for the Google Photorealistic 3D Tiles map) --------
// Real WGS84 coordinates for each district, so a patient's marker lands on the
// actual building when we render the photoreal globe. The center anchors the
// ReorientationPlugin (Victoria Harbour, between Kowloon and the Island).

export const HK_CENTER = { lat: 22.295, lon: 114.169 };

export const DISTRICT_LATLON: Record<string, { lat: number; lon: number }> = {
  // Kowloon (north of the harbour)
  "Cheung Sha Wan": { lat: 22.337, lon: 114.1555 },
  "Wong Tai Sin": { lat: 22.3415, lon: 114.1935 },
  "Diamond Hill": { lat: 22.34, lon: 114.2015 },
  "Sham Shui Po": { lat: 22.3303, lon: 114.162 },
  "Mong Kok": { lat: 22.319, lon: 114.169 },
  "Yau Ma Tei": { lat: 22.313, lon: 114.1705 },
  "Tsim Sha Tsui": { lat: 22.2975, lon: 114.1722 },
  "West Kowloon": { lat: 22.304, lon: 114.1605 },
  "Hung Hom": { lat: 22.303, lon: 114.182 },
  "Kowloon City": { lat: 22.328, lon: 114.19 },
  // Hong Kong Island, north shore
  "Kennedy Town": { lat: 22.281, lon: 114.1285 },
  "Sheung Wan": { lat: 22.287, lon: 114.15 },
  Central: { lat: 22.282, lon: 114.158 },
  Admiralty: { lat: 22.279, lon: 114.165 },
  "Wan Chai": { lat: 22.28, lon: 114.173 },
  "Causeway Bay": { lat: 22.28, lon: 114.185 },
  "North Point": { lat: 22.291, lon: 114.2 },
  "Quarry Bay": { lat: 22.287, lon: 114.213 },
  // Hills / south side
  "The Peak": { lat: 22.271, lon: 114.149 },
  Aberdeen: { lat: 22.248, lon: 114.155 },
  Stanley: { lat: 22.219, lon: 114.212 },
};

/** A patient's real lat/lon: their district centre plus a stable jitter (~600 m). */
export function patientLatLon(patient: Patient): { lat: number; lon: number } {
  const base = DISTRICT_LATLON[patient.district] ?? HK_CENTER;
  const rng = seeded(patient.id + 1000);
  const angle = rng() * Math.PI * 2;
  const radius = Math.sqrt(rng()) * 0.0055; // degrees (~610 m)
  const dLat = Math.sin(angle) * radius;
  const dLon = (Math.cos(angle) * radius) / Math.cos((base.lat * Math.PI) / 180);
  return { lat: base.lat + dLat, lon: base.lon + dLon };
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
