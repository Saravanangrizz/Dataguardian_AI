from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import router

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://dataguardian-ai-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/api/system-info")
async def system_info():
    from app.ai_provider import get_ai_provider, get_ai_fallback_reason
    provider = get_ai_provider()
    info = {
        "datahub_mode": settings.datahub_mode,
        "ai_provider_requested": settings.ai_provider,
        "ai_provider": provider.name,
        "write_enabled": settings.datahub_write_enabled or settings.datahub_mode == "mock",
    }
    if provider.name != settings.ai_provider:
        info["ai_provider_fallback_reason"] = get_ai_fallback_reason()
    return info
