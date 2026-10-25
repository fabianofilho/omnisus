"""Tests for the CNES Master importer (API → lake.cnes_master)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from omnisus import import_cnes_master
from omnisus.lake import Lake
from tests.support.connection_faults import FaultyConnection


def _api_url(cnes_unpadded: str) -> str:
    return f"https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes_unpadded}"


def _api_response(cnes_int: int, *, nome_fantasia: str, razao: str) -> dict:
    return {
        "codigo_cnes": cnes_int,
        "nome_fantasia": nome_fantasia,
        "nome_razao_social": razao,
        "codigo_tipo_unidade": 5,
    }


def _seed_cnes_estabelecimentos(lake: Lake, cnes_codes: list[str]) -> None:
    """Minimal cnes_estabelecimentos with one row per code so import_cnes_master() finds them."""
    con = lake.connect()
    con.execute(
        f"""
        CREATE TABLE {lake.alias}.cnes_estabelecimentos (
            cnes VARCHAR, tp_unid VARCHAR, codufmun VARCHAR,
            ano INTEGER, mes INTEGER
        )
        """
    )
    con.executemany(
        f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES (?, '05', '355030', 2024, 1)",
        [(c,) for c in cnes_codes],
    )


@respx.mock
def test_import_cnes_master_writes_table_and_refreshes_view(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["2789590", "0123456"])

    # API uses unpadded integer paths
    respx.get(_api_url("2789590")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(
                _api_response(2789590, nome_fantasia="HOSPITAL BRASIL", razao="REDE DOR")
            ),
        )
    )
    respx.get(_api_url("123456")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(
                _api_response(123456, nome_fantasia="UBS BAIRRO X", razao="MUNICIPIO X")
            ),
        )
    )

    n = import_cnes_master(target=target)
    assert n == 2

    with Lake.local(target) as lake:
        rows = (
            lake.connect()
            .execute(
                f"SELECT cnes, nome, nome_fantasia, razao_social "
                f"FROM {lake.alias}.cnes_master ORDER BY cnes"
            )
            .fetchall()
        )
        assert rows == [
            ("0123456", "UBS BAIRRO X", "UBS BAIRRO X", "MUNICIPIO X"),
            ("2789590", "HOSPITAL BRASIL", "HOSPITAL BRASIL", "REDE DOR"),
        ]
        # aux_cnes view now joins names
        view_rows = (
            lake.connect()
            .execute(f"SELECT cnes, nome FROM {lake.alias}.aux_cnes ORDER BY cnes")
            .fetchall()
        )
        assert view_rows == [
            ("0123456", "UBS BAIRRO X"),
            ("2789590", "HOSPITAL BRASIL"),
        ]


@respx.mock
def test_import_cnes_master_skips_404_and_network_failures(tmp_path: Path) -> None:
    """One CNES returns 200, another 404, another times out — only the 200 lands."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1111111", "2222222", "3333333"])

    respx.get(_api_url("1111111")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(_api_response(1111111, nome_fantasia="OK", razao="OK SA")),
        )
    )
    respx.get(_api_url("2222222")).mock(return_value=httpx.Response(404))
    respx.get(_api_url("3333333")).mock(side_effect=httpx.ConnectError("boom"))

    n = import_cnes_master(target=target)
    assert n == 1

    with Lake.local(target) as lake:
        rows = (
            lake.connect()
            .execute(f"SELECT cnes FROM {lake.alias}.cnes_master ORDER BY cnes")
            .fetchall()
        )
        assert rows == [("1111111",)]


@respx.mock
def test_import_cnes_master_fallbacks_to_razao_when_nome_fantasia_empty(
    tmp_path: Path,
) -> None:
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1234567"])

    respx.get(_api_url("1234567")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(
                _api_response(1234567, nome_fantasia="", razao="HOSPITAL DA RAZAO SA")
            ),
        )
    )

    import_cnes_master(target=target)
    with Lake.local(target) as lake:
        nome = (
            lake.connect()
            .execute(f"SELECT nome FROM {lake.alias}.cnes_master WHERE cnes = '1234567'")
            .fetchone()[0]
        )
        assert nome == "HOSPITAL DA RAZAO SA"


@respx.mock
def test_import_cnes_master_drops_records_with_no_usable_name(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["9999999"])

    respx.get(_api_url("9999999")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(_api_response(9999999, nome_fantasia="", razao="")),
        )
    )

    n = import_cnes_master(target=target)
    assert n == 0
    with Lake.local(target) as lake:
        rows = (
            lake.connect().execute(f"SELECT COUNT(*) FROM {lake.alias}.cnes_master").fetchone()[0]
        )
        assert rows == 0


