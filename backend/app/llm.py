"""Provider-pluggable LLM wrapper.

Two backends behind one function:
  - gemini    — Google Gemini API free tier (default when GEMINI_API_KEY is set)
  - anthropic — Claude, used when LLM_PROVIDER=anthropic and credits exist

Every call is schema-validated against a Pydantic model; on any validation
failure we retry exactly once with the error message included (spec 4/9.6).
The citation verifier downstream is the second line of defense — no LLM
output reaches the UI unchecked."""

import time
from typing import TypeVar

from pydantic import BaseModel

from .config import (
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_MODEL,
    LLM_PROVIDER,
)

T = TypeVar("T", bound=BaseModel)


class LLMKeyMissingError(Exception):
    pass


# ----------------------------------------------------------------- gemini

_gemini_client = None


def _get_gemini():
    global _gemini_client
    if not GEMINI_API_KEY:
        raise LLMKeyMissingError(
            "GEMINI_API_KEY is not set — free key at https://aistudio.google.com/apikey"
        )
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


# Free-tier daily quotas are per-model, so when the primary model's bucket is
# exhausted we fall back to the next one rather than failing the analysis.
GEMINI_FALLBACK_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash-lite"]

# Models that returned a daily-quota 429 this process; skipped until restart.
# Without this, the SDK's internal retry loop re-hammers the dead model on
# every call and a 12-call pipeline stretches to ~20 minutes.
_exhausted_models: set[str] = set()


def _gemini_models() -> list[str]:
    models = [GEMINI_MODEL]
    models += [m for m in GEMINI_FALLBACK_MODELS if m not in models]
    live = [m for m in models if m not in _exhausted_models]
    return live or models  # if everything is marked dead, try anyway


def _with_gemini_quota_fallback(fn):
    """Run fn(model) across the model ladder. A per-minute 429 waits and
    retries the same model; a daily-quota 429 marks the model exhausted for
    this process and moves to the next one."""
    from google.genai import errors as genai_errors

    last_error: Exception | None = None
    for model in _gemini_models():
        for attempt in range(3):
            try:
                return fn(model)
            except genai_errors.APIError as e:
                code = getattr(e, "code", None)
                last_error = e
                if code == 429 and "PerDay" in str(e):
                    _exhausted_models.add(model)  # daily quota — next model
                    break
                if code == 429:
                    time.sleep(30)  # per-minute window — retry same model
                    continue
                if code == 503:
                    time.sleep(45)  # transient overload — retry same model
                    continue
                raise
    raise last_error  # every model failed


def _gemini_structured(
    system: str, user_content: str, output_model: type[T],
    temperature: float, max_tokens: int,
) -> T:
    from google.genai import types as genai_types

    client = _get_gemini()

    def attempt(model: str, extra: str = "") -> T:
        response = client.models.generate_content(
            model=model,
            contents=user_content + extra,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                response_schema=output_model,
            ),
        )
        parsed = response.parsed
        if parsed is None:
            snippet = (response.text or "")[:500]
            raise ValueError(f"Gemini output failed schema validation: {snippet!r}")
        return parsed

    def run(model: str) -> T:
        try:
            return attempt(model)
        except ValueError as e:
            return attempt(model, _retry_suffix(e))

    return _with_gemini_quota_fallback(run)


# --------------------------------------------------------------- anthropic

_anthropic_client = None


def _get_anthropic():
    global _anthropic_client
    if not ANTHROPIC_API_KEY:
        raise LLMKeyMissingError("ANTHROPIC_API_KEY is not set — add it to backend/.env")
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _anthropic_structured(
    system: str, user_content: str, output_model: type[T],
    temperature: float, max_tokens: int,
) -> T:
    client = _get_anthropic()

    def attempt(extra: str = "") -> T:
        response = client.messages.parse(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user_content + extra}],
            output_format=output_model,
        )
        if response.parsed_output is None:
            raise ValueError(
                f"Model output failed schema validation (stop_reason={response.stop_reason})"
            )
        return response.parsed_output

    try:
        return attempt()
    except ValueError as e:
        return attempt(_retry_suffix(e))


def call_grounded_search(prompt: str, temperature: float = 0.2) -> tuple[str, list[str]]:
    """Web-grounded research call. Returns (research_text, source_urls).

    Source URLs come from the search grounding metadata — the model cannot
    fabricate them. Gemini only for now (Anthropic path would use the
    web_search server tool)."""
    if LLM_PROVIDER != "gemini":
        raise NotImplementedError("Grounded search is implemented for the Gemini provider")

    from google.genai import types as genai_types

    client = _get_gemini()

    def run(model: str) -> tuple[str, list[str]]:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                temperature=temperature,
            ),
        )
        text = response.text or ""
        urls: list[str] = []
        candidates = response.candidates or []
        metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            if uri and uri not in urls:
                urls.append(uri)
        return text, urls

    return _with_gemini_quota_fallback(run)


# ------------------------------------------------------------------ shared

def _retry_suffix(e: Exception) -> str:
    return (
        f"\n\nYour previous attempt failed validation with this error: {e}. "
        "Correct the problem and produce output that conforms exactly to the schema."
    )


def call_structured(
    system: str,
    user_content: str,
    output_model: type[T],
    temperature: float = 0.0,
    max_tokens: int = 16000,
) -> T:
    """One structured LLM call via the active provider, validated against
    output_model, with a single retry-on-validation-failure."""
    if LLM_PROVIDER == "gemini":
        return _gemini_structured(system, user_content, output_model, temperature, max_tokens)
    return _anthropic_structured(system, user_content, output_model, temperature, max_tokens)
