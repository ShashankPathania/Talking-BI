"""Dataset preprocessing and profiling helpers."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


class DataPreparationService:
    ABBREVIATION_MAP = {
        "cat": "category",
        "qty": "quantity",
        "prod": "product",
        "cust": "customer",
        "amt": "amount",
        "rev": "revenue",
    }

    def prepare(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        prepared = frame.copy()
        column_labels: dict[str, str] = {}
        column_aliases: dict[str, str] = {}
        renamed_columns: dict[str, str] = {}
        seen: set[str] = set()

        for index, column in enumerate(prepared.columns):
            canonical = self._canonicalize_column(str(column))
            if canonical in seen:
                canonical = f"{canonical}_{index + 1}"
            seen.add(canonical)
            renamed_columns[column] = canonical
            column_labels[canonical] = str(column)

            variations = {
                str(column),
                str(column).lower(),
                str(column).replace("_", " "),
                str(column).replace(" ", "_"),
                canonical,
                canonical.replace("_", " "),
                canonical.replace("_", ""),
            }
            variations.update(self._expanded_variations(str(column)))
            variations.update(self._expanded_variations(canonical))
            for variation in variations:
                alias_key = self._canonicalize_column(str(variation))
                if alias_key:
                    column_aliases[alias_key] = canonical

        prepared = prepared.rename(columns=renamed_columns)

        numeric_columns: list[str] = []
        datetime_columns: list[str] = []
        missing_counts = prepared.isna().sum().to_dict()
        duplicate_rows = int(prepared.duplicated().sum())

        for column in prepared.columns:
            series = prepared[column]
            if self._looks_datetime(series):
                converted = pd.to_datetime(series, errors="coerce")
                if converted.notna().sum() >= max(2, int(len(series) * 0.5)):
                    prepared[column] = converted
                    datetime_columns.append(column)
                    continue

            if series.dtype == object:
                numeric_candidate = pd.to_numeric(series, errors="coerce")
                if numeric_candidate.notna().sum() >= max(2, int(len(series) * 0.6)):
                    prepared[column] = numeric_candidate

            if pd.api.types.is_numeric_dtype(prepared[column]):
                numeric_columns.append(column)

        outliers: dict[str, int] = {}
        for column in numeric_columns:
            series = prepared[column].dropna()
            if len(series) < 4:
                outliers[column] = 0
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                outliers[column] = 0
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outliers[column] = int(((series < lower) | (series > upper)).sum())

        profile = {
            "column_labels": column_labels,
            "column_aliases": column_aliases,
            "numeric_columns": numeric_columns,
            "datetime_columns": datetime_columns,
            "missing_counts": {str(key): int(value) for key, value in missing_counts.items()},
            "duplicate_rows": duplicate_rows,
            "outlier_counts": outliers,
        }
        return prepared, profile

    @staticmethod
    def _canonicalize_column(name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
        return normalized or "column"

    @staticmethod
    def _looks_datetime(series: pd.Series) -> bool:
        name = str(series.name).lower()
        if "date" in name or "time" in name:
            return True
        if not len(series):
            return False
        sample = series.dropna().astype(str).head(5)
        return any("-" in value or "/" in value for value in sample)

    @classmethod
    def _expanded_variations(cls, name: str) -> set[str]:
        tokens = re.split(r"[^a-zA-Z0-9]+", name.lower())
        if not tokens:
            return set()
        expanded = [
            cls.ABBREVIATION_MAP.get(token, token)
            for token in tokens
            if token
        ]
        if not expanded:
            return set()
        joined_space = " ".join(expanded)
        joined_underscore = "_".join(expanded)
        joined_plain = "".join(expanded)
        return {joined_space, joined_underscore, joined_plain}
