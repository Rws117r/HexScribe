# hexscribe/ai/feature_description_ai.py
from __future__ import annotations

import os
import json
from typing import Optional
import requests

# ------------------------------------------------------------------------------
# Ollama connection
# ------------------------------------------------------------------------------
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
DEFAULT_MODEL = os.environ.get("HEXSCRIBE_MODEL", "llama3.2:3b")

# ------------------------------------------------------------------------------
# Prompting and length control
# ------------------------------------------------------------------------------
SYSTEM_INSTRUCTION = (
    "You are a seasoned fantasy setting stylist. Rewrite terse hex-crawl feature notes "
    "into one evocative, game-usable paragraph. Keep all stated facts; do not invent new lore. "
    "Use present tense, avoid second person and purple prose, and keep it concise."
)

# soft target, reinforced in prompt; we also hard-trim after generation
TARGET_WORDS_MIN = 70
TARGET_WORDS_MAX = 110
DEFAULT_MAX_WORDS = 220  # relaxed because we'll scroll visually


def generate_feature_description(
    notes: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.6,
    timeout: int = 60,
    stream: bool = True,
    tone: Optional[str] = None,
    max_words: int = DEFAULT_MAX_WORDS,
) -> str:
    """
    Transform raw notes into a single polished fantasy paragraph.
    Returns text trimmed to max_words (word boundary; adds ellipsis if needed).
    """
    prompt = _build_prompt(notes, tone=tone)
    try:
        if stream:
            out = _generate_stream(model, prompt, temperature, timeout)
        else:
            out = _generate_blocking(model, prompt, temperature, timeout)
    except requests.RequestException as e:
        try:
            out = _generate_blocking(model, prompt, temperature, timeout)
        except Exception:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    return _trim_to_words(out, max_words).strip()


# ------------------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------------------
def _build_prompt(notes: str, *, tone: Optional[str]) -> str:
    tone_line = f"Preferred tone: {tone}.\n" if tone else ""
    return (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"{tone_line}"
        f"Notes:\n{notes.strip()}\n\n"
        f"Output:\nA single paragraph of {TARGET_WORDS_MIN}-{TARGET_WORDS_MAX} words, "
        f"rich with sensory detail, present tense, and game-ready clarity."
    )


def _generate_stream(model: str, prompt: str, temperature: float, timeout: int) -> str:
    out_parts: list[str] = []
    with requests.post(
        GENERATE_URL,
        json={"model": model, "prompt": prompt, "stream": True, "options": {"temperature": temperature}},
        stream=True,
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            j = json.loads(line.decode("utf-8"))
            out_parts.append(j.get("response", ""))
            if j.get("done"):
                break
    return "".join(out_parts)


def _generate_blocking(model: str, prompt: str, temperature: float, timeout: int) -> str:
    resp = requests.post(
        GENERATE_URL,
        json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature}},
        timeout=timeout,
    )
    resp.raise_for_status()
    j = resp.json()
    return j.get("response", "")


def _trim_to_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    clipped = " ".join(words[:max_words])
    if not clipped.endswith((".", "!", "?", "…")):
        clipped += "…"
    return clipped
