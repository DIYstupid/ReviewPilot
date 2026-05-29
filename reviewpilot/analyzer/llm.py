from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from reviewpilot.config import get_settings


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMRequest:
    messages: list[ChatMessage]
    model: str
    temperature: float = 0.2
    response_format: dict[str, str] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    cached: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


class LLMConfigurationError(RuntimeError):
    """Raised when the selected provider is missing configuration."""


class ChatCompletionClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider: str,
        timeout: float = 60.0,
        cache_dir: str | Path | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError(f"{provider} API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None

    async def complete(self, request: LLMRequest, use_cache: bool = True) -> LLMResponse:
        cache_key = request_cache_key(self.provider, request)
        if use_cache:
            cached = self._read_cache(cache_key)
            if cached is not None:
                return LLMResponse(
                    content=cached["content"],
                    model=cached["model"],
                    cached=True,
                    raw=cached.get("raw", {}),
                )

        import httpx

        payload = _request_payload(request)
        data: dict[str, Any] | None = None
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code >= 400:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                        await asyncio.sleep(min(1.0 * (2 ** attempt), 30.0))
                        continue
                    response.raise_for_status()
                data = response.json()
                break
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in {429, 500, 502, 503, 504} or attempt >= 3:
                    raise
                await asyncio.sleep(min(1.0 * (2 ** attempt), 30.0))
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt >= 3:
                    raise
                await asyncio.sleep(min(1.0 * (2 ** attempt), 30.0))
        if data is None and last_exc is not None:
            raise last_exc
        if data is None:
            raise RuntimeError("LLM request failed after retries")

        content = _extract_content(data)
        llm_response = LLMResponse(content=content, model=request.model, raw=data)
        if use_cache:
            self._write_cache(cache_key, llm_response)
        return llm_response

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / self.provider / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, key: str, response: LLMResponse) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / self.provider / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "content": response.content,
                    "model": response.model,
                    "raw": response.raw,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def create_deepseek_client() -> ChatCompletionClient:
    settings = get_settings()
    return ChatCompletionClient(
        api_key=settings.deepseek_api_key or "",
        base_url=settings.deepseek_base_url,
        provider="deepseek",
        cache_dir=settings.cache_dir,
    )


def create_qwen_client() -> ChatCompletionClient:
    settings = get_settings()
    return ChatCompletionClient(
        api_key=settings.qwen_api_key or "",
        base_url=settings.qwen_base_url or "",
        provider="qwen",
        cache_dir=settings.cache_dir,
    )


def request_cache_key(provider: str, request: LLMRequest) -> str:
    payload = {
        "provider": provider,
        "request": {
            "messages": [asdict(message) for message in request.messages],
            "model": request.model,
            "temperature": request.temperature,
            "response_format": request.response_format,
            "metadata": request.metadata,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _request_payload(request: LLMRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [asdict(message) for message in request.messages],
        "temperature": request.temperature,
    }
    if request.response_format:
        payload["response_format"] = request.response_format
    return payload


def _extract_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response did not contain choices[0].message.content") from exc
    if not isinstance(content, str):
        raise ValueError("LLM response content must be a string")
    return content
