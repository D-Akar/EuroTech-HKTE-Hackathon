import { useMemo, useState } from "react";
import type { Patient, PatientStatus } from "../types";
import { STATUS, STATUS_ORDER } from "../city";
import { StatusPip } from "./StatusBadge";

interface Props {
  patients: Patient[];
  selectedId: number | null;
  featuredId: number | null;
  statusFilter: Set<string> | null;
  onSelect: (id: number) => void;
}

export function PatientList({ patients, selectedId, featuredId, statusFilter, onSelect }: Props) {
  const [query, setQuery] = useState("");

  // Filter by the active watch-chip status and the search box, then group by
  // status so anyone needing care rises to the top of the rail.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = patients.filter((p) => {
      if (statusFilter && !statusFilter.has(p.status)) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        p.district.toLowerCase().includes(q) ||
        p.practice.toLowerCase().includes(q)
      );
    });
    return STATUS_ORDER.map((status) => ({
      status,
      patients: matched
        .filter((p) => p.status === status)
        .sort((a, b) => a.name.localeCompare(b.name)),
    })).filter((g) => g.patients.length > 0);
  }, [patients, statusFilter, query]);

  const total = groups.reduce((n, g) => n + g.patients.length, 0);

  return (
    <div className="roster">
      <div className="roster-head">
        <div className="roster-title">
          <h2>Roster</h2>
          <span className="roster-count num">
            {total} of {patients.length}
          </span>
        </div>
        <div className="search">
          <Search />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name or district"
            aria-label="Search patients"
          />
        </div>
      </div>

      <ul className="roster-list">
        {total === 0 && (
          <li className="muted" style={{ padding: "20px 12px", fontSize: 14 }}>
            No patients match.
          </li>
        )}
        {groups.map((g) => (
          <li key={g.status}>
            <div className="roster-section">
              {STATUS[g.status as PatientStatus].label} · {g.patients.length}
            </div>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {g.patients.map((p) => (
                <li
                  key={p.id}
                  className={`patient-row ${p.id === selectedId ? "selected" : ""}`}
                  onClick={() => onSelect(p.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(p.id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={p.id === selectedId}
                >
                  <StatusPip status={p.status} />
                  <div className="patient-row-body">
                    <div className="patient-name">
                      {p.name}
                      {p.id === featuredId && <span className="you-tag">You</span>}
                    </div>
                    <div className="patient-row-sub">
                      {p.district} · Age {p.age}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Search() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="m20 20-3.2-3.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
