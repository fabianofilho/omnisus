"""RD 1992-2007: a field the DBF publishes as C in some months and N in others lands as text (#40).

`num_proc` is N4 in RDRR9602 and C4 in RDRR9709. `insc_pn` and `seq_aih5` are N from 2004-07
to 2006-03 (RDRR0407 is sih_rd_rr_2004_07_excerpt) and C before and after (RDRR0712 is
sih_rd_rr_2007_12_mini). The number is kept as published: `0` stays `"0"`, not
`"0000000000"`, and `364` stays `"364"`, not `"0364"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

ERA_1 = "sih_aih_reduzida_1992_1997"
ERA_2 = "sih_aih_reduzida_1998_2007"
# (dataset, N month, C month, the fields, what each month holds)
CASES = {
    ERA_1: (
        ("sih_rd_rr_1996_02_mini", ScopeKey(uf="RR", ano=1996, mes=2)),
        ("sih_rd_rr_1997_09_mini", ScopeKey(uf="RR", ano=1997, mes=9)),
        ("num_proc",),
        [(2, ("364",)), (9, ("0489",))],
    ),
    ERA_2: (
        ("sih_rd_rr_2004_07_excerpt", ScopeKey(uf="RR", ano=2004, mes=7)),
        ("sih_rd_rr_2007_12_mini", ScopeKey(uf="RR", ano=2007, mes=12)),
        ("insc_pn", "seq_aih5"),
        [(7, ("0", "0")), (12, ("0000000000", "000"))],
    ),
}


@pytest.mark.parametrize("n_first", [True, False], ids=["N-C", "C-N"])
@pytest.mark.parametrize("dataset", sorted(CASES))
def test_an_n_month_and_a_c_month_import_into_one_table(
    dataset, n_first, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dbc_fixture
) -> None:
    n_month, c_month, fields, expected = CASES[dataset]
    target = f"ducklake:{tmp_path}/rd.ducklake"
    for fixture, scope in (n_month, c_month) if n_first else (c_month, n_month):
        fake_datasus.serve(monkeypatch, dataset, {scope: dbc_fixture(fixture).read_bytes()})
        report = sus.import_dataset(dataset, scopes=[scope], target=target)
        assert not report.failed, report.failed
    with Lake.local(target) as lake:
        con = lake.connect()
        types = {
            name: kind for name, kind, *_ in con.execute(f"DESCRIBE lake.{dataset}").fetchall()
        }
        assert {types[f] for f in fields} == {"VARCHAR"}
        rows = con.execute(
            f"SELECT mes, {', '.join(fields)} FROM lake.{dataset} GROUP BY ALL ORDER BY mes"
        ).fetchall()
    assert [(row[0], tuple(row[1:])) for row in rows] == expected
