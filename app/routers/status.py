from fastapi import APIRouter

from app.config import settings
from app.services.cache import cache
from app.services.stacks_api import stacks_client

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
async def status():
    result = await stacks_client.check_status()
    result["cache"] = cache.stats()
    result["ai_service"] = {
        "configured": bool(settings.anthropic_api_key),
        "note": "ANTHROPIC_API_KEY is set" if settings.anthropic_api_key else "ANTHROPIC_API_KEY is not set - AI features will return an error",
    }
    result["environment"] = {
        "stacks_api_base_configured": bool(settings.stacks_api_base),
        "stacks_api_key_configured": bool(settings.stacks_api_key),
        "cors_origins_configured": bool(settings.cors_origins),
    }
    result["backend_status"] = "running"
    return result
