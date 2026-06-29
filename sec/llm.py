from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from .config import Config


Message = dict[str, str]
STRUCTURED_REASONING_FALLBACK_TAGS = {"reviewer", "self_eval"}


def _effective_response_text(content: str, reasoning: Any, tag: str) -> str:
    if content.strip():
        return content
    if tag in STRUCTURED_REASONING_FALLBACK_TAGS and isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return content


@dataclass
class LLMStats:
    network_calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_prompt_tokens: int = 0
    cached_completion_tokens: int = 0
    cached_total_tokens: int = 0
    call_records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return self.network_calls + self.cache_hits

    @property
    def cache_hit_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.cache_hits / self.total_calls

    def add_usage(self, usage: dict[str, Any]) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.total_tokens += int(usage.get("total_tokens") or 0)

    def add_cached_usage(self, usage: dict[str, Any]) -> None:
        self.cached_prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.cached_completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cached_total_tokens += int(usage.get("total_tokens") or 0)

    def public_summary(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "network_calls": self.network_calls,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": self.cache_hit_rate,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "cached_completion_tokens": self.cached_completion_tokens,
            "cached_total_tokens": self.cached_total_tokens,
            "trace_total_tokens": self.total_tokens + self.cached_total_tokens,
            "errors": self.errors,
        }


class LLMClient:
    def __init__(self, cfg: Config) -> None:
        api_key = os.environ.get(cfg.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var {cfg.api_key_env}.")
        self.cfg = cfg
        self.client = AsyncOpenAI(api_key=api_key, base_url=cfg.base_url, timeout=cfg.request_timeout_sec)
        self.sem = asyncio.Semaphore(cfg.concurrency)
        self.cache_dir = cfg.cache_path()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats = LLMStats()
        self._locks: dict[str, asyncio.Lock] = {}
        self._rate_lock = asyncio.Lock()
        self._last_network_ts = 0.0

    def _key(self, *, model: str, messages: list[Message], temp: float, max_tokens: int | None) -> str:
        payload = {
            "base_url": self.cfg.base_url,
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def chat(
        self,
        messages: list[Message],
        *,
        temp: float = 0.0,
        model: str | None = None,
        max_tokens: int | None = None,
        tag: str = "",
    ) -> str:
        model_name = model or self.cfg.model
        key = self._key(model=model_name, messages=messages, temp=temp, max_tokens=max_tokens)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                record = json.loads(cache_file.read_text(encoding="utf-8"))
                self.stats.cache_hits += 1
                self.stats.add_cached_usage(record.get("usage", {}))
                self.stats.call_records.append({"key": key, "tag": tag, "cached": True})
                response = record.get("response", {})
                return _effective_response_text(
                    str(response.get("content") or ""),
                    response.get("reasoning_content"),
                    tag,
                )

            async with self.sem:
                delay = 1.0
                last_error: Exception | None = None
                for attempt in range(1, self.cfg.max_retries + 1):
                    try:
                        await self._throttle()
                        response = await self.client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temp,
                            max_tokens=max_tokens,
                        )
                        content = response.choices[0].message.content or ""
                        reasoning = getattr(response.choices[0].message, "reasoning_content", None)
                        usage = response.usage.model_dump() if response.usage else {}
                        record = {
                            "key": key,
                            "tag": tag,
                            "request": {
                                "model": model_name,
                                "messages": messages,
                                "temperature": temp,
                                "max_tokens": max_tokens,
                            },
                            "response": {
                                "content": content,
                                "reasoning_content": reasoning,
                            },
                            "usage": usage,
                            "ts": time.time(),
                            "cached": False,
                        }
                        tmp_file = cache_file.with_suffix(".tmp")
                        tmp_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                        tmp_file.replace(cache_file)
                        self.stats.network_calls += 1
                        self.stats.add_usage(usage)
                        self.stats.call_records.append({"key": key, "tag": tag, "cached": False, "usage": usage})
                        return _effective_response_text(content, reasoning, tag)
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        self.stats.errors += 1
                        if attempt >= self.cfg.max_retries:
                            raise RuntimeError(f"LLM call failed after {attempt} attempts: {exc}") from exc
                        wait = max(delay, 65.0) if "rate limit" in str(exc).lower() or "too many requests" in str(exc).lower() else delay
                        await asyncio.sleep(wait)
                        delay = min(delay * 2, 20.0)
                raise RuntimeError(f"LLM call failed: {last_error}")

    async def _throttle(self) -> None:
        if self.cfg.rate_limit_per_min <= 0:
            return
        interval = 60.0 / self.cfg.rate_limit_per_min
        async with self._rate_lock:
            now = time.monotonic()
            wait = interval - (now - self._last_network_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_network_ts = time.monotonic()
