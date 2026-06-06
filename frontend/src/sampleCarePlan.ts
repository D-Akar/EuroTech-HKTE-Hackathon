// A realistic FHIR R4 CarePlan for an elderly outpatient, used by the "Load
// sample plan" affordance in CarePlanPanel. Exercises the full read-path in
// backend/app/fhir_careplan.py: contained Conditions (addresses), contained
// Goals with targets, R4 activity[].detail, period, category and notes — so the
// rendered context handed to the ElevenLabs agent reads like a real plan.
export const SAMPLE_CARE_PLAN = JSON.stringify(
  {
    resourceType: "CarePlan",
    id: "sample-elderly-careplan",
    status: "active",
    intent: "plan",
    title: "Chronic care plan: hypertension, type 2 diabetes, osteoarthritis",
    description:
      "Coordinated outpatient plan for an 82-year-old living at home, focused on " +
      "stable blood pressure and blood sugar, safe mobility, and reliable daily " +
      "medication routines.",
    category: [{ text: "Geriatric chronic disease management" }],
    period: { start: "2026-05-01", end: "2026-11-01" },
    subject: { display: "Elderly outpatient" },
    contained: [
      {
        resourceType: "Condition",
        id: "cond-htn",
        code: { text: "Essential hypertension" },
      },
      {
        resourceType: "Condition",
        id: "cond-dm2",
        code: { text: "Type 2 diabetes mellitus" },
      },
      {
        resourceType: "Condition",
        id: "cond-oa",
        code: { text: "Osteoarthritis of both knees" },
      },
      {
        resourceType: "Goal",
        id: "goal-bp",
        description: { text: "Keep blood pressure in a safe range" },
        target: [
          {
            measure: { text: "Systolic blood pressure" },
            detailQuantity: { value: 135, unit: "mmHg" },
          },
        ],
      },
      {
        resourceType: "Goal",
        id: "goal-glucose",
        description: { text: "Maintain steady blood sugar" },
        target: [
          {
            measure: { text: "Fasting glucose" },
            detailString: "4.0 to 7.0 mmol/L",
          },
        ],
      },
      {
        resourceType: "Goal",
        id: "goal-mobility",
        description: { text: "Stay mobile and prevent falls" },
        target: [{ detailString: "A short daily walk without assistance" }],
      },
    ],
    addresses: [
      { reference: "#cond-htn" },
      { reference: "#cond-dm2" },
      { reference: "#cond-oa" },
    ],
    goal: [
      { reference: "#goal-bp" },
      { reference: "#goal-glucose" },
      { reference: "#goal-mobility" },
    ],
    activity: [
      {
        detail: {
          code: { text: "Take morning blood-pressure and diabetes medication" },
          status: "in-progress",
          scheduledString: "Every morning, with breakfast",
        },
      },
      {
        detail: {
          code: { text: "Check blood pressure at home and write it down" },
          status: "in-progress",
          scheduledString: "Once daily, in the morning",
        },
      },
      {
        detail: {
          code: { text: "Gentle walk or seated chair exercises" },
          status: "in-progress",
          scheduledString: "About 20 minutes, daily",
        },
      },
      {
        detail: {
          code: { text: "Low-salt, diabetic-friendly meals" },
          status: "in-progress",
          scheduledString: "Every meal",
        },
      },
      {
        detail: {
          code: { text: "Weigh in and note any ankle swelling" },
          status: "not-started",
          scheduledString: "Weekly, Sunday morning",
        },
      },
      {
        detail: {
          code: { text: "Knee physiotherapy exercises" },
          status: "in-progress",
          scheduledString: "3 times per week",
        },
      },
    ],
    note: [
      {
        text:
          "Lives alone; daughter visits on weekends. Hard of hearing, so speak " +
          "slowly and confirm the morning medication was actually taken. Watch for " +
          "dizziness when standing up.",
      },
    ],
  },
  null,
  2,
);
