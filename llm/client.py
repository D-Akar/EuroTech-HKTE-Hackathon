"""Reusable client for querying a vLLM (OpenAI-compatible) server.

Usage:
    from llm.client import VLLMClient
    client = VLLMClient()                  # reads config.py / env
    text = client.chat("Hello")            # one-shot
    obj  = client.chat_json([...msgs...])  # parse a JSON object out of the reply

The *instruction* prompt is pulled from a Markdown file (see config.PROMPT_FILE).
Edit that .md to change behaviour - no code change needed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from . import config


def load_prompt(prompt_file: str | None = None) -> str:
    """Load the system prompt from a Markdown file in the repo root.

    The file may contain a `---` horizontal rule; everything after the *first*
    such line on its own is treated as the actual prompt, so the top of the .md
    can hold human-facing notes. If there is no `---`, the whole file is used.
    """
    path = config.resolve_prompt_path(prompt_file)
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^---\s*$", text, maxsplit=1)
    body = parts[1] if len(parts) == 2 else parts[0]
    return body.strip()


def extract_json(text: str) -> Any:
    """Best-effort parse of a JSON object/array out of a model reply.

    Handles raw JSON, ```json fenced blocks, and leading/trailing prose.
    """
    text = text.strip()
    # Strip reasoning blocks emitted by thinking models (Gemma 4: <thought>...,
    # others: <think>...). The JSON answer comes after the closing tag.
    text = re.sub(r"(?is)<(thought|think)>.*?</\1>", "", text).strip()
    # Strip markdown fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} or [...] span.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    raise ValueError(f"No JSON found in model reply:\n{text[:500]}")


class VLLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        prompt_file: str | None = None,
        merge_system: bool | None = None,
    ) -> None:
        backend = config.active_backend()
        self.base_url = base_url or backend["base_url"]
        self.model = model or backend["model"]
        self.prompt_file = prompt_file
        # Gemma via the Gemini API does not reliably accept a separate `system`
        # role, so we fold the system prompt into the user turn for that backend.
        self.merge_system = backend["merge_system"] if merge_system is None else merge_system
        self._client = OpenAI(base_url=self.base_url, api_key=api_key or backend["api_key"])

    # -- low level ----------------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=config.TEMPERATURE if temperature is None else temperature,
            max_tokens=config.MAX_TOKENS if max_tokens is None else max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    # -- convenience --------------------------------------------------------
    def chat(self, user: str, *, system: str | None = None, **kw) -> str:
        """One-shot chat. `system` defaults to the prompt from the .md file."""
        sys_prompt = system if system is not None else load_prompt(self.prompt_file)
        messages = []
        if sys_prompt and self.merge_system:
            # Inline the system prompt for backends (Gemma) that reject `system`.
            user = f"{sys_prompt}\n\n---\n\n{user}"
        elif sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": user})
        return self.complete(messages, **kw)

    def chat_json(self, user: str, *, system: str | None = None, **kw) -> Any:
        # NOTE: we deliberately do NOT use vLLM's response_format=json_object
        # (guided decoding). The xgrammar backend in this build crashes the
        # server (nanobind refcount bug). temperature=0 + the prompt's JSON
        # contract is reliable, and extract_json tolerates fences/prose.
        kw.setdefault("json_mode", False)
        return extract_json(self.chat(user, system=system, **kw))

    def health(self) -> bool:
        """True if the server answers a models list."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False


# Provider-neutral alias - the client speaks OpenAI Chat Completions to either
# the Gemini API (Gemma 4) or a local vLLM server, per config.LLM_PROVIDER.
LLMClient = VLLMClient
