"""
Central configuration for DataGuardian AI.

Everything here is read from environment variables so the same codebase
runs in three modes without code changes:

  1. DEMO mode   - DATAHUB_MODE=mock,  no AI key set   -> deterministic
                   heuristic reasoning, zero external dependencies.
                   This is what judges can run in under a minute.
  2. AI mode     - DATAHUB_MODE=mock,  AI key set       -> mock DataHub
                   data, real LLM reasoning. Good for iterating on
                   agent prompts without a live DataHub instance.
  3. Live mode   - DATAHUB_MODE=live,  AI key set       -> real DataHub
                   instance + real LLM reasoning. The full hackathon
                   submission mode.

IMPORTANT: this reads backend/.env explicitly via pydantic-settings'
`env_file` (resolved to an absolute path, so it works regardless of the
directory `uvicorn` is launched from). An earlier version of this file
used bare `os.getenv(...)` as field defaults with no env_file loading at
all -- which meant backend/.env was silently never read unless you ran
uvicorn with --env-file or exported the variables yourself. If you're
debugging a "my .env changes aren't taking effect" issue, this is almost
certainly why -- confirmed by reproducing it: plain `os.getenv()` field
defaults never see a .env file's contents on their own.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parent is backend/app, parent.parent is backend/
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- DataHub -----------------------------------------------------
    datahub_mode: str = "mock"  # mock | live
    datahub_gms_url: str = "http://localhost:8080"
    datahub_token: str = ""
    datahub_write_enabled: bool = False

    # --- AI provider ---------------------------------------------------
    ai_provider: str = "heuristic"  # heuristic | anthropic | openai | gemini
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ai_model: str = ""  # optional override per-provider

    # --- App -----------------------------------------------------------
    cors_origins: list[str] = ["*"]
    app_name: str = "DataGuardian AI"


@lru_cache
def get_settings() -> Settings:
    return Settings()