def test_import_cnes_master_returns_zero_when_cnes_estabelecimentos_missing(
    tmp_path: Path,
) -> None:
    """Without cnes_estabelecimentos (and without explicit codes), there's nothing to fetch."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    n = import_cnes_master(target=target)
    assert n == 0


@respx.mock
def test_import_cnes_master_accepts_explicit_codes(tmp_path: Path) -> None:
    """Explicit codes bypasses the cnes_estabelecimentos discovery."""
    target = f"ducklake:{tmp_path}/x.ducklake"

    respx.get(_api_url("7654321")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(_api_response(7654321, nome_fantasia="EXPLICIT", razao="X SA")),
        )
    )

    n = import_cnes_master(codes=["7654321"], target=target)
    assert n == 1
    with Lake.local(target) as lake:
        nome = lake.connect().execute(f"SELECT nome FROM {lake.alias}.cnes_master").fetchone()[0]
        assert nome == "EXPLICIT"


def test_aux_cnes_view_works_without_cnes_master_loaded(tmp_path: Path) -> None:
    """The view degrades gracefully: nome is NULL when cnes_master doesn't exist yet."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1234567"])
        assert lake.ensure_aux_cnes_view() is True

        rows = (
            lake.connect()
            .execute(f"SELECT cnes, nome, tp_unid FROM {lake.alias}.aux_cnes")
            .fetchall()
        )
        assert rows == [("1234567", None, "05")]


# ---------------------------------------------------------------------------
# Incremental runs + progress callback
# ---------------------------------------------------------------------------


@respx.mock
def test_import_cnes_master_only_missing_skips_already_fetched(tmp_path: Path) -> None:
    """Re-running with only_missing=True (default) only fetches new codes."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1111111", "2222222"])

    # First run — both fetched
    respx.get(_api_url("1111111")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(1111111, nome_fantasia="A", razao="A SA"))
        )
    )
    respx.get(_api_url("2222222")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(2222222, nome_fantasia="B", razao="B SA"))
        )
    )
    assert import_cnes_master(target=target) == 2

    # Add a new code to cnes_estabelecimentos; re-run — only the new one should be fetched.
    with Lake.local(target) as lake:
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES ('3333333', '02', '355030', 2024, 1)"
        )

    respx.get(_api_url("3333333")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(3333333, nome_fantasia="C", razao="C SA"))
        )
    )

    n = import_cnes_master(target=target)
    assert n == 1  # only the new code

    # Original two records were preserved (upsert, not REPLACE TABLE).
    with Lake.local(target) as lake:
        all_rows = (
            lake.connect()
            .execute(f"SELECT cnes FROM {lake.alias}.cnes_master ORDER BY cnes")
            .fetchall()
        )
        assert all_rows == [("1111111",), ("2222222",), ("3333333",)]


@respx.mock
def test_import_cnes_master_only_missing_false_refetches_all(tmp_path: Path) -> None:
    """only_missing=False forces re-fetching everything (e.g. names changed)."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1234567"])

    respx.get(_api_url("1234567")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(1234567, nome_fantasia="OLD", razao="X SA"))
        )
    )
    import_cnes_master(target=target)

    # Re-mock with new name; only_missing=False should re-fetch and upsert.
    respx.get(_api_url("1234567")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(1234567, nome_fantasia="NEW", razao="X SA"))
        )
    )
    n = import_cnes_master(target=target, only_missing=False)
    assert n == 1
    with Lake.local(target) as lake:
        nome = (
            lake.connect()
            .execute(f"SELECT nome FROM {lake.alias}.cnes_master WHERE cnes = '1234567'")
            .fetchone()[0]
        )
        assert nome == "NEW"


