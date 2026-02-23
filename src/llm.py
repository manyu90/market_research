from __future__ import annotations

import asyncio
import json
import logging

import httpx

from src.settings import settings

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_concurrency)
    return _semaphore


async def llm_extract(
    prompt: str,
    *,
    system: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    """Call an OpenRouter chat-completion endpoint and return the response text."""
    config = settings.load_llm_config()
    defaults = config.get("defaults", {})
    base_url = config["base_url"]
    model = config["model"]

    temp = temperature if temperature is not None else defaults.get("temperature", 0.2)
    tokens = max_tokens if max_tokens is not None else defaults.get("max_tokens", 4096)
    retries = defaults.get("retries", 3)
    backoff = defaults.get("retry_backoff_seconds", 5)
    timeout = defaults.get("timeout_seconds", 60)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temp,
        "max_tokens": tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    sem = _get_semaphore()

    async with sem:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=body,
                    )
                    if resp.status_code >= 500:
                        resp.raise_for_status()
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < retries:
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM request failed (attempt %d/%d): %s — retrying in %ds",
                        attempt,
                        retries,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "LLM request failed after %d attempts: %s",
                        retries,
                        exc,
                    )

        raise RuntimeError(
            f"LLM request failed after {retries} attempts"
        ) from last_exc
