"""Google Gemini over the `google-genai` interactions API. Sync only -- batch raises rather than downgrading."""

from __future__ import annotations

import time

from core.llm import (BatchUnsupported, Exchange, LlmError, effort as llm_effort, max_tokens,
                      model_of, require_env)

#: Interaction statuses meaning the model stopped before finishing -- named when the text is empty.
TRUNCATED = ("incomplete", "budget_exceeded", "failed", "cancelled")


def _usage(raw: dict) -> dict:
    """Token counts mapped onto the shared names; Gemini's thought tokens sit outside the output figure."""
    return {
        "inputTokens": raw.get("total_input_tokens"),
        "outputTokens": raw.get("total_output_tokens"),
        "reasoningTokens": raw.get("total_thought_tokens"),
        "cachedInputTokens": raw.get("total_cached_tokens"),
        "cacheWriteTokens": None,
    }


def _sdk():
    """A configured SDK client. Imported here so a missing package breaks only this provider."""
    try:
        from google import genai
    except ImportError as error:
        raise LlmError("the `google-genai` package is required -- "
                       "pip install google-genai") from error
    # The key is passed explicitly, so a stray GOOGLE_API_KEY cannot outrank the one in .env.
    return genai.Client(api_key=require_env("GEMINI_API_KEY"))


class Gemini:
    """Gemini interactions: reasoning depth and structured output are separate request fields."""

    name = "gemini"
    supports_batch = False

    def _params(self, system: str, user: str, schema: dict | None) -> dict:
        """The request body, built once and sent as-is so what is logged is what was sent."""
        # On this API ADRIFT_MAX_TOKENS bounds thinking plus answer, not the answer alone.
        generation_config: dict = {"max_output_tokens": max_tokens()}

        # None or empty both mean "send nothing"; levels are minimal|low|medium|high. See llm.effort.
        depth = llm_effort(self.name)
        if depth:
            generation_config["thinking_level"] = depth
            # Summaries OFF: the cost is already visible as `total_thought_tokens`.
            generation_config["thinking_summaries"] = "none"

        params: dict = {
            "model": model_of(self.name),
            "system_instruction": system,
            "input": user,
            "generation_config": generation_config,
        }
        if schema is not None:
            # The Interactions spelling: the schema sits under `response_format.schema`.
            params["response_format"] = {"type": "text",
                                         "mime_type": "application/json",
                                         "schema": schema}
        return params

    def complete(self, system: str, user: str, schema: dict | None = None) -> Exchange:
        """One interaction, now."""
        params = self._params(system, user, schema)
        # BOUND TO A LOCAL: sub-resources do not keep the client alive, and it closes when collected.
        sdk = _sdk()
        started = time.perf_counter()
        interaction = sdk.interactions.create(**params)
        elapsed = int((time.perf_counter() - started) * 1000)

        # A re-serialisation, not the literal HTTP body -- this SDK exposes no raw-response accessor.
        payload = interaction.model_dump(mode="json", exclude_none=True)

        text = getattr(interaction, "output_text", "") or ""
        if not text.strip():
            status = payload.get("status") or "?"
            raise LlmError(f"gemini returned an empty completion (status={status})"
                           + (" -- raise ADRIFT_MAX_TOKENS" if status in TRUNCATED else ""))
        return Exchange(text=text, request=params, response=payload,
                        usage=_usage(payload.get("usage") or {}),
                        elapsed_ms=elapsed,
                        # No status line from the SDK, so None rather than a guessed 200.
                        http_status=None)

    def submit_batch(self, *_args, **_kwargs) -> str:
        """Always raises: Gemini's batch endpoint is not wired here, and a sync fallback would misbill."""
        raise BatchUnsupported("gemini is sync only here -- use --mode sync")

    def batch_status(self, handle: str) -> str:
        """Always raises -- see submit_batch."""
        raise BatchUnsupported("gemini is sync only here")

    def fetch_batch(self, handle: str) -> tuple[str, dict]:
        """Always raises -- see submit_batch."""
        raise BatchUnsupported("gemini is sync only here")
