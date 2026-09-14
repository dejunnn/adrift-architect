"""The provider registry -- one client module per API shape -- and the batch poller."""

from __future__ import annotations

import os
import time

from core.llm import DONE, FAILED, PROVIDERS, LlmError


def for_provider(provider: str):
    """The client for one provider, imported lazily so a missing SDK breaks only that provider."""
    if provider not in PROVIDERS:
        raise LlmError(f"unknown provider {provider!r} -- choose from {', '.join(PROVIDERS)}")
    if provider == "anthropic":
        from clients.anthropic_api import Anthropic
        return Anthropic()
    if provider == "gemini":
        from clients.gemini_api import Gemini
        return Gemini()
    if provider == "ollama":
        from clients.ollama_api import Ollama
        return Ollama()
    from clients import openai_api
    return openai_api.for_provider(provider)


def await_batch(provider: str, handle: str, on_poll=None,
                custom_id: str = "adrift-1") -> tuple[str, dict]:
    """Poll until the batch ends, then return one entry's text and usage, selected by `custom_id`."""
    engine = for_provider(provider)
    interval = int(os.environ.get("ADRIFT_BATCH_POLL_SECONDS", "20"))
    deadline = time.time() + int(os.environ.get("ADRIFT_BATCH_TIMEOUT_SECONDS", "86400"))
    while time.time() < deadline:
        status = engine.batch_status(handle)
        if status in DONE:
            return engine.fetch_batch(handle, custom_id)
        if status in FAILED:
            raise LlmError(f"batch {handle} ended as {status}")
        if on_poll:
            on_poll(status)
        time.sleep(interval)
    raise LlmError(f"batch {handle} still {engine.batch_status(handle)} after the timeout -- "
                   f"re-run to resume polling")
