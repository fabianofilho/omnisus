"""End-to-end: SIH monthly fixture -> import_dataset("sih_aih_reduzida") -> lake -> query."""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus


@pytest.mark.integration
def test_import_sih_monthly(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    fixture_bytes = dbc_fixture("sih_rr_2024_01_mini").read_bytes()
    fake_datasus.serve(
        monkeypatch, "sih_aih_reduzida", {ScopeKey(uf="RR", ano=2024, mes=1): fixture_bytes}
    )

    target = f"ducklake:{tmp_path}/test.ducklake"
    sus.import_dataset(
        "sih_aih_reduzida",
        scopes=sus.scopes_for("sih_aih_reduzida", years=[2024], ufs=["RR"], months=[1]),
        target=target,
    )

    lake = Lake.local(target)
    rows = (
        lake.connect()
        .execute("SELECT count(*) FROM lake.sih_aih_reduzida WHERE ano=2024 AND uf='RR' AND mes=1")
        .fetchone()[0]
    )
    assert rows > 0
    lake.close()
