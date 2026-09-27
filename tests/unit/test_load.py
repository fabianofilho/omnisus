"""`sus.load` and `import_dataset` inside a running event loop (marimo, Jupyter).

Real data: `sim_rr_2023_mini.dbc` is DORR2023.dbc (3 311 rows), served by the fake
DATASUS listing in `tests/support/fake_datasus.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import polars as pl
import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

RR_2023 = ScopeKey(uf="RR", ano=2023)
ROWS = 3311


@pytest.fixture
def served(monkeypatch, dbc_fixture) -> bytes:
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {RR_2023: payload})
    return payload


def test_import_dataset_runs_inside_a_running_event_loop(served, tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/lake.ducklake"

    async def notebook_cell() -> sus.ImportReport:
        # A marimo or Jupyter cell already runs inside an event loop.
        return sus.import_dataset("sim_obitos", scopes=[RR_2023], target=target)

    report = asyncio.run(notebook_cell())

    assert not report.failed, report.failed
    assert report.rows == ROWS


def test_load_imports_and_returns_the_requested_rows(served, tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/lake.ducklake"

    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    assert isinstance(dados, pl.DataFrame)
    assert dados.height == ROWS
    assert set(dados["uf"]) == {"RR"} and set(dados["ano"]) == {2023}


def test_load_twice_does_not_duplicate_rows(served, tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/lake.ducklake"

    sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)
    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    assert dados.height == ROWS


def test_load_works_inside_a_running_event_loop(served, tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/lake.ducklake"

    async def notebook_cell() -> pl.DataFrame:
        return sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    assert asyncio.run(notebook_cell()).height == ROWS


def test_load_names_the_failure_and_replace_rewrites(served, monkeypatch, tmp_path: Path) -> None:
    """The same file imported under another dictionary version: skip_same refuses."""
    target = f"ducklake:{tmp_path}/lake.ducklake"
    sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp.dbf_contract.publication_parser_version",
        lambda dictionary_hash: "dbc-staging-v1:outra-versao",
    )

    with pytest.raises(RuntimeError, match=r"RR_2023.*policy='replace'"):
        sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target, policy="replace")
    assert dados.height == ROWS


def test_load_raises_when_nothing_is_published(served, tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/lake.ducklake"

    with pytest.raises(LookupError, match="sim_obitos"):
        sus.load("sim_obitos", years=[2023], ufs=["AC"], target=target)


def test_load_returns_only_the_requested_scopes(monkeypatch, dbc_fixture, tmp_path: Path) -> None:
    """The lake holds the same file as RR 2023 and RR 2022; load asks for 2023 only."""
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    rr_2022 = ScopeKey(uf="RR", ano=2022)
    fake_datasus.serve(monkeypatch, "sim_obitos", {RR_2023: payload, rr_2022: payload})
    target = f"ducklake:{tmp_path}/lake.ducklake"
    report = sus.import_dataset("sim_obitos", scopes=[RR_2023, rr_2022], target=target)
    assert len(report.ok) == 2, report.outcomes

    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    assert dados.height == ROWS
    assert set(dados["ano"]) == {2023}


def test_default_lake_lives_in_data_raw_under_the_working_directory(
    served, monkeypatch, tmp_path: Path
) -> None:
    """No target: the lake goes to ./data/raw, which is /content/data/raw on Colab."""
    monkeypatch.delenv("OMNISUS_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"])

    assert (tmp_path / "data/raw/omnisus.ducklake").is_dir()
    with sus.LakeReader() as reader:
        assert "sim_obitos" in reader.tables()
    assert dados.height == ROWS


def test_data_dir_env_is_read_at_call_time(served, monkeypatch, tmp_path: Path) -> None:
    """A notebook sets the variable after `import omnisus`; the next call honours it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMNISUS_DATA_DIR", str(tmp_path / "outro"))

    sus.load("sim_obitos", years=[2023], ufs=["RR"])

    assert (tmp_path / "outro/omnisus.ducklake").is_dir()
    assert not (tmp_path / "data").exists()


def test_set_lake_dir_moves_the_default_lake(served, monkeypatch, tmp_path: Path) -> None:
    """On Colab the researcher points the lake at the mounted Drive, then calls as usual."""
    monkeypatch.delenv("OMNISUS_DATA_DIR", raising=False)  # restored after the test
    monkeypatch.chdir(tmp_path)

    lake_dir = sus.set_lake_dir("drive/omnisus")
    sus.load("sim_obitos", years=[2023], ufs=["RR"])

    assert lake_dir == tmp_path.resolve() / "drive/omnisus"
    assert (lake_dir / "omnisus.ducklake").is_dir()
    with sus.LakeReader() as reader:
        assert "sim_obitos" in reader.tables()
    assert not (tmp_path / "data").exists()


def test_set_lake_dir_expands_the_home_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OMNISUS_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # expanduser reads it on Windows

    assert sus.set_lake_dir("~/omnisus") == tmp_path.resolve() / "omnisus"


def test_load_requires_ufs_for_uf_datasets() -> None:
    """Omitting ufs would plan all 27 UFs into memory; ask for it explicitly."""
    with pytest.raises(ValueError, match=r"ufs=.*sus\.ALL_UFS"):
        sus.load("sim_obitos", years=[2023])


def test_load_rejects_ufs_for_national_datasets() -> None:
    with pytest.raises(ValueError, match="national"):
        sus.load("sinan_chagas", years=[2023], ufs=["RR"])


@pytest.mark.parametrize(
    ("name", "function"),
    [("ibge_populacao", "import_ibge_populacao"), ("cnes_master", "import_cnes_master")],
)
def test_load_points_other_products_to_their_function(name: str, function: str) -> None:
    with pytest.raises(ValueError, match=rf"sus\.{function}"):
        sus.load(name, years=[2023], ufs=["RR"])
