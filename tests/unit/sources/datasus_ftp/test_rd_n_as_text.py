"""RD 1992-2007: a field the DBF publishes as C in some months and N in others lands as text (#40).

`insc_pn` and `seq_aih5` are N from 2004-07 to 2006-03 (RDRR0407 is sih_rd_rr_2004_07_excerpt)
and C before and after (RDRR0712 is sih_rd_rr_2007_12_mini). The number is kept as published:
`0` stays `"0"`, not `"0000000000"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

DATASET = "sih_aih_reduzida_1998_2007"
N_MONTH = ("sih_rd_rr_2004_07_excerpt", ScopeKey(uf="RR", ano=2004, mes=7))
C_MONTH = ("sih_rd_rr_2007_12_mini", ScopeKey(uf="RR", ano=2007, mes=12))


@pytest.mark.parametrize("order", [(C_MONTH, N_MONTH), (N_MONTH, C_MONTH)], ids=["C-N", "N-C"])
def test_an_n_month_and_a_c_month_import_into_one_table(
    order, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dbc_fixture
) -> None:
    target = f"ducklake:{tmp_path}/rd.ducklake"
    for fixture, scope in order:
        fake_datasus.serve(monkeypatch, DATASET, {scope: dbc_fixture(fixture).read_bytes()})
        report = sus.import_dataset(DATASET, scopes=[scope], target=target)
        assert not report.failed, report.failed
    with Lake.local(target) as lake:
        con = lake.connect()
        types = {
            name: kind for name, kind, *_ in con.execute(f"DESCRIBE lake.{DATASET}").fetchall()
        }
        assert types["insc_pn"] == types["seq_aih5"] == "VARCHAR"
        rows = con.execute(
            f"SELECT mes, insc_pn, seq_aih5, count(*) FROM lake.{DATASET} "
            "GROUP BY ALL ORDER BY mes"
        ).fetchall()
    assert [(mes, insc, seq) for mes, insc, seq, _ in rows] == [
        (7, "0", "0"),
        (12, "0000000000", "000"),
    ]
