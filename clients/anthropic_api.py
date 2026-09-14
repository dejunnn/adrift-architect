"""Anthropic messages over the `anthropic` SDK, sync or batched."""

from __future__ import annotations

import json
import time

from core.llm import (Exchange, LlmError, effort as llm_effort, max_tokens, model_of,
                      require_env)



def _usage(raw: dict) -> dict:
    """Token counts, including the cache fields Anthropic keeps out of `input_tokens`."""
    return {
        "inputTokens": raw.get("input_tokens"),
        "outputTokens": raw.get("output_tokens"),
        # Thinking is billed as output and never broken out, so this stays None rather than guessed.
        "reasoningTokens": None,
        "cachedInputTokens": raw.get("cache_read_input_tokens"),
        "cacheWriteTokens": raw.get("cache_creation_input_tokens"),
    }

#: One client for the process, never one per call: a dropped client's finaliser breaks batch reads.
_CLIENT = None


def _sdk():
    """The process's SDK client, created once. See _CLIENT for why it must not be per-call."""
    global _CLIENT
    if _CLIENT is None:
        try:
            from anthropic import Anthropic as Sdk
        except ImportError as error:
            raise LlmError("the `anthropic` package is required -- pip install anthropic") from error
        _CLIENT = Sdk(api_key=require_env("ANTHROPIC_API_KEY"))
    return _CLIENT


#: Attempts at READING a finished batch's results -- a transport fault, not a model retry.
RETRIES = 3


class Anthropic:
    """Anthropic messages: reasoning depth and structured output both ride on `output_config`."""

    name = "anthropic"
    supports_batch = True

    def _params(self, system: str, user: str, schema: dict | None) -> dict:
        """The request body, identical for sync and batch so batching cannot change an answer."""
        output_config: dict = {}
        # None means the model must be sent no reasoning parameters at all -- see llm.effort.
        depth = llm_effort(self.name)
        if depth:
            output_config["effort"] = depth
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}

        params: dict = {
            "model": model_of(self.name),
            "max_tokens": max_tokens(),
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if depth is not None:
            # `summarized` rather than the default, which bills the reasoning but never returns it.
            params["thinking"] = {"type": "adaptive", "display": "summarized"}
        if output_config:
            params["output_config"] = output_config
        return params

    @staticmethod
    def _text(message) -> str:
        """Text blocks only -- thinking blocks are reasoning, not the answer."""
        return "".join(block.text for block in message.content
                       if getattr(block, "type", "") == "text")

    def complete(self, system: str, user: str, schema: dict | None = None) -> Exchange:
        """One message, now. The raw HTTP body is kept as the response of record."""
        params = self._params(system, user, schema)
        started = time.perf_counter()
        raw = _sdk().messages.with_raw_response.create(**params)
        elapsed = int((time.perf_counter() - started) * 1000)
        payload = json.loads(raw.text)
        message = raw.parse()

        text = self._text(message)
        if not text.strip():
            raise LlmError("anthropic returned an empty completion "
                           f"(stop_reason={getattr(message, 'stop_reason', '?')})")
        usage = payload.get("usage") or {}
        return Exchange(text=text, request=params, response=payload,
                        usage=_usage(usage),
                        elapsed_ms=elapsed, http_status=raw.status_code)

    def submit_batch(self, system: str, user: str, schema: dict | None = None) -> str:
        """Queue the same request as a one-entry batch. Returns the handle to poll."""
        batch = _sdk().messages.batches.create(
            requests=[{"custom_id": "adrift-1",
                       "params": self._params(system, user, schema)}])
        return batch.id

    def batch_status(self, handle: str) -> str:
        """Anthropic's own vocabulary; `core.llm.DONE` and `FAILED` interpret it."""
        return _sdk().messages.batches.retrieve(handle).processing_status

    def submit_batch_many(self, items: list[tuple[str, str, str]],
                          schema: dict | None = None) -> str:
        """Queue MANY prompts as ONE batch, given [(custom_id, system, user)]; ids must be unique."""
        seen = [c for c, _, _ in items]
        if len(set(seen)) != len(seen):
            raise LlmError("batch custom_ids must be unique -- duplicates would make it "
                           "impossible to say which cell a result belongs to")
        batch = _sdk().messages.batches.create(
            requests=[{"custom_id": cid, "params": self._params(system, user, schema)}
                      for cid, system, user in items])
        return batch.id

    def fetch_batch(self, handle: str, custom_id: str = "adrift-1") -> tuple[str, dict]:
        """The text and usage for one custom_id, matched by id and drained before anything is selected."""
        entries: dict = {}
        problem: Exception | None = None
        for attempt in range(RETRIES):
            try:
                entries = {getattr(e, "custom_id", None): e
                           for e in _sdk().messages.batches.results(handle)}
                problem = None
                break
            except Exception as error:                      # transport, not the model
                problem, entries = error, {}
                time.sleep(2 ** attempt)
        if problem is not None:
            raise LlmError(f"could not read results for batch {handle}: {problem}") from problem

        entry = entries.get(custom_id)
        if entry is None:
            raise LlmError(f"batch {handle} has no entry with custom_id {custom_id!r} "
                           f"({len(entries)} entries present)")
        if entry.result.type != "succeeded":
            raise LlmError(f"batch {handle} entry {custom_id} failed: {entry.result.type}")
        message = entry.result.message
        raw = message.model_dump() if hasattr(message, "model_dump") else {}
        return self._text(message), _usage(raw.get("usage") or {})
