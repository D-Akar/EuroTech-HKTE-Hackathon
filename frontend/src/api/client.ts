import type { CheckIn, Patient, WearableReading } from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`);
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText} for ${path}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  listPatients: () => getJSON<Patient[]>("/patients"),
  getCheckins: (patientId: number) =>
    getJSON<CheckIn[]>(`/patients/${patientId}/checkins`),
  getWearables: (patientId: number) =>
    getJSON<WearableReading[]>(`/patients/${patientId}/wearables`),
};
