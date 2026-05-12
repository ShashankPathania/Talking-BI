"""System status endpoints."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/system/status")
async def system_status() -> dict:
    return {
        "llm_enabled": settings.llm_enabled,
        "llm_mode": settings.llm_mode,
        "groq_configured": bool(settings.groq_api_key),
        "openrouter_configured": bool(settings.openrouter_api_key),
        "groq_model": settings.groq_heavy_model,
        "openrouter_model": settings.openrouter_light_model,
    }
