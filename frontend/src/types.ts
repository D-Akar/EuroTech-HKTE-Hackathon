// Mirrors backend Pydantic models in backend/app/models.py

export type PatientStatus = "stable" | "attention" | "urgent";

export interface Patient {
  id: number;
  name: string;
  age: number;
  status: PatientStatus;
  practice: string;
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
