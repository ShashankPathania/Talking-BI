"""Browser UI routes for the Talking BI MVP."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["frontend"])
WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


@router.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")
