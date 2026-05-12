"""Dataset upload and registration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas.dataset import (
    DatabaseRegistrationRequest,
    DatasetListResponse,
    UploadResponse,
)
from app.services.datasets import DatasetService

router = APIRouter(tags=["datasets"])
service = DatasetService()


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets() -> DatasetListResponse:
    return DatasetListResponse(datasets=service.list_profiles())


@router.post("/datasets/upload", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile = File(...),
    dataset_name: str | None = Form(default=None),
) -> UploadResponse:
    try:
        dataset = await service.save_upload(file, dataset_name=dataset_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResponse(dataset=dataset)


@router.post("/datasets/register-database", response_model=UploadResponse)
async def register_database_dataset(
    request: DatabaseRegistrationRequest,
) -> UploadResponse:
    try:
        dataset = service.register_database(
            name=request.name,
            database_url=request.database_url,
            table_name=request.table_name,
            dialect=request.dialect,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResponse(dataset=dataset)
