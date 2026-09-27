"""End-to-end: SINASC fixture -> import_dataset("sinasc_nascidos_vivos") -> lake -> query."""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus


@pytest.mark.integration
def test_import_sinasc_with_fixture(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    fixture_bytes = dbc_fixture("sinasc_rr_2022_mini").read_bytes()
    fake_datasus.serve(
        monkeypatch, "sinasc_nascidos_vivos", {ScopeKey(uf="RR", ano=2022): fixture_bytes}
    )

    target = f"ducklake:{tmp_path}/test.ducklake"
    sus.import_dataset(
        "sinasc_nascidos_vivos",
        scopes=sus.scopes_for("sinasc_nascidos_vivos", years=[2022], ufs=["RR"]),
        target=target,
    )

    lake = Lake.local(target)
    n = (
        lake.connect()
        .execute("SELECT count(*) FROM lake.sinasc_nascidos_vivos WHERE ano=2022 AND uf='RR'")
        .fetchone()[0]
    )
    assert n > 0
    lake.close()
