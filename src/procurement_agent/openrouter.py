"""Small OpenRouter adapter; no framework or runtime dependencies required."""

import json
import os
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenRouterError(RuntimeError):
    """A configuration, transport, or response error safe to display."""


@dataclass(frozen=True)
class OpenRouterClient:
    api_key: str = field(repr=False)
    model: str
    timeout: float = 60

    @classmethod
    def from_env(cls):
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        model = os.environ.get("OPENROUTER_MODEL", "").strip()
        if not key:
            raise OpenRouterError("Set OPENROUTER_API_KEY before running the agent.")
        if not model:
            raise OpenRouterError("Set OPENROUTER_MODEL to an OpenRouter model ID.")
        return cls(api_key=key, model=model)

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int = 1500) -> str:
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": False,
            }).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Procurement Agent",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # Do not echo provider bodies or request headers: they may contain secrets.
            hint = {
                401: "Check your OpenRouter API key.",
                402: "Check your OpenRouter credits.",
                403: "Check account permissions and network policy.",
                429: "Rate limited; retry later.",
            }.get(exc.code, "Check model availability or retry later.")
            raise OpenRouterError(f"OpenRouter HTTP {exc.code}. {hint}") from None
        except (URLError, TimeoutError, OSError):
            raise OpenRouterError("OpenRouter connection failed; check network access or retry later.") from None
        except (ValueError, UnicodeError):
            raise OpenRouterError("OpenRouter returned invalid JSON.") from None
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop":
                raise OpenRouterError("OpenRouter response did not finish normally; no complete result available.")
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise OpenRouterError("OpenRouter returned no usable text completion.") from None
