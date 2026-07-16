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
STRUCTURED_REASONING_FALLBACK_TAGS = {"reviewer", "expel_reviewer", "self_eval"}


def _is_content_filter_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return "81011" in s or "sensitive information" in s or "content_filter" in s


def _perturb_messages(messages: list[Message], attempt: int) -> list[Message]:
    """Benign nonce for content-filter retries: same task, different sampled surface.

    Endpoint moderation (e.g. ModelArts.81011) can flag a borderline output
    repeatedly for the same request; a formatting reminder changes the sample
    without changing the task. The cache key stays bound to the ORIGINAL messages.
    """
    perturbed = [dict(m) for m in messages]
    for m in reversed(perturbed):
        if m.get("role") == "user":
            m["content"] = f"{m['content']}\n\n[retry {attempt}: answer strictly in the requested format]"
            break
    return perturbed


def _effective_response_text(content: str, reasoning: Any, tag: str) -> str:
    if content.strip():
        return content
    if tag in STRUCTURED_REASONING_FALLBACK_TAGS and isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return content


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _with_thinking_control(messages: list[Message], cfg: Config) -> list[Message]:
    if not cfg.disable_thinking:
        return messages
    controlled = [dict(m) for m in messages]
    marker = (
        "\n\n/no_think\n"
        "Do not include hidden or visible chain-of-thought. Return only the requested final format."
    )
    for m in reversed(controlled):
        if m.get("role") == "user":
            if "/no_think" not in m.get("content", ""):
                m["content"] = f"{m['content']}{marker}"
            break
    return controlled


def _extra_body(cfg: Config) -> dict[str, Any]:
    body = dict(cfg.llm_extra_body or {})
    if cfg.disable_thinking:
        # Several OpenAI-compatible Qwen endpoints honor this extra body field;
        # the /no_think prompt marker above is the preregistered fallback.
        body.setdefault("enable_thinking", False)
    return body


@dataclass
class LLMStats:
    network_calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    content_filter_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_prompt_tokens: int = 0
    cached_completion_tokens: int = 0
    cached_total_tokens: int = 0
    retry_count: int = 0
    network_latency_sec: list[float] = field(default_factory=list)
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
            "retry_count": self.retry_count,
            "content_filter_hits": self.content_filter_hits,
            "latency_p50_sec": _percentile(self.network_latency_sec, 0.50),
            "latency_p95_sec": _percentile(self.network_latency_sec, 0.95),
            "latency_n": len(self.network_latency_sec),
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

    def _key(
        self,
        *,
        model: str,
        messages: list[Message],
        temp: float,
        max_tokens: int | None,
        cache_salt: str = "",
    ) -> str:
        payload = {
            "base_url": self.cfg.base_url,
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
        }
        extra_body = _extra_body(self.cfg)
        if extra_body:
            payload["extra_body"] = extra_body
        if cache_salt:
            # Execution-context salt (round/task/agent/step). Without it, identical prompts
            # across rounds or conditions replay one cached sample and fake the dynamics.
            payload["salt"] = cache_salt
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
        cache_salt: str = "",
    ) -> str:
        model_name = model or self.cfg.model
        base_messages = _with_thinking_control(messages, self.cfg)
        key = self._key(model=model_name, messages=base_messages, temp=temp, max_tokens=max_tokens, cache_salt=cache_salt)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cache_file = self.cache_dir / f"{key}.json"
            cache_enabled = self.cfg.cache_policy != "off"
            if cache_enabled and cache_file.exists():
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
                content_filtered = False
                extra_body = _extra_body(self.cfg)
                for attempt in range(1, self.cfg.max_retries + 1):
                    request_messages = _perturb_messages(base_messages, attempt) if content_filtered else base_messages
                    try:
                        await self._throttle()
                        request_started = time.monotonic()
                        kwargs: dict[str, Any] = {
                            "model": model_name,
                            "messages": request_messages,
                            "temperature": temp,
                            "max_tokens": max_tokens,
                        }
                        if extra_body:
                            kwargs["extra_body"] = extra_body
                        response = await self.client.chat.completions.create(**kwargs)
                        latency_sec = time.monotonic() - request_started
                        content = response.choices[0].message.content or ""
                        reasoning = getattr(response.choices[0].message, "reasoning_content", None)
                        usage = response.usage.model_dump() if response.usage else {}
                        record = {
                            "key": key,
                            "tag": tag,
                            "request": {
                                "model": model_name,
                                "messages": base_messages,
                                "temperature": temp,
                                "max_tokens": max_tokens,
                                "extra_body": extra_body,
                            },
                            "response": {
                                "content": content,
                                "reasoning_content": reasoning,
                            },
                            "usage": usage,
                            "latency_sec": latency_sec,
                            "attempts": attempt,
                            "ts": time.time(),
                            "cached": False,
                        }
                        if cache_enabled:
                            tmp_file = cache_file.with_suffix(".tmp")
                            tmp_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                            tmp_file.replace(cache_file)
                        self.stats.network_calls += 1
                        self.stats.add_usage(usage)
                        self.stats.network_latency_sec.append(latency_sec)
                        self.stats.call_records.append(
                            {
                                "key": key,
                                "tag": tag,
                                "cached": False,
                                "usage": usage,
                                "latency_sec": latency_sec,
                                "attempts": attempt,
                            }
                        )
                        return _effective_response_text(content, reasoning, tag)
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        self.stats.errors += 1
                        if attempt < self.cfg.max_retries:
                            self.stats.retry_count += 1
                        if _is_content_filter_error(exc):
                            self.stats.content_filter_hits += 1
                            content_filtered = True
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
