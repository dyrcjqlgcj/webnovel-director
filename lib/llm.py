"""Unified LLM calling for webnovel-director.

Supports multiple backends through a single `call_llm()` interface.
Configure via config.yaml, environment variables, or the `--model` CLI flag.

Strategy (tried in order, each with retry):
  1. Direct API — DeepSeek / OpenAI-compatible endpoints (fastest)
  2. OpenClaw gateway — fallback via `openclaw agent --local`
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("wd.llm")

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]

# Provider registry — extend by adding entries here or in config.yaml
PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "api": "openai-completions",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "api": "openai-completions",
    },
    "gptsapi": {
        "base_url": "https://api.gptsapi.net/v1/chat/completions",
        "api_key_env": "GPTSAPI_API_KEY",
        "default_model": "gpt-5.5",
        "api": "openai-completions",
    },
}


def _load_config() -> dict:
    """Load optional config.yaml from the skill root."""
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                if cfg.get("providers"):
                    PROVIDERS.update(cfg["providers"])
                return cfg
        except Exception:
            pass
    return {}


def _call_openai_compatible(prompt: str, model: str = "", provider: str = "deepseek",
                            timeout: int = 120, max_tokens: int = 4000,
                            temperature: float = 0.7) -> tuple[str, bool]:
    """Call an OpenAI-compatible chat completions endpoint."""
    pconfig = PROVIDERS.get(provider, PROVIDERS["deepseek"])
    api_key = os.environ.get(pconfig.get("api_key_env", ""), "")
    if not api_key:
        return "", False

    actual_model = model or pconfig.get("default_model", "deepseek-chat")
    base_url = pconfig.get("base_url", "")

    data = json.dumps({
        "model": actual_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    req = urllib.request.Request(
        base_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
            log.debug(f"{provider} API attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    return "", False


def _try_openclaw_gateway(prompt: str, model: str = "", timeout: int = 120) -> tuple[str, bool]:
    """Try calling LLM via openclaw agent gateway (fallback)."""
    cmd = ["openclaw", "agent", "--json", "--local", "--message", prompt]
    if model:
        cmd.extend(["--model", model])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            reply = data.get("reply") or data.get("content") or ""
            if reply:
                return reply, True
    except (subprocess.TimeoutExpired, Exception):
        pass
    return "", False


def call_llm(prompt: str, model: str = "", provider: str = "deepseek",
             timeout: int = 120, max_tokens: int = 4000,
             temperature: float = 0.7) -> str:
    """Call LLM with retry and fallback.

    Args:
        prompt: The prompt to send.
        model: Override model name (uses provider default if empty).
        provider: Provider key from PROVIDERS dict (default: deepseek).
        timeout: Request timeout in seconds.
        max_tokens: Max tokens in response.
        temperature: Sampling temperature.

    Returns:
        Response text, or empty string on failure.
    """
    _load_config()  # Refresh config on each call (lightweight)

    strategies = [
        ("api_direct", lambda: _call_openai_compatible(
            prompt, model, provider, timeout, max_tokens, temperature)),
        ("openclaw_gateway", lambda: _try_openclaw_gateway(prompt, model, timeout)),
    ]

    for strategy_name, strategy_fn in strategies:
        reply, ok = strategy_fn()
        if ok and reply:
            log.info(f"LLM OK via {strategy_name}")
            return reply
        elif reply:
            log.debug(f"{strategy_name} returned empty response, trying next...")

    log.warning("LLM 调用失败（已重试全部策略）")
    return ""


def call_llm_writing(prompt: str, model: str = "", provider: str = "deepseek",
                     timeout: int = 300, max_tokens: int = 8000,
                     temperature: float = 0.8) -> str:
    """Call LLM for writing tasks (higher max_tokens, longer timeout)."""
    return call_llm(prompt, model, provider, timeout, max_tokens, temperature)


def call_llm_review(prompt: str, model: str = "", provider: str = "deepseek",
                    timeout: int = 180, max_tokens: int = 4000,
                    temperature: float = 0.3) -> str:
    """Call LLM for review tasks (lower temperature for consistency)."""
    return call_llm(prompt, model, provider, timeout, max_tokens, temperature)
