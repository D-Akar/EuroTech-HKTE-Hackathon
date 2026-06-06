import { useEffect, useState } from "react";
import { api } from "./api/client";
import { PatientDetail } from "./components/PatientDetail";
import { PatientList } from "./components/PatientList";
import type { Patient } from "./types";

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listPatients()
      .then((p) => {
        setPatients(p);
        if (p.length > 0) setSelectedId(p[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const selected = patients.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Elderly Care Dashboard</h1>
        <span className="muted">Practice overview · {patients.length} patients</span>
      </header>

      {error && (
        <p className="error">
          Could not reach the API ({error}). Is the backend running on :8000?
        </p>
      )}

      <div className="layout">
        <aside className="sidebar">
          <PatientList
            patients={patients}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </aside>
        <main className="content">
          {selected ? (
            <PatientDetail patient={selected} />
          ) : (
            <p className="muted">Select a patient to view their health timeline.</p>
          )}
        </main>
      </div>
    </div>
  );
}
