"""Local models over Ollama's HTTP API -- no SDK, sync only, and retrying for itself."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from core.llm import BatchUnsupported, Exchange, LlmError, model_of, num_ctx, setting

RETRIES = 3

#: Seconds to wait on the daemon before abandoning an attempt and retrying. Short on purpose.
TIMEOUT = int(os.environ.get("ADRIFT_OLLAMA_TIMEOUT", "120"))


class Ollama:
    """Ollama's /api/chat. Sync only -- there is no batch endpoint to wrap."""

    name = "ollama"
    supports_batch = False

    @staticmethod
    def _host() -> str:
        """The daemon's base URL, trailing slash stripped so paths concatenate cleanly."""
        return os.environ.get("ADRIFT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    def complete(self, system: str, user: str, schema: dict | None = None) -> Exchange:
        """One chat completion. Retries only when the daemon did not answer -- see below."""
        body: dict = {
            "model": model_of(self.name),
            "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "keep_alive": os.environ.get("ADRIFT_OLLAMA_KEEP_ALIVE", "5m"),
            # Ollama's reasoning switch is a BOOLEAN, so an effort string like "medium" reads false.
            "think": setting(self.name, "THINK").lower() in ("1", "true", "yes", "on"),
        }
        if schema is not None:
            # Ollama takes the schema itself, not a wrapper around it.
            body["format"] = schema
        window = num_ctx()
        if window is not None:
            # Ollama has no output ceiling, only `num_ctx`, which bounds prompt and completion together.
            body["options"] = {"num_ctx": window}

        request = urllib.request.Request(
            f"{self._host()}/api/chat", data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"}, method="POST")
        started = time.perf_counter()
        status, data = None, None
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    status = response.status
                    data = json.loads(response.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as error:
                # The daemon answered and refused; retrying would just repeat the same rejection.
                detail = error.read().decode("utf-8", "replace").strip()[:300]
                raise LlmError(f"ollama returned {error.code}: {detail or error.reason}") from error
            except (urllib.error.URLError, TimeoutError) as error:
                # No answer at all -- daemon down, loading a model, or timed out. Worth retrying.
                if attempt == RETRIES - 1:
                    raise LlmError(f"ollama at {self._host()} unreachable after {RETRIES} "
                                   f"attempts: {error}") from error
                time.sleep(2 ** attempt)
        elapsed = int((time.perf_counter() - started) * 1000)

        text = data.get("message", {}).get("content", "")
        if not text.strip():
            raise LlmError("ollama returned an empty completion")
        # Ollama names its counters differently; normalised here, raw values stay in `data`.
        return Exchange(text=text, request=body, response=data,
                        usage={"inputTokens": data.get("prompt_eval_count"),
                               "outputTokens": data.get("eval_count")},
                        elapsed_ms=elapsed, http_status=status)

    def submit_batch(self, *_args, **_kwargs) -> str:
        """Always raises: Ollama has no batch API, and a silent sync fallback would misbill."""
        raise BatchUnsupported("ollama is sync only -- use --mode sync")

    def batch_status(self, handle: str) -> str:
        """Always raises -- see submit_batch."""
        raise BatchUnsupported("ollama is sync only")

    def fetch_batch(self, handle: str) -> tuple[str, dict]:
        """Always raises -- see submit_batch."""
        raise BatchUnsupported("ollama is sync only")
