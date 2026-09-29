"""End-to-end: fixture DBC -> import_dataset("sim_obitos") -> lake -> query."""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus


@pytest.mark.integration
def test_import_sim_e2e_with_fixture(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    fixture = dbc_fixture("sim_rr_2023_mini")
    fixture_bytes = fixture.read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): fixture_bytes})

    target = f"ducklake:{tmp_path}/test.ducklake"
    report = sus.import_dataset(
        "sim_obitos", scopes=sus.scopes_for("sim_obitos", years=[2023], ufs=["RR"]), target=target
    )
    assert not report.failed, report.failed
    assert report.rows > 0

    lake = Lake.local(target)
    n = (
        lake.connect()
        .execute("SELECT count(*) FROM lake.sim_obitos WHERE ano=2023 AND uf='RR'")
        .fetchone()[0]
    )
    assert n > 0
    lake.close()
