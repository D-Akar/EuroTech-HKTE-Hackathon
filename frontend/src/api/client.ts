import type {
  Alert,
  CallConfig,
  CallRecord,
  CarePlanContext,
  CheckIn,
  ConversationDetail,
  EscalationRecord,
  LiveVitals,
  MedicalProfile,
  Meta,
  Patient,
  PatientQuestions,
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

async function sendText<T>(path: string, text: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: text,
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

  // LLM-generated, tailored check-in questions for the voice agent.
  getQuestions: (patientId: number) =>
    getJSON<PatientQuestions>(`/patients/${patientId}/questions`),
  // Re-run question generation for one patient (calls the LLM; can take a few seconds).
  regenerateQuestions: (patientId: number) =>
    sendJSON<PatientQuestions>(
      "POST",
      `/patients/${patientId}/questions/regenerate`,
    ),

  // Persist the patient's check-in phone number; returns the updated patient.
  updatePatientPhone: (patientId: number, phone_number: string) =>
    sendJSON<Patient>("PUT", `/patients/${patientId}/phone`, { phone_number }),

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
    body: { questions: string[]; greeting: string | null; system_prompt: string | null },
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
  getCallConversation: (patientId: number, callId: number) =>
    getJSON<ConversationDetail>(
      `/patients/${patientId}/calls/${callId}/conversation`,
    ),
  listSchedules: (patientId: number) =>
    getJSON<ScheduledCall[]>(`/patients/${patientId}/calls/schedules`),
  cancelSchedule: (patientId: number, scheduleId: number) =>
    sendJSON<ScheduledCall>(
      "DELETE",
      `/patients/${patientId}/calls/schedules/${scheduleId}`,
    ),

  // --- Real-time escalation ---
  escalate: (
    patientId: number,
    body: {
      reason: string;
      source?: string;
      notify_nurse?: boolean;
      nurse_number?: string;
    },
  ) =>
    sendJSON<EscalationRecord>("POST", `/patients/${patientId}/escalate`, body),

  // Server-Sent Events stream — open with `new EventSource(api.eventsUrl())`.
  eventsUrl: () => `${BASE_URL}/events`,

  // --- Care plans ---
  uploadCarePlan: (patientId: number, document: string) =>
    sendText<CarePlanContext>(`/patients/${patientId}/care-plan`, document),
  getCarePlan: (patientId: number) =>
    getJSON<CarePlanContext>(`/patients/${patientId}/care-plan`),
  deleteCarePlan: (patientId: number) =>
    fetch(`${BASE_URL}/patients/${patientId}/care-plan`, { method: "DELETE" }).then(
      (r) => {
        if (!r.ok && r.status !== 404) throw new Error(`${r.status} ${r.statusText}`);
      },
    ),
};
