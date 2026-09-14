"""OpenAI, Groq and OpenRouter: one Responses API client over the `openai` SDK."""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass

from core.llm import (SCHEMA_NAME, BatchUnsupported, Exchange, LlmError,
                      effort as llm_effort, max_tokens,
                      model_of, require_env, setting)



def _usage(raw: dict) -> dict:
    """Token counts, including the reasoning and cache breakdowns that decide what a run costs."""
    out_detail = raw.get("output_tokens_details") or {}
    in_detail = raw.get("input_tokens_details") or {}
    return {
        "inputTokens": raw.get("input_tokens"),
        "outputTokens": raw.get("output_tokens"),
        "reasoningTokens": out_detail.get("reasoning_tokens"),
        "cachedInputTokens": in_detail.get("cached_tokens"),
        "cacheWriteTokens": in_detail.get("cache_write_tokens"),
    }

#: One client per endpoint, keyed by key variable and base URL -- never one per call.
_CLIENTS: dict = {}


def _sdk(key_variable: str, base_url: str | None = None):
    """The SDK for one endpoint, created once, bringing its own retry-with-backoff on 429 and 5xx."""
    key = (key_variable, base_url)
    if key not in _CLIENTS:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise LlmError("the `openai` package is required -- pip install openai") from error
        _CLIENTS[key] = OpenAI(api_key=require_env(key_variable),
                               **({"base_url": base_url} if base_url else {}))
    return _CLIENTS[key]


@dataclass(frozen=True)
class OpenAIResponses:
    """One host of the Responses API."""

    name: str
    key_variable: str
    base_url: str | None = None
    supports_batch: bool = False
    #: OpenRouter serves one model id from several upstreams; force one that honours the schema.
    require_parameters: bool = False

    BATCH_ENDPOINT = "/v1/responses"

    def _client(self):
        return _sdk(self.key_variable, self.base_url)

    def _body(self, system: str, user: str, schema: dict | None) -> dict:
        """The Responses request, identical for sync and batch so batching changes only cost and timing."""
        body: dict = {
            "model": model_of(self.name),
            "input": [{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            "max_output_tokens": max_tokens(),
        }
        # None or empty both mean "send nothing"; None means the model rejects it. See llm.effort.
        depth = llm_effort(self.name)
        if depth:
            body["reasoning"] = {"effort": depth}
        if schema is not None:
            body["text"] = {"format": {"type": "json_schema", "name": SCHEMA_NAME,
                                       "schema": schema, "strict": True}}
        return body

    def _extra(self, schema: dict | None) -> dict:
        """OpenRouter-only routing hints, passed outside the request body."""
        if self.require_parameters and schema is not None:
            return {"extra_body": {"provider": {"require_parameters": True}}}
        return {}

    @staticmethod
    def _text(response) -> str:
        """The assistant text, from the SDK's convenience field or by walking the output."""
        text = getattr(response, "output_text", "") or ""
        if text.strip():
            return text
        parts = []
        for item in getattr(response, "output", None) or []:
            for block in getattr(item, "content", None) or []:
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts)

    def complete(self, system: str, user: str, schema: dict | None = None) -> Exchange:
        """One response, now, with the literal HTTP body kept as the response of record."""
        body = self._body(system, user, schema)
        started = time.perf_counter()
        # with_raw_response gives the literal HTTP body, so what is logged is what arrived.
        raw = self._client().responses.with_raw_response.create(**body, **self._extra(schema))
        elapsed = int((time.perf_counter() - started) * 1000)
        payload = json.loads(raw.text)
        response = raw.parse()

        text = self._text(response)
        if not text.strip():
            raise LlmError(f"{self.name} returned an empty completion")
        usage = payload.get("usage") or {}
        return Exchange(text=text, request=body, response=payload,
                        usage=_usage(usage),
                        elapsed_ms=elapsed, http_status=raw.status_code)

    def submit_batch(self, system: str, user: str, schema: dict | None = None) -> str:
        """Upload one JSONL line, create the batch, return its id."""
        if not self.supports_batch:
            raise BatchUnsupported(f"{self.name} is sync only here -- use --mode sync")

        line = json.dumps({"custom_id": "adrift-1", "method": "POST",
                           "url": self.BATCH_ENDPOINT,
                           "body": self._body(system, user, schema)}, sort_keys=True)
        payload = io.BytesIO(line.encode("utf-8"))
        payload.name = "adrift-batch.jsonl"
        sdk = self._client()
        uploaded = sdk.files.create(file=payload, purpose="batch")
        return sdk.batches.create(input_file_id=uploaded.id, endpoint=self.BATCH_ENDPOINT,
                                  completion_window="24h").id

    def batch_status(self, handle: str) -> str:
        """OpenAI says "completed" where Anthropic says "ended"; normalised to the latter."""
        status = self._client().batches.retrieve(handle).status
        return "ended" if status == "completed" else status

    def submit_batch_many(self, items: list[tuple[str, str, str]],
                          schema: dict | None = None) -> str:
        """Queue many prompts as ONE batch, given [(custom_id, system, user)]; ids must be unique."""
        seen = [c for c, _, _ in items]
        if len(set(seen)) != len(seen):
            raise LlmError("batch custom_ids must be unique -- duplicates would make it "
                           "impossible to say which cell a result belongs to")
        lines = "\n".join(
            json.dumps({"custom_id": cid, "method": "POST", "url": self.BATCH_ENDPOINT,
                        "body": self._body(system, user, schema)}, sort_keys=True)
            for cid, system, user in items)
        payload = io.BytesIO(lines.encode("utf-8"))
        payload.name = "adrift-batch.jsonl"
        sdk = self._client()
        uploaded = sdk.files.create(file=payload, purpose="batch")
        return sdk.batches.create(input_file_id=uploaded.id, endpoint=self.BATCH_ENDPOINT,
                                  completion_window="24h").id

    def fetch_batch(self, handle: str, custom_id: str = "adrift-1") -> tuple[str, dict]:
        """The text and usage for one custom_id in the batch, matched by id and never by position."""
        sdk = self._client()
        batch = sdk.batches.retrieve(handle)
        output_id = getattr(batch, "output_file_id", None)
        if not output_id:
            raise LlmError(f"batch {handle} produced no output file (status {batch.status})")
        for raw in sdk.files.content(output_id).text.splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            if record.get("custom_id") != custom_id:
                continue
            body = (record.get("response") or {}).get("body") or {}
            # A batched result is a decoded dict, so `_text`'s attribute walk finds nothing here.
            for item in body.get("output") or []:
                for block in item.get("content") or []:
                    if block.get("text"):
                        return str(block["text"]), _usage(body.get("usage") or {})
            raise LlmError(f"batch {handle} entry {custom_id} carried no text")
        raise LlmError(f"batch {handle} has no entry with custom_id {custom_id!r}")


_HOSTS = {
    "openai": OpenAIResponses("openai", "OPENAI_API_KEY", supports_batch=True),
    "groq": OpenAIResponses("groq", "GROQ_API_KEY",
                            base_url="https://api.groq.com/openai/v1"),
    "openrouter": OpenAIResponses("openrouter", "OPENROUTER_API_KEY",
                                  base_url="https://openrouter.ai/api/v1",
                                  require_parameters=True),
}


def for_provider(name: str) -> OpenAIResponses:
    """The host serving `name`. `clients.for_provider` has already rejected unknown ones."""
    return _HOSTS[name]
