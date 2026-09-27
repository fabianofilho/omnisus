"""End-to-end: CNES-ST fixture -> import_dataset() or load() -> lake -> aux_cnes.

Real data: `cnes_rr_2024_01_mini.dbc` is STRR2401.dbc, served by the fake DATASUS listing.
Every door into a CNES-ST import leaves `aux_cnes` up to date.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

RR_2024_01 = ScopeKey(uf="RR", ano=2024, mes=1)


@pytest.fixture
def target(monkeypatch, tmp_path: Path, dbc_fixture) -> str:
    fixture_bytes = dbc_fixture("cnes_rr_2024_01_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "cnes_estabelecimentos", {RR_2024_01: fixture_bytes})
    return f"ducklake:{tmp_path}/test.ducklake"


def _counts(target: str) -> tuple[int, int]:
    with Lake.local(target) as lake:
        con = lake.connect()
        rows = con.execute("SELECT count(*) FROM lake.cnes_estabelecimentos").fetchone()[0]
        establishments = con.execute("SELECT count(*) FROM lake.aux_cnes").fetchone()[0]
    return rows, establishments


@pytest.mark.integration
def test_import_dataset_refreshes_aux_cnes(target: str) -> None:
    sus.import_dataset("cnes_estabelecimentos", scopes=[RR_2024_01], target=target)

    rows, establishments = _counts(target)
    assert rows > 0 and establishments > 0


@pytest.mark.integration
def test_load_refreshes_aux_cnes(target: str) -> None:
    dados = sus.load("cnes_estabelecimentos", years=[2024], months=[1], ufs=["RR"], target=target)

    rows, establishments = _counts(target)
    assert rows == dados.height and establishments > 0
