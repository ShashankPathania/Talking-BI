import json
import os
import sys
from pathlib import Path

# Add the app directory to sys.path to import local modules
sys.path.append(os.getcwd())

from app.services.datasets import DatasetService
from app.core.dataset import DatasetProfile

def migrate():
    print("--- Metadata & Data Migration (json -> sqlite/duckdb) ---")
    
    # Use DatasetService to handle the logic
    service = DatasetService()
    
    # Path to old metadata
    old_meta_path = Path("storage/datasets/datasets.json")
    if not old_meta_path.exists():
        print("No old datasets.json found. Skipping migration.")
        return

    try:
        with open(old_meta_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except Exception as e:
        print(f"Error reading datasets.json: {e}")
        return

    print(f"Found {len(old_data)} datasets to migrate.")

    for dataset_id, raw_profile in old_data.items():
        try:
            profile = DatasetProfile.model_validate(raw_profile)
            print(f"Migrating: {profile.name} (ID: {dataset_id})")
            
            # 1. Save metadata
            service.metadata.save_dataset(profile)
            
            # 2. Try to ingest into DuckDB if file exists
            if profile.file_path and os.path.exists(profile.file_path):
                print(f"  Ingesting file to DuckDB: {profile.file_path}")
                try:
                    df = service.load_dataframe_from_path(Path(profile.file_path))
                    service.duckdb.ingest_dataframe(profile.table_name, df)
                    print("  Success: Ingested to DuckDB.")
                except Exception as e:
                    print(f"  Warning: Could not ingest to DuckDB: {e}")
            else:
                print(f"  File not found or not required: {profile.file_path}")

        except Exception as e:
            print(f"Error migrating dataset {dataset_id}: {e}")

    print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
