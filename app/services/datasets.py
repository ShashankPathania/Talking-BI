"""Dataset registration and loading service with DuckDB & SQLite persistence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile

from app.core.config import settings
from app.core.dataset import DatasetProfile
from app.core.state import DataLayer, QueryState, utc_now
from app.services.data_preparation import DataPreparationService
from app.services.db_connectors import DatabaseConnector
from app.services.data.duckdb_store import DuckDBStore
from app.services.persistence.metadata_db import MetadataStore


class DatasetService:
    def __init__(
        self,
        dataset_root: Path | None = None,
        db_connector: DatabaseConnector | None = None,
    ) -> None:
        self.dataset_root = dataset_root or settings.dataset_store_path
        self.dataset_root.mkdir(parents=True, exist_ok=True)
        self.db_connector = db_connector or DatabaseConnector()
        self.preparation_service = DataPreparationService()
        
        # New v3.5 Stores
        self.duckdb = DuckDBStore(self.dataset_root / "talking_bi.duckdb")
        self.metadata = MetadataStore(self.dataset_root / "metadata.db")

    async def save_upload(
        self,
        file: UploadFile,
        dataset_name: str | None = None,
    ) -> DatasetProfile:
        filename = file.filename or "dataset"
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            raise ValueError("Only CSV and Excel uploads are supported.")

        dataset_id = str(uuid4())
        target_path = self.dataset_root / f"{dataset_id}{suffix}"
        content = await file.read()
        target_path.write_bytes(content)

        # 1. Load and Prepare Data
        frame = self.load_dataframe_from_path(target_path, suffix)
        prepared_frame, preparation_profile = self.preparation_service.prepare(frame)
        
        # 2. Strict Namespacing for Table Name
        clean_name = self._derive_table_name(dataset_name or Path(filename).stem, dataset_id)
        # Force format: dataset_<id_prefix>_<original_name>
        namespaced_table = f"dataset_{dataset_id.split('-')[0]}_{clean_name}"
        
        # 3. Ingest to DuckDB (Disk-backed analytical sink)
        self.duckdb.ingest_dataframe(namespaced_table, prepared_frame)
        
        # Inject standard sample preview
        sample_rows = [
            {k: str(v) if pd.notnull(v) else None for k, v in row.items()}
            for row in prepared_frame.head(3).to_dict(orient="records")
        ]
        preparation_profile["data_preview"] = sample_rows
        
        profile = DatasetProfile(
            dataset_id=dataset_id,
            name=dataset_name or Path(filename).stem,
            source_type="csv" if suffix == ".csv" else "excel",
            file_path=str(target_path),
            table_name=namespaced_table,
            schema={column: str(dtype) for column, dtype in prepared_frame.dtypes.items()},
            column_labels=preparation_profile["column_labels"],
            column_aliases=preparation_profile["column_aliases"],
            preprocessing_profile=preparation_profile,
            row_count=len(prepared_frame),
            updated_at=utc_now(),
        )
        
        # 4. Save Profile to SQLite Metadata
        self.metadata.save_dataset(profile)
        return profile

    def get_profile(self, dataset_id: str) -> DatasetProfile | None:
        return self.metadata.get_dataset(dataset_id)

    def list_profiles(self) -> list[DatasetProfile]:
        return self.metadata.list_datasets()

    def register_database(
        self,
        name: str,
        database_url: str,
        table_name: str,
        dialect: str = "sqlite",
    ) -> DatasetProfile:
        snapshot = self.db_connector.inspect_table(dialect, database_url, table_name)
        dataset_id = str(uuid4())
        profile = DatasetProfile(
            dataset_id=dataset_id,
            name=name,
            source_type="database",
            dialect=dialect,  # type: ignore[arg-type]
            table_name=table_name,
            database_url=database_url,
            schema=snapshot.schema_map,
            preprocessing_profile={"data_preview": snapshot.sample_rows},
            row_count=snapshot.row_count,
            updated_at=utc_now(),
        )
        self.metadata.save_dataset(profile)
        return profile

    def load_dataframe(self, dataset_id: str) -> pd.DataFrame:
        profile = self.get_profile(dataset_id)
        if profile is None:
            raise ValueError(f"Dataset '{dataset_id}' was not found.")
            
        # Optimization: Try loading from DuckDB first if it's a file-backed dataset
        if profile.source_type != "database" and profile.table_name:
            if self.duckdb.table_exists(profile.table_name):
                return self.duckdb.execute_query(f"SELECT * FROM \"{profile.table_name}\"")

        if profile.source_type == "database":
            if profile.database_url is None or profile.table_name is None or profile.dialect is None:
                raise ValueError(f"Dataset '{dataset_id}' is missing database metadata.")
            return self.load_database_table(profile.dialect, profile.database_url, profile.table_name)
            
        if profile.file_path is None:
            raise ValueError(f"Dataset '{dataset_id}' is missing file metadata.")
            
        frame = self.load_dataframe_from_path(Path(profile.file_path))
        prepared_frame, _ = self.preparation_service.prepare(frame)
        return prepared_frame

    def attach_to_state(self, state: QueryState, dataset_id: str) -> QueryState:
        profile = self.get_profile(dataset_id)
        if profile is None:
            raise ValueError(f"Dataset '{dataset_id}' was not found.")
        state.data = DataLayer(
            source_type=profile.source_type,
            source_id=profile.dataset_id,
            table_name=profile.table_name,
            schema=profile.schema_map,
            column_labels=profile.column_labels,
            column_aliases=profile.column_aliases,
            preprocessing_profile=profile.preprocessing_profile,
        )
        # Context Binding for v3.5 Agent
        state.data.active_dataset_id = dataset_id
        return state

    @staticmethod
    def load_dataframe_from_path(path: Path, suffix: str | None = None) -> pd.DataFrame:
        file_suffix = (suffix or path.suffix).lower()
        if file_suffix == ".csv":
            return pd.read_csv(path)
        return pd.read_excel(path)

    def load_database_table(self, dialect: str, database_url: str, table_name: str) -> pd.DataFrame:
        return self.db_connector.load_table(dialect, database_url, table_name)

    @staticmethod
    def _derive_table_name(name: str, dataset_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
        if not normalized:
            normalized = f"dataset_{dataset_id.replace('-', '_')}"
        if normalized[0].isdigit():
            normalized = f"dataset_{normalized}"
        return normalized