@respx.mock
def test_import_cnes_master_invokes_progress_callback(tmp_path: Path) -> None:
    """Progress callback fires once per CNES code processed (success or failure)."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1111111", "2222222", "3333333"])

    respx.get(_api_url("1111111")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(1111111, nome_fantasia="A", razao="A SA"))
        )
    )
    respx.get(_api_url("2222222")).mock(return_value=httpx.Response(404))
    respx.get(_api_url("3333333")).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(3333333, nome_fantasia="C", razao="C SA"))
        )
    )

    calls: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> None:
        calls.append((done, total))

    import_cnes_master(target=target, progress=on_progress)

    # 3 codes total → 3 progress callbacks; final must reach (3, 3).
    assert len(calls) == 3
    assert calls[-1] == (3, 3)
    assert all(total == 3 for _, total in calls)
    # Order is non-deterministic (concurrent), but done values must be 1,2,3.
    assert sorted(d for d, _ in calls) == [1, 2, 3]


def test_upsert_failure_preserves_previous_record(tmp_path):
    from omnisus.sources.cnes.importers.master import _ensure_master_table, _upsert_master

    with Lake.local(f"ducklake:{tmp_path}/atomic.ducklake") as lake:
        _ensure_master_table(lake)
        lake.connect().execute(
            "INSERT INTO lake.cnes_master (cnes, nome, nome_fantasia, razao_social) VALUES ('1234567', 'OLD', 'OLD', NULL)"
        )
        lake._con = FaultyConnection(
            lake.connect(), before={"INSERT INTO": RuntimeError("insert failed")}
        )
        records = [
            {"cnes": "1234567", "nome": "NEW", "nome_fantasia": "NEW", "razao_social": None}
        ]
        with pytest.raises(RuntimeError, match="insert failed"):
            _upsert_master(lake, records)
        assert lake.connect().execute("SELECT nome FROM lake.cnes_master").fetchall() == [("OLD",)]


def test_conflicting_records_are_rejected_before_delete(tmp_path):
    from omnisus.sources.cnes.importers.master import _ensure_master_table, _upsert_master

    with Lake.local(f"ducklake:{tmp_path}/conflict.ducklake") as lake:
        _ensure_master_table(lake)
        lake.connect().execute(
            "INSERT INTO lake.cnes_master (cnes, nome, nome_fantasia, razao_social) VALUES ('1234567', 'OLD', 'OLD', NULL)"
        )
        records = [
            {"cnes": "1234567", "nome": "A", "nome_fantasia": "A", "razao_social": None},
            {"cnes": "1234567", "nome": "B", "nome_fantasia": "B", "razao_social": None},
        ]
        with pytest.raises(ValueError, match="conflicting"):
            _upsert_master(lake, records)
        assert lake.connect().execute("SELECT nome FROM lake.cnes_master").fetchall() == [("OLD",)]


@respx.mock
def test_duplicate_codes_fetch_once(tmp_path):
    route = respx.get(_api_url("1234567")).mock(
        return_value=httpx.Response(
            200, json=_api_response(1234567, nome_fantasia="NEW", razao="NEW SA")
        )
    )
    target = f"ducklake:{tmp_path}/dedup.ducklake"
    assert import_cnes_master(codes=["1234567", "1234567"], target=target) == 1
    assert route.call_count == 1
    with Lake.local(target) as lake:
        assert lake.connect().execute("SELECT count(*) FROM lake.cnes_master").fetchone()[0] == 1


@respx.mock
def test_view_failure_rolls_back_master_refresh(tmp_path, monkeypatch):
    from omnisus.sources.cnes.importers.master import _ensure_master_table

    target = f"ducklake:{tmp_path}/view.ducklake"
    with Lake.local(target) as lake:
        _ensure_master_table(lake)
        lake.connect().execute(
            "INSERT INTO lake.cnes_master (cnes, nome, nome_fantasia, razao_social) VALUES ('1234567', 'OLD', 'OLD', NULL)"
        )
    respx.get(_api_url("1234567")).mock(
        return_value=httpx.Response(
            200, json=_api_response(1234567, nome_fantasia="NEW", razao="NEW SA")
        )
    )

    def fail_view(self):
        raise RuntimeError("view unavailable")

    monkeypatch.setattr(Lake, "ensure_aux_cnes_view", fail_view)
    with pytest.raises(RuntimeError, match="view unavailable"):
        import_cnes_master(codes=["1234567"], target=target)
    with Lake.local(target) as lake:
        assert lake.connect().execute("SELECT nome FROM lake.cnes_master").fetchall() == [("OLD",)]


@respx.mock
def test_import_cnes_master_runs_inside_a_running_event_loop(tmp_path: Path) -> None:
    """A marimo or Jupyter cell already runs an event loop; `asyncio.run` there fails."""
    import asyncio

    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["2789590"])
    respx.get(_api_url("2789590")).mock(
        return_value=httpx.Response(
            200,
            content=json.dumps(
                _api_response(2789590, nome_fantasia="HOSPITAL BRASIL", razao="REDE DOR")
            ),
        )
    )

    async def notebook_cell() -> int:
        return import_cnes_master(target=target)

    assert asyncio.run(notebook_cell()) == 1
