"""Central config for the LLM querying pipeline.

Two backends are supported, selected with ``LLM_PROVIDER``:

* ``gemini`` (default) - Google's **Gemma 4** served through the Gemini API's
  OpenAI-compatible endpoint. Needs ``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``).
* ``vllm`` - a local vLLM OpenAI-compatible server (e.g. Qwen via
  ``serve_vllm.sh``). No key required.

Both speak the OpenAI Chat Completions API, so the same ``client.py`` drives
either one. Everything below is overridable via environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root = parent of this `llm/` package directory.
REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Provider selection ----------------------------------------------------
# "gemini" -> Gemma 4 via the Gemini API; "vllm" -> local vLLM server.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# --- Gemini API (Gemma 4) --------------------------------------------------
# The Gemini API exposes an OpenAI-compatible surface; point the OpenAI SDK at
# it and use a Gemma model id. Get a key from https://aistudio.google.com/apikey
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
# Hosted Gemma 4 instruction-tuned models: gemma-4-26b-a4b-it, gemma-4-31b-it.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it")

# --- Local vLLM / OpenAI-compatible endpoint -------------------------------
# vLLM exposes an OpenAI-compatible API. We use 8001 because the FastAPI
# backend already owns 8000.
VLLM_HOST = os.getenv("VLLM_HOST", "127.0.0.1")
VLLM_PORT = os.getenv("VLLM_PORT", "8001")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", f"http://{VLLM_HOST}:{VLLM_PORT}/v1")
# vLLM ignores the key but the OpenAI SDK requires a non-empty string.
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")
# Served model id. Must match what `vllm serve <model>` was launched with.
# Default fits an 8 GB GPU (AWQ 4-bit, ~5.5 GB weights).
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")


def active_backend() -> dict:
    """Resolve (base_url, api_key, model, merge_system) for the active provider.

    ``merge_system`` folds the system prompt into the user turn - Gemma served
    through the Gemini API does not always accept a separate ``system`` role, so
    we inline it there to stay robust.
    """
    if LLM_PROVIDER == "vllm":
        return {
            "base_url": VLLM_BASE_URL,
            "api_key": VLLM_API_KEY,
            "model": VLLM_MODEL,
            "merge_system": False,
        }
    # default: gemini / gemma
    return {
        "base_url": GEMINI_BASE_URL,
        "api_key": GEMINI_API_KEY,
        "model": GEMINI_MODEL,
        "merge_system": True,
    }


# --- Prompts ---------------------------------------------------------------
# System prompts live in Markdown files in the repo root so they are easy to
# edit. Override the classifier prompt with PROMPT_FILE.
PROMPT_FILE = os.getenv("PROMPT_FILE", "chronic_conditions_prompt.md")
INJECT_PROMPT_FILE = os.getenv("INJECT_PROMPT_FILE", "chronic_conditions_inject_prompt.md")

# --- Data ------------------------------------------------------------------
DATA_DIR = Path(os.getenv("FHIR_DATA_DIR", str(REPO_ROOT / "data" / "fhir_processed")))

# Cached, model-curated catalogue of HK/Asia chronic diseases (see
# fix_chronic_conditions.py). Built once by the model, then reused.
CATALOG_FILE = Path(
    os.getenv("HK_ASIA_CATALOG_FILE", str(REPO_ROOT / "llm" / "hk_asia_chronic_catalog.json"))
)

# How many chronic conditions an affected patient should end up with.
INJECT_MIN = int(os.getenv("INJECT_MIN", "2"))
INJECT_MAX = int(os.getenv("INJECT_MAX", "3"))

# --- Generation defaults ---------------------------------------------------
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", os.getenv("VLLM_TEMPERATURE", "0.0")))
# Gemma 4 is a reasoning model: it spends tokens on a <thought> block before the
# JSON answer, so it needs a generous budget. The local vLLM context is small
# (4096), so keep its default low.
_DEFAULT_MAX_TOKENS = "2048" if LLM_PROVIDER == "vllm" else "16384"
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("VLLM_MAX_TOKENS", _DEFAULT_MAX_TOKENS)))


def resolve_prompt_path(prompt_file: str | None = None) -> Path:
    """Resolve a prompt path; relative paths are taken from the repo root."""
    p = Path(prompt_file or PROMPT_FILE)
    return p if p.is_absolute() else (REPO_ROOT / p)
