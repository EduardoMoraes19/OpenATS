"""Multi-provider LLM gateway via OpenRouter (https://openrouter.ai/docs) -
one HTTP API, one key, model/provider chosen per-request by `model` id
(e.g. "google/gemini-2.5-flash", "anthropic/claude-3.5-sonnet",
"openai/gpt-4o"). Swapping provider or model is an OPENROUTER_MODEL env var
change, or a `model=` argument here - never a code change. Any module that
needs an LLM call imports this, not a provider-specific SDK.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.settings import settings

_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
_TIMEOUT_SECONDS = 30.0

_client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)


async def complete(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    plugins: list[dict[str, Any]] | None = None,
) -> str:
    """Sends a chat-completion request, returns the assistant's raw text.
    Raises on any transport/HTTP error or an empty response - callers
    decide what "fatal" means for them (see cv_analysis's non-fatal
    AI-summary call for an example of catching this)."""
    payload: dict[str, Any] = {"model": model or settings.openrouter_model, "messages": messages}
    if plugins:
        payload["plugins"] = plugins

    response = await _client.post(
        _BASE_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json=payload,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if not content:
        raise RuntimeError("OpenRouter returned no content in its response")
    return content


def pdf_content_part(*, filename: str, pdf_bytes: bytes) -> dict[str, Any]:
    """An OpenRouter `file` content part for PDF input - pair with
    `pdf_parser_plugin()` in the same request's `plugins`."""
    encoded = base64.b64encode(pdf_bytes).decode()
    return {
        "type": "file",
        "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{encoded}"},
    }


def pdf_parser_plugin(engine: str = "pdf-text") -> dict[str, Any]:
    """engine="pdf-text" (default) extracts embedded PDF text - works with
    any text model, not just ones with native document support. Use
    "mistral-ocr" for scanned/image PDFs (paid, ~$2/1000 pages)."""
    return {"id": "file-parser", "pdf": {"engine": engine}}


def strip_markdown_fences(text: str) -> str:
    """Models often wrap JSON responses in ``` fences regardless of
    provider - strip them before json.loads."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.strip()
