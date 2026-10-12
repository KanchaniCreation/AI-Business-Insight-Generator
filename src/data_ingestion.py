"""STEP 3a - Data ingestion: safely read an Excel/CSV file into a DataFrame.

Real users upload empty files, renamed .txt files, corrupted Excel sheets...
This module turns every one of those problems into a clear DataValidationError
instead of an ugly traceback.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import BinaryIO, Union

import pandas as pd

from src.exceptions import DataValidationError

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
MAX_FILE_MB = 100


def load_dataset(source: Union[str, Path, BinaryIO], filename: str | None = None) -> pd.DataFrame:
    """Load a CSV/XLSX from a path or an uploaded file object (e.g. Streamlit's uploader)."""
    # 1) get raw bytes + a file name to detect the format
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise DataValidationError(f"File not found: {path}")
        filename = filename or path.name
        raw = path.read_bytes()
    else:
        filename = filename or getattr(source, "name", "")
        raw = source.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")

    # 2) basic checks
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DataValidationError(f"Unsupported file type '{ext or 'unknown'}'. Please upload a .csv or .xlsx file.")
    if not raw or not raw.strip():
        raise DataValidationError("The uploaded file is empty.")
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise DataValidationError(f"File is larger than {MAX_FILE_MB} MB. Please upload a smaller file.")

    # 3) parse
    try:
        if ext == ".csv":
            try:
                df = pd.read_csv(io.BytesIO(raw))
            except UnicodeDecodeError:  # Excel-exported CSVs are often latin-1
                df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
        else:
            df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")  # first sheet
    except pd.errors.EmptyDataError as exc:
        raise DataValidationError("The file has no readable data.") from exc
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as exc:
        raise DataValidationError(
            "Could not read the file. It may be corrupted or not a valid Excel/CSV file."
        ) from exc
    except pd.errors.ParserError as exc:
        raise DataValidationError("The CSV file is malformed and could not be parsed.") from exc

    if df.empty or df.dropna(how="all").empty:
        raise DataValidationError("The file contains headers but no data rows.")
    return df
