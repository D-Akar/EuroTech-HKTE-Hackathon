# Opening / consent question (spoken first on every check-in call)

Edit the question **below the `---` line**. The outbound voice agent asks this
first, and it acts as a **consent gate**: per the system prompt, the agent will
not ask any check-in question or engage with anything the patient says until they
give a clear affirmative answer to it (a privacy question or a tangent just loops
back to re-asking this). So phrase it as something the patient can clearly say
"yes" or "no" to. Everything above the `---` is an editing note and is ignored —
only the text below it is spoken.

The backend reads this file fresh on every call, so a saved edit takes effect on
the next call with no restart needed.

---

Before we go through today's questions, I require your formal confirmation. Do you comply with and agree to the recording of this conversation, and the processing of your information in accordance with our privacy policy? Please say 'Yes, I agree' or 'No'.