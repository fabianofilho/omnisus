"""`publications(snapshot_id=)` and `reference_join_sql(snapshot_id=)` read one snapshot
through one attach, whatever snapshot the attach itself is pinned to (#101).

Real data: `sim_rr_2023_mini.dbc` (DORR2023.dbc) served by the fake DATASUS listing,
and the packaged vocabularies of `auxiliares-bootstrap.zip`. The lake has three
snapshots: s0 (empty), s1 (vocabularies and SIM RR 2023, run ``r1``) and s2 (the same
scope replaced by run ``r2``, and one CID-10 label rewritten by hand to stand for a
vocabulary republished between s1 and s2).
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus
from tests.support.lake_rows import DBC

RR_2023 = ScopeKey(uf="RR", ano=2023)
REWRITTEN = "rótulo reescrito em s2"


@dataclass(frozen=True)
class PinnedLake:
    target: str
    s0: int
    s1: int
    s2: int
    code: str
    label_s1: str


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> PinnedLake:
    """Built once for the module: every test only reads it, through ``LakeReader``."""
    target = f"ducklake:{tmp_path_factory.mktemp('pin')}/pin.ducklake"
    with pytest.MonkeyPatch.context() as patch:
        # The conftest guard is per test and not active while a module fixture sets up.
        fake_datasus.block_ftp_listing(patch)
        with sus.Lake.local(target) as writer:
            s0 = sus.latest_snapshot_id(writer)
            writer.bootstrap_auxiliares()
        fake_datasus.serve(
            patch, "sim_obitos", {RR_2023: (DBC / "sim_rr_2023_mini.dbc").read_bytes()}
        )
        sus.import_dataset("sim_obitos", scopes=[RR_2023], target=target, run_id="r1")
        with sus.Lake.local(target) as writer:
            s1 = sus.latest_snapshot_id(writer)
            code, label = (
                writer.connect()
                .execute(
                    "SELECT d.causabas, r.descricao FROM lake.sim_obitos d "
                    "JOIN lake.aux_cid10 r ON d.causabas = r.codigo "
                    "GROUP BY ALL ORDER BY count(*) DESC, d.causabas LIMIT 1"
                )
                .fetchone()
            )
        sus.import_dataset(
            "sim_obitos", scopes=[RR_2023], target=target, policy="replace", run_id="r2"
        )
        with sus.Lake.local(target) as writer:
            writer.connect().execute(
                "UPDATE lake.aux_cid10 SET descricao = ? WHERE codigo = ?", [REWRITTEN, code]
            )
            s2 = sus.latest_snapshot_id(writer)
    return PinnedLake(target, s0, s1, s2, code, label)


def _runs(rows: list[dict]) -> set[tuple[str, bool]]:
    return {(row["run_id"], row["active"]) for row in rows}


def test_publications_at_a_snapshot_before_the_manifest_is_empty(lake: PinnedLake) -> None:
    with sus.LakeReader(lake.target) as reader:
        assert reader.publications(snapshot_id=lake.s0) == []


def test_publications_at_a_snapshot_the_lake_never_had_raise(lake: PinnedLake) -> None:
    with sus.LakeReader(lake.target) as reader, pytest.raises(duckdb.InvalidInputException):
        reader.publications(snapshot_id=lake.s2 + 1)


def test_publications_at_s1_do_not_see_the_s2_publication(lake: PinnedLake) -> None:
    with sus.LakeReader(lake.target) as reader:
        assert _runs(reader.publications(snapshot_id=lake.s1)) == {("r1", True)}
        assert _runs(reader.publications()) == {("r1", False), ("r2", True)}
        (pinned,) = reader.publications(snapshot_id=lake.s1, run_id="r1")
        assert pinned["sources"][0]["source_uri"].endswith("DORR2023.dbc")


def test_the_parameter_wins_over_the_attach_snapshot(lake: PinnedLake) -> None:
    with sus.LakeReader(lake.target, snapshot_id=lake.s1) as reader:
        assert _runs(reader.publications()) == {("r1", True)}
        assert _runs(reader.publications(snapshot_id=lake.s2)) == {("r1", False), ("r2", True)}


def test_reference_join_at_s1_returns_the_s1_label(lake: PinnedLake) -> None:
    def label(snapshot_id: int | None) -> str:
        join = sus.reference_join_sql("sim_obitos", "causabas", snapshot_id=snapshot_id)
        with sus.LakeReader(lake.target) as reader:
            (row,) = (
                reader.connect()
                .execute(
                    f"SELECT DISTINCT ref_causabas.descricao FROM lake.sim_obitos AS d "
                    f"{join} WHERE d.causabas = ?",
                    [lake.code],
                )
                .fetchall()
            )
        return row[0]

    assert label(None) == REWRITTEN
    assert label(lake.s1) == lake.label_s1 != REWRITTEN


def test_reference_join_sql_pins_the_vocabulary_after_its_alias() -> None:
    assert sus.reference_join_sql("sim_obitos", "causabas", snapshot_id=7) == (
        'LEFT JOIN "lake"."aux_cid10" AS "ref_causabas" AT (VERSION => 7) '
        'ON d."causabas" = "ref_causabas"."codigo"'
    )
    assert sus.reference_join_sql(
        "sim_obitos", "causabas", snapshot_id=None
    ) == sus.reference_join_sql("sim_obitos", "causabas")


@pytest.mark.parametrize("bad", [-1, True, 1.0, "7"])
def test_snapshot_id_must_be_a_non_negative_int(bad: object) -> None:
    with pytest.raises(ValueError, match="snapshot_id"):
        sus.reference_join_sql("sim_obitos", "causabas", snapshot_id=bad)  # type: ignore[arg-type]
