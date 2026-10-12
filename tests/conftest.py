"""Shared pytest fixtures for omnisus."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import duckdb
import pytest

from omnisus.sources.datasus_ftp.native import API_VERSION

# DuckDB checks the signature of the ducklake and sqlite_scanner binaries (35-36 MB each)
# on every LOAD into a new instance, and omnisus opens one instance per Lake and
# LakeReader, so the check is most of the time of each attach. The tests load the same
# signed binaries that INSTALL fetched, so they skip it; production code still runs it.
_duckdb_connect = duckdb.connect


def _connect_without_signature_check(
    database=":memory:", read_only=False, config=None
) -> duckdb.DuckDBPyConnection:
    config = {"allow_unsigned_extensions": True, **(config or {})}
    return _duckdb_connect(database=database, read_only=read_only, config=config)


duckdb.connect = _connect_without_signature_check


def pytest_addoption(parser):
    parser.addoption(
        "--require-rust-dbf",
        action="store_true",
        default=False,
        help="Require the real native extension and all committed DBF/DBC fixtures.",
    )


def _native_available():
    try:
        import omnisus_dbf
    except ModuleNotFoundError as exc:
        if exc.name == "omnisus_dbf":
            return False
        raise
    if omnisus_dbf.API_VERSION != API_VERSION:
        raise pytest.UsageError(f"Incompatible native API (expected {API_VERSION})")
    return True


def pytest_sessionstart(session):
    if session.config.getoption("--require-rust-dbf"):
        if not _native_available():
            raise pytest.UsageError("--require-rust-dbf requires the installed native wheel")
        from tests.support.dbf import DBC_CASES

        root = Path(__file__).parent / "fixtures"
        for name, _dataset in DBC_CASES:
            if not (root / "dbc" / f"{name}.dbc").is_file():
                raise pytest.UsageError(f"Required DBC fixture missing: {name}")
        for entry in json.loads((root / "dbf" / "manifest.json").read_text(encoding="utf-8")):
            seed = root / "dbf" / entry["file"]
            if (
                not seed.is_file()
                or hashlib.sha256(seed.read_bytes()).hexdigest() != entry["sha256"]
            ):
                raise pytest.UsageError(f"Required DBF seed missing or changed: {seed.name}")


def pytest_collection_modifyitems(config, items):
    native_tests = [item for item in items if "rust_dbf" in item.keywords]
    if native_tests and not _native_available():
        for item in native_tests:
            item.add_marker(pytest.mark.skip(reason="Optional Rust DBF wheel is not installed"))


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to tests/fixtures/."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def dbc_fixture(fixtures_dir: Path) -> Callable[[str], Path]:
    """Factory: dbc_fixture('sim_rr_2023_mini') -> Path."""

    def _resolve(name: str) -> Path:
        path = fixtures_dir / "dbc" / f"{name}.dbc"
        if not path.exists():
            pytest.skip(f"DBC fixture not present: {path}. Run scripts/build_fixtures.py")
        return path

    return _resolve


@pytest.fixture
def tmp_lake(tmp_path: Path) -> Iterator[Path]:
    """Temp directory for an ephemeral DuckLake."""
    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()
    yield lake_dir
