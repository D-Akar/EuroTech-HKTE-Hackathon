import type {
  Alert,
  CallConfig,
  CallRecord,
  CheckIn,
  LiveVitals,
  MedicalProfile,
  Meta,
  Patient,
  ScheduledCall,
  Summary,
  WearableReading,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`);
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText} for ${path}`);
  }
  return resp.json() as Promise<T>;
}

async function sendJSON<T>(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const data = await resp.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  listPatients: () => getJSON<Patient[]>("/patients"),
  getMeta: () => getJSON<Meta>("/meta"),
  getCheckins: (patientId: number) =>
    getJSON<CheckIn[]>(`/patients/${patientId}/checkins`),
  getWearables: (patientId: number) =>
    getJSON<WearableReading[]>(`/patients/${patientId}/wearables`),
  getLive: (patientId: number) =>
    getJSON<LiveVitals>(`/patients/${patientId}/live`),
  getSummary: (patientId: number) =>
    getJSON<Summary>(`/patients/${patientId}/summary`),
  getAlerts: (patientId: number) =>
    getJSON<Alert[]>(`/patients/${patientId}/alerts`),
  // Real FHIR clinical record — only for MongoDB-backed patients (404 otherwise).
  getProfile: (patientId: number) =>
    getJSON<MedicalProfile>(`/patients/${patientId}/profile`),

  // URL of the clinician-ready PDF report (opened/downloaded directly by the browser).
  reportUrl: (patientId: number) =>
    `${BASE_URL}/patients/${patientId}/report.pdf`,

  // --- Calls ---
  triggerCall: (
    patientId: number,
    body: { to_number?: string; questions?: string[] },
  ) => sendJSON<CallRecord>("POST", `/patients/${patientId}/calls/trigger`, body),
  getCallHistory: (patientId: number) =>
    getJSON<CallRecord[]>(`/patients/${patientId}/calls`),
  getCallConfig: (patientId: number) =>
    getJSON<CallConfig>(`/patients/${patientId}/calls/config`),
  saveCallConfig: (
    patientId: number,
    body: { questions: string[]; greeting: string | null },
  ) => sendJSON<CallConfig>("PUT", `/patients/${patientId}/calls/config`, body),
  createSchedule: (
    patientId: number,
    body: { scheduled_at: string; recurring: boolean },
  ) =>
    sendJSON<ScheduledCall>(
      "POST",
      `/patients/${patientId}/calls/schedules`,
      body,
    ),
  listSchedules: (patientId: number) =>
    getJSON<ScheduledCall[]>(`/patients/${patientId}/calls/schedules`),
  cancelSchedule: (patientId: number, scheduleId: number) =>
    sendJSON<ScheduledCall>(
      "DELETE",
      `/patients/${patientId}/calls/schedules/${scheduleId}`,
    ),
};
