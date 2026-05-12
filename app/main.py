"""FastAPI entrypoint for Talking BI v2."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.frontend import router as frontend_router
from app.api.routes.query import router as query_router
from app.api.routes.session import router as session_router
from app.api.routes.system import router as system_router
from app.api.routes.upload import router as upload_router

app = FastAPI(title="Talking BI v2", version="0.1.0")
app.include_router(frontend_router)
app.include_router(query_router, prefix="/v1")
app.include_router(upload_router, prefix="/v1")
app.include_router(session_router, prefix="/v1")
app.include_router(system_router, prefix="/v1")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "web"),
    name="static",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
