import type { Patient } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  patients: Patient[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function PatientList({ patients, selectedId, onSelect }: Props) {
  return (
    <ul className="patient-list">
      {patients.map((p) => (
        <li
          key={p.id}
          className={`patient-row ${p.id === selectedId ? "selected" : ""}`}
          onClick={() => onSelect(p.id)}
        >
          <div className="patient-row-main">
            <span className="patient-name">{p.name}</span>
            <StatusBadge status={p.status} />
          </div>
          <div className="patient-row-sub">
            Age {p.age} · {p.practice}
          </div>
        </li>
      ))}
    </ul>
  );
}
