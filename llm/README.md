# LLM querying pipeline (Gemma 4 / vLLM)

A small, reusable pipeline for querying an LLM over the OpenAI Chat Completions API.
Two interchangeable backends, selected with `LLM_PROVIDER`:

| `LLM_PROVIDER` | Backend | Model (default) | Key |
| --- | --- | --- | --- |
| `gemini` *(default)* | **Gemma 4** via the Gemini API | `gemma-4-26b-a4b-it` | `GEMINI_API_KEY` |
| `vllm` | Local vLLM server | `Qwen/Qwen2.5-7B-Instruct-AWQ` | none |

The instruction prompts are pulled from Markdown files in the repo root, so behaviour
is changed by editing text, not code.

```
llm/
  config.py                       backend / model / prompt-path settings (env-overridable)
  client.py                       LLMClient — load_prompt(), chat(), chat_json()
  fix_chronic_conditions.py       MAIN task: drop garbage + inject HK/Asia diseases
  clean_chronic_conditions.py     legacy: drop-only cleanup (keep/drop report)
  serve_vllm.sh                   launch a local vLLM server (tuned for 8 GB GPU)
  hk_asia_chronic_catalog.json    model-curated disease catalogue (generated on first run)
  chronic_conditions_decisions.json  cached keep/drop report
  original_chronic_conditions_backup.json  pre-edit snapshot (undo source for --restore)
  requirements.txt
../chronic_conditions_prompt.md         keep/drop classifier prompt (editable)
../chronic_conditions_inject_prompt.md  HK/Asia catalogue prompt (editable)
```

## Quickstart — Gemma 4 (default)

```bash
conda activate qwen-vllm                       # has the `openai` SDK installed
pip install -r llm/requirements.txt            # if needed
export GEMINI_API_KEY=...                       # https://aistudio.google.com/apikey

# dry run: drop the noisy findings + preview the randomly injected HK/Asia diseases
python -m llm.fix_chronic_conditions

# apply in place (git-tracked, so reversible)
python -m llm.fix_chronic_conditions --apply
```

To use the bigger hosted Gemma 4: `GEMINI_MODEL=gemma-4-31b-it python -m llm.fix_chronic_conditions`.

## The fix-chronic-conditions task

`fix_chronic_conditions.py` does the whole fix in one pass:

1. **Drop garbage.** Every distinct condition label is classified keep/drop by the
   model (social/lifestyle/acute findings → dropped, genuine diseases → kept). The
   report is cached in `chronic_conditions_decisions.json` and reused; pass
   `--reclassify` to re-run it.
2. **Inject replacements.** The model curates a catalogue of chronic diseases common
   in **Hong Kong / Asia** (cached in `hk_asia_chronic_catalog.json`; `--rebuild-catalog`
   to refresh). Python then samples it randomly — weighted by prevalence — so each
   affected patient ends up with 2–3 genuine chronic conditions. Genuine conditions
   already present are kept; the random draw is reproducible via `--seed`.

Useful flags:

```
--apply             write changes (default: dry run)
--seed N            RNG seed for the random assignment (default 42)
--min N / --max N   conditions per affected patient (default 2 / 3)
--reclassify        re-run keep/drop with the model
--rebuild-catalog   re-query the HK/Asia catalogue
--offline           skip the model: reuse the cached report + a built-in fallback
                    catalogue (handy with no key / no network)
--fill-empty        also seed patients who had no conditions
```

`data/fhir_processed/` is **gitignored** (not tracked), so git can't undo `--apply`.
Instead, the first `--apply` snapshots every patient's original `chronic_conditions`
to `llm/original_chronic_conditions_backup.json` (never overwritten once created).
Undo with `python -m llm.fix_chronic_conditions --restore`.

> The dashboard reads patient data from **MongoDB**, not these files directly. To
> surface the cleaned conditions, re-import: `python -m scripts.import_fhir_to_mongo`
> (from `backend/`). That overwrites Mongo — keep the backup JSON if you want the
> originals.

## Local vLLM backend (alternative)

```bash
conda activate qwen-vllm
bash llm/serve_vllm.sh                          # serves Qwen2.5-7B-Instruct-AWQ on :8001
LLM_PROVIDER=vllm python -m llm.fix_chronic_conditions
```

Fits an 8 GB GPU (AWQ 4-bit). For OOM, drop to a smaller model:
`VLLM_MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ bash llm/serve_vllm.sh`.

## Reuse for other tasks

```python
from llm.client import LLMClient
client = LLMClient(prompt_file="my_prompt.md")   # any .md in the repo root
answer = client.chat("...")            # uses the .md as the system prompt
data   = client.chat_json("...")       # parses a JSON object out of the reply
```

Override via env: `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL`
(Gemma); `VLLM_BASE_URL`, `VLLM_MODEL` (vLLM); `PROMPT_FILE`, `INJECT_PROMPT_FILE`.
