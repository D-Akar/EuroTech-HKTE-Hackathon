// Mirrors backend Pydantic models in backend/app/models.py

export type PatientStatus = "stable" | "attention" | "urgent";

export interface Patient {
  id: number;
  name: string;
  age: number;
  status: PatientStatus;
  practice: string;
  phone_number: string;
}

export interface CheckIn {
  id: number;
  patient_id: number;
  date: string; // ISO date
  mood: string;
  pain_level: number;
  answered: boolean;
  notes: string;
}

export interface WearableReading {
  id: number;
  patient_id: number;
  timestamp: string; // ISO datetime
  heart_rate: number;
  steps: number;
  sleep_hours: number;
}

// --- Outbound check-in calls ---

export interface CallConfig {
  patient_id: number;
  questions: string[];
  greeting: string | null;
}

export interface ScheduledCall {
  id: number;
  patient_id: number;
  scheduled_at: string; // ISO datetime
  recurring: boolean;
  status: "pending" | "cancelled";
  questions: string[];
}

export interface CallRecord {
  id: number;
  patient_id: number;
  triggered_at: string; // ISO datetime
  kind: "instant" | "scheduled";
  to_number: string;
  status: "initiated" | "failed";
  conversation_id: string | null;
  call_sid: string | null;
  error: string | null;
}
