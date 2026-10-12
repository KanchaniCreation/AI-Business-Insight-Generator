import io

import pytest

from src.data_ingestion import load_dataset
from src.exceptions import DataValidationError


def test_empty_file_is_rejected():
    with pytest.raises(DataValidationError, match="empty"):
        load_dataset(io.BytesIO(b""), filename="x.csv")


def test_wrong_extension_is_rejected():
    with pytest.raises(DataValidationError, match="Unsupported"):
        load_dataset(io.BytesIO(b"a,b\n1,2"), filename="x.txt")


def test_fake_excel_file_is_rejected():
    with pytest.raises(DataValidationError, match="Could not read"):
        load_dataset(io.BytesIO(b"this is not an excel file"), filename="x.xlsx")


def test_header_only_csv_is_rejected():
    with pytest.raises(DataValidationError):
        load_dataset(io.BytesIO(b"Date,Sales\n"), filename="x.csv")


def test_valid_csv_loads():
    df = load_dataset(io.BytesIO(b"Date,Sales\n2026-01-01,10\n"), filename="x.csv")
    assert len(df) == 1


def test_missing_path_is_rejected():
    with pytest.raises(DataValidationError, match="not found"):
        load_dataset("does_not_exist.csv")
