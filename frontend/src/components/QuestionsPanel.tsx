import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { GeneratedQuestion, PatientQuestions } from "../types";

// "Questions to ask" — the LLM-generated, patient-tailored questions the voice
// agent should raise on the next check-in call. Generated offline from the
// patient's recent check-ins, their chronic conditions, and the worsening-symptom
// guide; can be regenerated on demand with the button.

const CATEGORY_LABEL: Record<string, string> = {
  symptom_followup: "Follow-up",
  proactive_monitoring: "Monitoring",
  wellbeing: "Wellbeing",
  adherence: "Adherence",
};

export function QuestionsPanel({ patientId }: { patientId: number }) {
  const [data, setData] = useState<PatientQuestions | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getQuestions(patientId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  async function handleRegenerate() {
    setRegenerating(true);
    setError(null);
    try {
      const fresh = await api.regenerateQuestions(patientId);
      setData(fresh);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setRegenerating(false);
    }
  }

  const questions = data?.questions ?? [];

  return (
    <section className="qpanel">
      <div className="qpanel-head">
        <div className="section-label" style={{ margin: 0 }}>
          Questions to ask
        </div>
        <button
          className="btn btn-ghost qpanel-regen"
          onClick={handleRegenerate}
          disabled={regenerating || loading}
        >
          <RefreshGlyph spinning={regenerating} />
          {regenerating ? "Generating…" : "Regenerate"}
        </button>
      </div>

      {error && <p className="call-error">{error}</p>}

      {loading ? (
        <div className="qpanel-list">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton" style={{ height: 54, borderRadius: 10 }} />
          ))}
        </div>
      ) : regenerating ? (
        <p className="muted qpanel-empty">
          Cross-referencing recent check-ins with chronic-condition warning signs…
        </p>
      ) : questions.length === 0 ? (
        <p className="muted qpanel-empty">
          No tailored questions yet. Click <strong>Regenerate</strong> to build them
          from this patient's check-ins, conditions, and worsening-symptom guide.
        </p>
      ) : (
        <ol className="qpanel-list">
          {questions.map((q, i) => (
            <QuestionItem key={i} index={i + 1} q={q} />
          ))}
        </ol>
      )}
    </section>
  );
}

function QuestionItem({ index, q }: { index: number; q: GeneratedQuestion }) {
  const catLabel = q.category ? (CATEGORY_LABEL[q.category] ?? q.category) : null;
  const target = [q.related_condition, q.related_symptom].filter(Boolean).join(" · ");
  return (
    <li className="qpanel-item">
      <span className="qpanel-num num">{index}</span>
      <div className="qpanel-body">
        <p className="qpanel-text">{q.text}</p>
        <div className="qpanel-meta">
          {catLabel && (
            <span className={`qpanel-cat cat-${q.category ?? "other"}`}>{catLabel}</span>
          )}
          {target && <span className="qpanel-target">{target}</span>}
        </div>
      </div>
    </li>
  );
}

function RefreshGlyph({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={spinning ? "spin" : undefined}
    >
      <path
        d="M20 11a8 8 0 1 0-.5 4M20 5v6h-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
