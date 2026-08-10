"""
One reasoning interface, three possible backends. Agents call
`get_ai_provider().reason(prompt)` and never know which LLM (or no LLM
at all) answered.

- HeuristicProvider: zero dependencies, zero API keys, deterministic.
  This is what runs out of the box so anyone can clone the repo and see
  real findings immediately. It's rule-based, not an LLM -- agents that
  use it are honest about that in the `confidence`/`reasoning_source`
  field they return (see agents/*.py).
- AnthropicProvider / OpenAIProvider / GeminiProvider: thin wrappers,
  selected via AI_PROVIDER env var. Only the selected one needs its
  package installed / key set.
"""
from __future__ import annotations
import hashlib
from functools import lru_cache
from app.config import get_settings


class AIProvider:
    name = "base"

    async def reason(self, system: str, prompt: str) -> str:
        raise NotImplementedError


class HeuristicProvider(AIProvider):
    """No external calls. Used as the zero-setup default and as a
    graceful fallback if a real provider errors (e.g. missing key)."""
    name = "heuristic"

    async def reason(self, system: str, prompt: str) -> str:
        return (
            "Heuristic reasoning (no AI provider configured): findings below "
            "are derived from rule thresholds, not LLM inference. Set "
            "AI_PROVIDER + the matching API key to enable narrative reasoning."
        )


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self):
        import anthropic  # imported lazily so it's optional
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.ai_model or "claude-sonnet-4-6"

    async def reason(self, system: str, prompt: str) -> str:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.ai_model or "gpt-5.6"

    async def reason(self, system: str, prompt: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""


class GeminiProvider(AIProvider):
    """Uses `google-genai`, the current unified SDK. The older
    `google-generativeai` package is fully deprecated by Google (no more
    updates or bug fixes as of this writing) -- confirmed by installing
    it and seeing its own FutureWarning say so. Every shape below was
    checked against the installed `google-genai` package's real pydantic
    field names, not assumed from memory."""

    name = "gemini"

    def __init__(self):
        from google import genai
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.ai_model or "gemini-2.5-flash"

    async def reason(self, system: str, prompt: str) -> str:
        from google.genai import types
        resp = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return resp.text or ""


_last_fallback_reason: dict[str, str] = {}


def get_ai_fallback_reason() -> str | None:
    """None if the configured provider is active as requested; otherwise
    the specific reason it fell back to heuristic (missing package,
    missing key, bad config) -- surfaced in /api/system-info instead of
    only living in server logs."""
    return _last_fallback_reason.get("error")


class ResilientProvider(AIProvider):
    """Wraps a real provider so one flaky call (rate limit, transient
    network blip, quota hit) degrades to heuristic reasoning for just
    that call, instead of throwing a 500 through to the frontend mid-demo.
    `.name` stays the real provider's name so /api/system-info still
    reports what's configured; only the call itself has a safety net."""

    def __init__(self, inner: AIProvider):
        self._inner = inner
        self.name = inner.name

    async def reason(self, system: str, prompt: str) -> str:
        try:
            return await self._inner.reason(system, prompt)
        except Exception as e:
            print(f"[ai_provider] {self._inner.name} call failed, degrading to heuristic for this call: {type(e).__name__}: {e}")
            return await HeuristicProvider().reason(system, prompt)


class CachingProvider(AIProvider):
    """Wraps any provider so an identical (system, prompt) pair only
    calls the real API once per process lifetime, then serves cached
    text on every repeat.

    This is the actual fix for hitting Gemini's free-tier rate limit
    (5 requests/minute, 20/day) almost immediately: /api/findings
    recomputes every finding's narrative from scratch on EVERY request,
    with no memory of having already asked the same question. A single
    dashboard load already fires one AI call per stale dataset and one
    per undocumented dataset (confirmed by counting the call sites in
    agents/reliability.py and agents/governance.py); React's dev-mode
    StrictMode double-invoking the initial fetch doubles that again;
    and a page refresh repeats the whole thing from zero, with no
    reuse of a narrative that hasn't actually changed. Caching by
    content hash means only genuinely new findings ever reach the API,
    so refreshing the dashboard or reopening the same investigation is
    free after the first run -- which also means it's worth loading
    everything once before recording a demo, then recording the replay,
    since nothing after that first pass touches the real API.

    Bounded to `max_entries` with simple oldest-first eviction (plain
    dict preserves insertion order) -- unbounded growth isn't a real
    risk at hackathon scale, but there's no reason not to cap it.
    """

    def __init__(self, inner: AIProvider, max_entries: int = 500):
        self._inner = inner
        self.name = inner.name
        self._cache: dict[str, str] = {}
        self._max_entries = max_entries

    async def reason(self, system: str, prompt: str) -> str:
        key = hashlib.sha256(f"{system}\n---\n{prompt}".encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        result = await self._inner.reason(system, prompt)
        if len(self._cache) >= self._max_entries:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        return result


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "heuristic":
        return HeuristicProvider()
    provider: AIProvider = HeuristicProvider()
    try:
        if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
            provider = ResilientProvider(AnthropicProvider())
        elif settings.ai_provider == "openai" and settings.openai_api_key:
            provider = ResilientProvider(OpenAIProvider())
        elif settings.ai_provider == "gemini" and settings.gemini_api_key:
            provider = ResilientProvider(GeminiProvider())
        else:
            # Provider requested but no matching API key set -- this is a
            # config mistake, not a runtime failure, so say so specifically
            # rather than falling through to the generic except below.
            _last_fallback_reason["error"] = (
                f"AI_PROVIDER={settings.ai_provider} but no matching API key is set "
                f"(check {settings.ai_provider.upper()}_API_KEY in your .env)"
            )
    except Exception as e:
        # Most common real cause: the provider's SDK package isn't
        # installed (requirements.txt intentionally comments these out
        # so people only install the one they use) -- e.g. AI_PROVIDER=
        # gemini requires `pip install google-genai` separately.
        # This used to be a bare `except: pass`, which silently hid
        # exactly this failure mode. Log it loudly instead.
        _last_fallback_reason["error"] = f"{type(e).__name__}: {e}"
        print(f"[ai_provider] Falling back to heuristic -- {_last_fallback_reason['error']}")
    return CachingProvider(provider)
