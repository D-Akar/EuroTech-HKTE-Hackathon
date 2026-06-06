// Mirrors backend Pydantic models in backend/app/models.py

export type PatientStatus = "stable" | "attention" | "urgent";

export interface Patient {
  id: number;
  name: string;
  age: number;
  status: PatientStatus;
  practice: string;
  district: string;
  phone_number: string;
  fhir_id: string | null; // set when backed by a real MongoDB FHIR record
}

// --- Real FHIR medical profile (MongoDB-backed patients) ---

export interface Condition {
  name: string;
  onset_date: string | null;
}

export interface Medication {
  name: string;
  frequency: string | null;
  prescribed_date: string | null;
}

export interface Allergy {
  substance: string;
  type: string | null;
  criticality: string | null;
}

export interface MedicalProfile {
  patient_id: number;
  fhir_id: string;
  gender: string | null;
  birth_date: string | null;
  preferred_language: string | null;
  chronic_conditions: Condition[];
  allergies: Allergy[];
  active_medications: Medication[];
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

// --- Live vitals, trends, and alerts (the featured Garmin-backed patient) ----

export type LiveSource = "live" | "ble" | "export-fallback" | "demo" | "none";

export interface LiveMetric {
  value: number;
  unit: string | null;
  at: string | null; // ISO datetime of the reading
}

export type AlertSeverity = "info" | "warning" | "critical";

export interface Alert {
  patient_id: number;
  kind: string;
  severity: AlertSeverity;
  message: string;
  value: number;
  unit: string;
  at: string | null;
}

export interface LiveVitals {
  source: LiveSource;
  heart_rate: LiveMetric | null;
  stress: LiveMetric | null;
  spo2: LiveMetric | null;
  steps: LiveMetric | null;
  status: PatientStatus | "none";
  alerts: Alert[];
}

export interface StatBlock {
  min: number;
  max: number;
  avg: number;
  n: number;
  low_events?: number;
  high_events?: number;
}

export interface Summary {
  days: number;
  heart_rate: StatBlock | null;
  sleep_hours: StatBlock | null;
  steps: StatBlock | null;
  spo2?: StatBlock;
  stress?: StatBlock;
}

export interface Meta {
  featured_patient_id: number;
  live_data: boolean;
}

export interface CarePlanGoal {
  description: string;
  target: string | null;
}

export interface CarePlanActivity {
  description: string;
  status: string | null;
  scheduled: string | null;
}

export interface CarePlanContext {
  title: string | null;
  status: string | null;
  intent: string | null;
  description: string | null;
  categories: string[];
  subject_display: string | null;
  period_start: string | null;
  period_end: string | null;
  addresses: string[];
  goals: CarePlanGoal[];
  activities: CarePlanActivity[];
  notes: string[];
  rendered_text: string;
}
