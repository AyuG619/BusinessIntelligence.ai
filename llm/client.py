"""Thin wrapper around whichever LLM provider is configured.

Deliberately minimal: call_llm(prompt) -> {text, input_tokens, output_tokens,
est_cost_usd, model, latency_ms}. No prompt-management abstraction, no
intent router — narrative.py and corroborate.py build their own prompts
inline and call this directly.

If LLM_API_KEY is unset, falls back to a deterministic offline stub so the
whole pipeline (and the demo) still runs without network access.
"""
import os
import time
import pathlib
from dotenv import load_dotenv
from core.telemetry import log_event

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "offline").strip().lower()
MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b").strip()
API_KEY = (os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()

# Rough per-1K-token cost estimates for the telemetry panel (USD). Not billing-accurate.
_COST_PER_1K = {
    "gemini": (0.000075, 0.0003),
    "openai": (0.00015, 0.0006),
    "anthropic": (0.003, 0.015),
    "groq": (0.00059, 0.00079),
    "offline": (0.0, 0.0),
}


def _estimate_tokens(text: str) -> int:
    # ~4 chars/token heuristic, good enough for a telemetry estimate
    return max(1, len(text) // 4)


def _offline_stub(prompt: str) -> str:
    """Deterministic fallback used when no API key is configured.
    Good enough to keep the app runnable end-to-end offline; real narrative
    quality requires a configured provider.

    For evidence-classification prompts, returns empty text so the caller
    (evidence/corroborate.py) falls through to its keyword heuristic instead
    of always resolving to NEUTRAL.
    """
    if "SUPPORTS, CONTRADICTS, or NEUTRAL" in prompt:
        return ""
    return ("[Offline mode — configure LLM_API_KEY in .env for a generated narrative. "
            "Showing the underlying analytics only.]")


def _call_gemini(prompt: str, max_tokens: int) -> str:
    import requests

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    resp = requests.post(url, params={"key": API_KEY}, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }, timeout=30)
    if not resp.ok:
        detail = resp.text[:500].replace(API_KEY, "<redacted>")
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback") or data.get("blockedReason") or "no candidates"
        raise RuntimeError(f"Gemini returned no candidates: {reason}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        finish_reason = candidates[0].get("finishReason", "unknown")
        raise RuntimeError(f"Gemini returned no text (finish reason: {finish_reason})")
    return text


def _call_openai(prompt: str, max_tokens: int) -> str:
    import requests
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_groq(prompt: str, max_tokens: int) -> str:
    import requests

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "temperature": 0.2},
        timeout=30,
    )
    if not resp.ok:
        detail = resp.text[:500].replace(API_KEY, "<redacted>")
        raise RuntimeError(f"Groq HTTP {resp.status_code}: {detail}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Groq returned no choices: {data.get('error', 'unknown response')}")
    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise RuntimeError("Groq returned an empty response")
    return text


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    import requests
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                  "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def call_llm(prompt: str, stage: str = "llm_call", max_tokens: int = 400) -> dict:
    start = time.perf_counter()
    text = ""
    try:
        if PROVIDER == "gemini" and API_KEY:
            text = _call_gemini(prompt, max_tokens)
        elif PROVIDER == "openai" and API_KEY:
            text = _call_openai(prompt, max_tokens)
        elif PROVIDER == "groq" and API_KEY:
            text = _call_groq(prompt, max_tokens)
        elif PROVIDER == "anthropic" and API_KEY:
            text = _call_anthropic(prompt, max_tokens)
        else:
            text = _offline_stub(prompt)
    except Exception as e:  # noqa: BLE001 — surface as offline stub, never crash the demo
        text = _offline_stub(prompt) + f" (provider error: {e})"

    latency_ms = (time.perf_counter() - start) * 1000
    in_tok = _estimate_tokens(prompt)
    out_tok = _estimate_tokens(text)
    in_rate, out_rate = _COST_PER_1K.get(PROVIDER, (0.0, 0.0))
    cost = (in_tok / 1000) * in_rate + (out_tok / 1000) * out_rate

    log_event(stage, latency_ms, model=MODEL, input_tokens=in_tok,
               output_tokens=out_tok, est_cost_usd=round(cost, 6))

    return {
        "text": text,
        "model": MODEL,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "est_cost_usd": round(cost, 6),
        "latency_ms": round(latency_ms, 1),
    }
