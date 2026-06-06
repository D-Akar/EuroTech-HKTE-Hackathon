# Product

## Register

product

## Users

**Primary (operational):** Care coordinators and practice staff at outpatient
elderly-care practices. They watch over a large roster of elderly outpatients at once,
all day, and need to know at a glance who is fine, who needs a look, and who needs
someone dispatched *now*. Their job is triage and deployment: turn a flood of check-in
answers and wearable signals into the next action for the right patient.

**Secondary (demo):** Hackathon judges and prospective partners seeing this for the
first time in a short live demo. They must immediately grasp the product's ambition,
the "city-scale care command center" narrative, and feel that this is what the future
of elderly care coordination looks like.

The design is **demo-first but must read as a believable real operational tool** the
moment anyone looks past the wow factor.

## Product Purpose

A two-way platform connecting outpatient elderly-care practices with their patients.
Patients get daily AI voice check-in calls (ElevenLabs + Twilio) and wear health
trackers; the platform fuses both streams into a live, city-scale overview of every
patient's wellbeing. The signature surface is a **digital twin of the city (Hong Kong)**:
a stylized 3D cityscape where patients live as points of light, status ripples across the
map in real time, and emergencies surface as markers a coordinator can dispatch care
toward. Success = a coordinator opens it and instantly knows where attention is needed,
and a first-time viewer instantly understands the whole product.

## Brand Personality

Futuristic, alive, reassuring. Three words: **luminous, vigilant, calm**. The voice is
competent and quiet, never alarmist. The interface feels like a living system keeping
watch over real people, so its confidence comes from precision and responsiveness, not
from shouting. Calm is the resting state; intensity is reserved for the moment a real
person genuinely needs help, and then it is unmistakable.

## Anti-references

- **Generic SaaS dashboard**: identical card grids, hero-metric tiles, KPI boxes with a
  gradient accent. This is a living map, not a metrics report.
- **Alarming "all-red medical" UI**: blood-red everywhere, crisis-by-default. We are
  watching grandparents; the default state must feel safe, not like an ER monitor.
- **Sterile EHR / hospital software**: gray forms, dense clinical tables, cognitive
  overload. Trust here comes from clarity and life, not institutional grayness.
- **Cliché sci-fi neon-on-black "crypto/gamer" look**: pure black backgrounds, garish
  full-saturation neon, HUD clutter for decoration. Futuristic must stay humane and
  legible, not a video-game overlay.

## Design Principles

1. **The city is alive, the patients are people.** The twin breathes and responds, but
   every point of light is a named human being one click from full context. Never let the
   spectacle abstract the patient away.
2. **Calm until it counts.** Stable is the quiet default; the UI spends its visual energy
   only where a real need exists. Emergencies earn motion, brightness, and focus; nothing
   else competes for them.
3. **Glance, then drill.** The twin answers "where do I look?" in one second; the
   list/timeline answers "what exactly is happening, and what do I do?" Both must be
   first-class, with a fluid path from the map to one patient's full story.
4. **Earn the future.** Depth, light, and motion must mean something (status, recency,
   urgency, location), never decorate. If an effect doesn't encode information, cut it.
5. **Trust through precision.** Reassurance is delivered by accuracy and responsiveness,
   not soft pastels. The system feels safe because it is clearly, competently watching.

## Accessibility & Inclusion

- **WCAG AA contrast** for all text and status indicators, including over the 3D canvas
  (status markers and labels must stay legible against a busy/animated background).
- **Colorblind-safe status**: stable / attention / urgent must never rely on color alone.
  Pair every status with shape, icon, label, and/or motion so it survives any color-vision
  deficiency and any monochrome screen.
- Honor `prefers-reduced-motion`: the "living" map and emergency animations need a calm,
  static-but-still-legible fallback (good practice even though not explicitly required).
- The 3D twin must never be the *only* way to reach information; the list and timeline
  provide a complete, non-spatial path to every patient and action.
