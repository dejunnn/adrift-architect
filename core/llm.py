"""Provider-agnostic LLM vocabulary: settings, the exchange record, errors and reply parsing."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = ("anthropic", "openai", "groq", "openrouter", "gemini", "ollama")

#: Providers whose `--mode batch` works; the others raise rather than silently running sync.
BATCH_PROVIDERS = ("anthropic", "openai")

SCHEMA_NAME = "adrift_response"

#: Batch states, in Anthropic's vocabulary. OpenAI's "completed" is normalised to "ended".
DONE = frozenset({"ended", "completed"})
FAILED = frozenset({"failed", "expired", "cancelled", "canceling", "cancelling"})


@dataclass
class Exchange:
    """One request/response pair: the exact JSON sent and received, plus what the run record needs."""

    text: str
    request: dict
    response: dict
    usage: dict                 # normalised: inputTokens / outputTokens
    elapsed_ms: int
    http_status: int | None = None


class LlmError(RuntimeError):
    """The provider could not be reached or refused its own answer; `completion` keeps any text it produced."""

    def __init__(self, *args, completion: str = ""):
        super().__init__(*args)
        self.completion = completion


def rejected_completion(error: BaseException) -> str:
    """The model's answer out of a provider's rejection, or "" when it produced none."""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        for key in ("failed_generation", "generation", "raw_output"):
            value = (inner or {}).get(key)
            if isinstance(value, str) and value.strip():
                return value
    return getattr(error, "completion", "") or ""


class BatchUnsupported(LlmError):
    """This provider has no batch API here. Never silently downgraded to a sync call."""


# ------------------------------------------------------------------------------ settings


def load_dotenv(path: str | Path) -> None:
    """Read KEY=value lines into the environment. Real environment variables win."""
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    """An environment variable the run cannot proceed without."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise LlmError(f"{name} is not set (check .env)")
    return value


def setting(provider: str, name: str) -> str:
    """A per-provider knob, e.g. ADRIFT_ANTHROPIC_EFFORT. Empty when unset."""
    return os.environ.get(f"ADRIFT_{provider.upper()}_{name}", "").strip()


#: Values of ADRIFT_<PROVIDER>_EFFORT that mean "ask for no reasoning at all".
NO_THINKING = ("none", "off")


def effort(provider: str) -> str | None:
    """The reasoning effort to request: a level, "" for the provider's default, or None to omit it entirely."""
    raw = setting(provider, "EFFORT")
    return None if raw.lower() in NO_THINKING else raw


def model_of(provider: str) -> str:
    """The model identifier for a provider, read from the environment and never defaulted."""
    return require_env(f"ADRIFT_{provider.upper()}_MODEL")


def max_tokens() -> int:
    """The output token ceiling sent to every provider."""
    return int(os.environ.get("ADRIFT_MAX_TOKENS", "16000"))


def num_ctx() -> int | None:
    """Ollama's context window, or None to let the model's own Modelfile default stand."""
    value = os.environ.get("ADRIFT_OLLAMA_NUM_CTX")
    return int(value) if value else None


# ------------------------------------------------------------------------------- parsing


def validate(document, schema: dict, path: str = "$") -> None:
    """Check a document against the small subset of JSON Schema our response schemas use."""
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(document, dict):
            raise LlmError(f"{path}: expected an object, got {type(document).__name__}")
        for key in schema.get("required", []):
            if key not in document:
                raise LlmError(f"{path}: missing required key {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(document) - set(properties))
            if unexpected:
                raise LlmError(f"{path}: unexpected key(s) {', '.join(unexpected)}")
        for key, value in document.items():
            if key in properties:
                validate(value, properties[key], f"{path}.{key}")
    elif expected == "array":
        if not isinstance(document, list):
            raise LlmError(f"{path}: expected an array, got {type(document).__name__}")
        if schema.get("items"):
            for index, value in enumerate(document):
                validate(value, schema["items"], f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(document, str):
            raise LlmError(f"{path}: expected a string, got {type(document).__name__}")
        if schema.get("enum") and document not in schema["enum"]:
            raise LlmError(f"{path}: {document!r} is not one of {', '.join(schema['enum'])}")


def parse_json(text: str) -> dict:
    """Parse the completion as one JSON object, strictly -- no code fences or prose tolerated."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as error:
        raise LlmError(f"the completion is not one JSON object -- {error}") from error


#: Everything NOT allowed in an id, as one run to collapse into a single dash.
_UNSAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def safe_id(value: str) -> str:
    """A model-supplied id, made safe to use as a filename."""
    cleaned = _UNSAFE_ID.sub("-", str(value).replace("/", " ").replace("\\", " ")).strip("-.")
    return cleaned or "unnamed"


def sanitise_ids(entries, ) -> list[str]:
    """Rewrite each entry's `id` in place to a unique, filesystem-safe name, returning the changes."""
    changed, seen = [], set()
    for entry in entries:
        original = str(entry.get("id", ""))
        candidate = base = safe_id(original)
        n = 2
        while candidate in seen:
            candidate, n = f"{base}-{n}", n + 1
        seen.add(candidate)
        if candidate != original:
            changed.append(f"{original!r} -> {candidate!r}")
            entry["id"] = candidate
    return changed
