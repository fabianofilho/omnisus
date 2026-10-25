"""Run with pytest in a clean wheel environment, outside the source checkout.

Copy this file, tests/fixtures/dbf and tests/fixtures/blast beside it, set
OMNISUS_NATIVE_SOURCE_ROOT to the checkout, and use an empty pytest.ini. No
main-package imports or DBF builders are needed: these tests consume the
committed synthetic corpus.
"""

from __future__ import annotations

import gc
import importlib.machinery
import importlib.metadata
import importlib.util
import os
import sys
from datetime import date
from pathlib import Path

import omnisus_dbf as dbf
import pyarrow as pa
import pytest
from omnisus_dbf import _native


def test_installed_distribution() -> None:
    source = Path(os.environ["OMNISUS_NATIVE_SOURCE_ROOT"]).resolve()
    environment = Path(sys.prefix).resolve()
    assert sys.prefix != sys.base_prefix, "The wheel gate requires a clean virtual environment"
    for path in (Path.cwd(), Path(__file__), Path(__file__).parent / "dbf"):
        assert not path.resolve().is_relative_to(source), f"Smoke input is inside checkout: {path}"

    distribution = importlib.metadata.distribution("omnisus-dbf")
    assert dbf.API_VERSION == 2
    assert dbf.__version__ == distribution.version
    files = distribution.files
    assert files, "Installed wheel has no file inventory"
    installed_paths = {Path(distribution.locate_file(file)).resolve() for file in files}
    for module in (dbf, _native):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(environment), f"Imported outside the clean environment: {path}"
        assert not path.is_relative_to(source), f"Imported from the checkout: {path}"
        assert path in installed_paths, f"Module is not owned by the installed wheel: {path}"
    assert any(
        str(_native.__file__).endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )

    for filename in ("__init__.py", "_native.pyi", "py.typed"):
        assert any(str(file) == f"omnisus_dbf/{filename}" for file in files), filename
    assert any(file.name == "LICENSE" and ".dist-info" in str(file) for file in files)
    wheel_metadata = distribution.read_text("WHEEL")
    assert wheel_metadata is not None
    assert "Root-Is-Purelib: false" in wheel_metadata
    assert "Tag: cp312-abi3-" in wheel_metadata
    assert importlib.util.find_spec("datasus_dbc") is None
    assert importlib.util.find_spec("omnisus") is None


@pytest.mark.parametrize("batch_rows", [1, 2, 100_000])
@pytest.mark.parametrize(
    ("filename", "encoding", "values", "value_type"),
    [
        ("text-latin1.dbf", "latin-1", ["\x81", " a", ""], pa.string()),
        ("numeric-exact.dbf", "cp1252", [2**60 + 1, None], pa.int64()),
    ],
)
def test_seed_values_schema_and_lifetime(
    filename, encoding, values, value_type, batch_rows
) -> None:
    data = (Path(__file__).parent / "dbf" / filename).read_bytes()
    reader = dbf.open_reader(data, encoding=encoding, batch_rows=batch_rows)
    batches = list(reader)
    reader.close()
    reader.close()
    del reader, data
    gc.collect()

    expected_chunks = [
        values[start : start + batch_rows] for start in range(0, len(values), batch_rows)
    ]
    assert len(batches) == len(expected_chunks)
    for batch, expected_values in zip(batches, expected_chunks, strict=True):
        expected_type = (
            value_type if any(value is not None for value in expected_values) else pa.null()
        )
        expected = pa.record_batch([pa.array(expected_values, type=expected_type)], names=["X"])
        batch.validate(full=True)
        assert batch.schema.equals(expected.schema, check_metadata=True)
        assert batch.equals(expected)
        assert batch.to_pydict() == {"X": expected_values}


def test_early_close_keeps_delivered_batch_alive() -> None:
    data = (Path(__file__).parent / "dbf" / "text-latin1.dbf").read_bytes()
    reader = dbf.open_reader(data, encoding="latin-1", batch_rows=1)
    batch = next(reader)
    reader.close()
    reader.close()
    with pytest.raises(StopIteration):
        next(reader)
    del reader, data
    gc.collect()
    batch.validate(full=True)
    assert batch.equals(pa.record_batch([pa.array(["\x81"], type=pa.string())], names=["X"]))


def test_date_seed_reads_as_date32() -> None:
    data = (Path(__file__).parent / "dbf" / "date.dbf").read_bytes()
    reader = dbf.open_reader(data, encoding="cp1252", batch_rows=1)
    batch = next(reader)
    reader.close()
    assert batch.equals(
        pa.record_batch([pa.array([date(2024, 1, 1)], type=pa.date32())], names=["X"])
    )


def test_unsupported_seed_fails_during_open() -> None:
    data = (Path(__file__).parent / "dbf" / "unsupported-logical.dbf").read_bytes()
    with pytest.raises(dbf.UnsupportedDbfError):
        dbf.open_reader(data, encoding="cp1252", batch_rows=1)


def test_decompress_dbc_vector() -> None:
    blast = Path(__file__).parent / "blast"
    raw = bytes(8) + (33).to_bytes(2, "little") + bytes(27) + (blast / "test.pk").read_bytes()
    assert dbf.decompress_dbc(raw) == raw[:33] + (blast / "test.txt").read_bytes()
    with pytest.raises(dbf.InvalidDbcError):
        dbf.decompress_dbc(raw[:-1])
