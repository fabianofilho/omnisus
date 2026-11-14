"""Tests for the CNES Master importer (API → lake.cnes_master)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import polars as pl
import pytest
import respx
from structlog.testing import capture_logs

from omnisus import import_cnes_master
from omnisus.lake import Lake
from omnisus.sources.cnes.importers.master import API_FONTE
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
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
            cnes VARCHAR, pf_pj VARCHAR, tp_unid VARCHAR, codufmun VARCHAR,
            ano INTEGER, mes INTEGER
        )
        """
    )
    con.executemany(
        f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES (?, '3', '05', '355030', 2024, 1)",
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
        # The source of an API name is recorded in cnes_master and shown as fonte_nome.
        assert lake.connect().execute(
            f"SELECT DISTINCT fonte FROM {lake.alias}.cnes_master"
        ).fetchall() == [(API_FONTE,)]
        assert lake.connect().execute(
            f"SELECT DISTINCT fonte_nome FROM {lake.alias}.aux_cnes"
        ).fetchall() == [(API_FONTE,)]


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
    """Explicit codes bypass the cnes_estabelecimentos discovery; the ST still has to mark
    them pessoa jurídica (pf_pj '3') for a name to be fetched."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["7654321"])

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
            f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES ('3333333', '3', '02', '355030', 2024, 1)"
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
    with Lake.local(target) as lake:
        _seed_cnes_estabelecimentos(lake, ["1234567"])
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


ST_RR = Path(__file__).resolve().parents[3] / "fixtures" / "dbc" / "cnes_rr_2024_01_mini.dbc"
PF_RR = "0048046"  # pf_pj '1' in the real ST excerpt of RR, 2024-01
PJ_RR = "0048038"  # pf_pj '3'
FORA_DO_ST = "9999999"


def _load_st_rr(lake: Lake) -> None:
    """The real ST excerpt of RR 2024-01 (pf_pj '3' 959 rows, '1' 77) as cnes_estabelecimentos."""
    frame = (
        dbc_bytes_to_lazyframe(ST_RR.read_bytes(), dataset="cnes_estabelecimentos")
        .collect()
        .with_columns(pl.lit(2024).alias("ano"), pl.lit(1).alias("mes"))
    )
    con = lake.connect()
    con.register("_st_rr", frame.to_arrow())
    con.execute(f"CREATE TABLE {lake.alias}.cnes_estabelecimentos AS SELECT * FROM _st_rr")
    con.unregister("_st_rr")


def _mock(code: str, nome: str) -> respx.Route:
    return respx.get(_api_url(code.lstrip("0"))).mock(
        return_value=httpx.Response(
            200, content=json.dumps(_api_response(int(code), nome_fantasia=nome, razao=nome))
        )
    )


@pytest.mark.parametrize("explicit", [False, True])
@respx.mock
def test_only_a_code_the_st_marks_pessoa_juridica_is_fetched(tmp_path: Path, explicit) -> None:
    """A pessoa física (pf_pj '1') and a code outside the ST are not fetched, listed or
    discovered: only a code the ST marks '3' in every imported month gets a name."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _load_st_rr(lake)
    pf, pj, fora = _mock(PF_RR, "DR FULANO"), _mock(PJ_RR, "HOSPITAL"), _mock(FORA_DO_ST, "X")
    # The ST has 958 other pessoa jurídica codes; discovery fetches them too.
    respx.get(url__regex=r"/cnes/estabelecimentos/\d+$").mock(return_value=httpx.Response(404))

    codes = [PF_RR, PJ_RR, FORA_DO_ST] if explicit else None
    with capture_logs() as logs:
        import_cnes_master(codes=codes, target=target)

    assert pj.called and not pf.called and not fora.called
    with Lake.local(target) as lake:
        names = dict(
            lake.connect().execute(f"SELECT cnes, nome FROM {lake.alias}.cnes_master").fetchall()
        )
    assert names[PJ_RR] == "HOSPITAL" and PF_RR not in names and FORA_DO_ST not in names
    (start,) = [e for e in logs if e["event"] == "cnes_master.start"]
    if explicit:
        assert (start["pessoa_fisica"], start["pf_pj_desconhecido"]) == (1, 1)


@respx.mock
def test_a_pessoa_fisica_name_already_in_cnes_master_is_removed(tmp_path: Path) -> None:
    """A lake filled before the rule keeps the professional's name; the next import of the
    API path removes it in the same transaction as the upsert."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _load_st_rr(lake)
    _mock(PJ_RR, "HOSPITAL")
    import_cnes_master(codes=[PJ_RR], target=target)
    with Lake.local(target) as lake:
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_master (cnes, nome) VALUES ('{PF_RR}', 'DR LEGADO')"
        )

    import_cnes_master(codes=[PJ_RR], target=target, only_missing=False)

    with Lake.local(target) as lake:
        con = lake.connect()
        master = {
            r[0] for r in con.execute(f"SELECT cnes FROM {lake.alias}.cnes_master").fetchall()
        }
        view = con.execute(
            f"SELECT nome FROM {lake.alias}.aux_cnes WHERE cnes = '{PF_RR}'"
        ).fetchall()
    assert PF_RR not in master
    assert view in ([], [(None,)])


@respx.mock
def test_without_pf_pj_in_the_lake_no_name_is_fetched(tmp_path: Path) -> None:
    """A lake whose cnes_estabelecimentos has no pf_pj cannot tell a pessoa física apart:
    nothing is fetched, and the log says why."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        lake.connect().execute(
            f"CREATE TABLE {lake.alias}.cnes_estabelecimentos "
            "(cnes VARCHAR, tp_unid VARCHAR, codufmun VARCHAR, ano INTEGER, mes INTEGER)"
        )
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES ('{PJ_RR}', '05', '140010', 2024, 1)"
        )
    route = _mock(PJ_RR, "HOSPITAL")
    with capture_logs() as logs:
        assert import_cnes_master(target=target) == 0
    assert not route.called
    (start,) = [e for e in logs if e["event"] == "cnes_master.start"]
    assert start["pf_pj_desconhecido"] == 1


@respx.mock
def test_an_api_name_with_a_valid_cpf_is_not_written(tmp_path: Path) -> None:
    """Synthetic, sensitive input: the CPF is made up, with valid check digits."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _load_st_rr(lake)
    _mock(PJ_RR, "FULANO DE TAL 52998224725")
    assert import_cnes_master(codes=[PJ_RR], target=target) == 0
    with Lake.local(target) as lake:
        names = lake.connect().execute(f"SELECT cnes FROM {lake.alias}.cnes_master").fetchall()
    assert names == []


# Synthetic, sensitive input: made up, with valid check digits, as in the test above.
CPF_SINTETICO = "52998224725"


def _master_names(target: str) -> dict[str, str | None]:
    with Lake.local(target) as lake:
        rows = lake.connect().execute(f"SELECT cnes, nome FROM {lake.alias}.cnes_master")
        return dict(rows.fetchall())


def _seed_legacy_cpf_names(target: str) -> None:
    """Synthetic, sensitive input: names with a CPF stored before the CPF rule. One has only
    ``nome``, the shape of the first API importer; the other has the CPF in the razão social
    of a code outside the ST."""
    from omnisus.sources.cnes.importers.master import _ensure_master_table

    with Lake.local(target) as lake:
        _load_st_rr(lake)
        _ensure_master_table(lake)
        con = lake.connect()
        con.execute(
            f"INSERT INTO {lake.alias}.cnes_master (cnes, nome) "
            f"VALUES ('{PJ_RR}', 'FULANO DE TAL {CPF_SINTETICO}')"
        )
        con.execute(
            f"INSERT INTO {lake.alias}.cnes_master (cnes, nome, razao_social) "
            f"VALUES ('{FORA_DO_ST}', 'CLINICA', 'BELTRANO 529.982.247-25')"
        )


@pytest.mark.parametrize(
    ("explicit", "only_missing", "api_name", "expected"),
    [
        # Discovery skips the code already in cnes_master; the next run fetches it.
        (False, True, "HOSPITAL", {}),
        # The API still writes the CPF: nothing is written for the code.
        (True, False, f"FULANO DE TAL {CPF_SINTETICO}", {}),
        # The API now gives a clean name: it replaces the removed one.
        (True, False, "HOSPITAL", {PJ_RR: "HOSPITAL"}),
    ],
)
@respx.mock
def test_a_name_with_a_cpf_already_in_cnes_master_is_removed(
    tmp_path: Path, monkeypatch, explicit, only_missing, api_name, expected
) -> None:
    """Every stored name with a CPF goes in the import's transaction, in any code and in any
    of nome, nome_fantasia and razao_social, whatever the API answers. One row per read, so
    a scan that stops after the first batch leaves a name behind."""
    monkeypatch.setattr("omnisus.sources.cnes.importers.master._CPF_SCAN_BATCH", 1)
    target = f"ducklake:{tmp_path}/x.ducklake"
    _seed_legacy_cpf_names(target)
    _mock(PJ_RR, api_name)
    respx.get(url__regex=r"/cnes/estabelecimentos/\d+$").mock(return_value=httpx.Response(404))

    with capture_logs() as logs:
        import_cnes_master(
            codes=[PJ_RR] if explicit else None, target=target, only_missing=only_missing
        )

    assert _master_names(target) == expected
    with Lake.local(target) as lake:
        view = dict(
            lake.connect()
            .execute(
                f"SELECT cnes, nome FROM {lake.alias}.aux_cnes WHERE cnes IN ('{PJ_RR}', '{FORA_DO_ST}')"
            )
            .fetchall()
        )
    assert view.get(PJ_RR) == expected.get(PJ_RR) and view.get(FORA_DO_ST) is None
    (removed,) = [e for e in logs if e["event"] == "cnes_master.names_removed"]
    assert removed["cpf_no_nome"] == 2


@respx.mock
def test_the_cpf_removal_rolls_back_with_the_import(tmp_path: Path, monkeypatch) -> None:
    """The removal is in the same transaction as the upsert: a failure undoes it."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    _seed_legacy_cpf_names(target)
    _mock(PJ_RR, "HOSPITAL")

    def fail_view(self):
        raise RuntimeError("view unavailable")

    monkeypatch.setattr(Lake, "ensure_aux_cnes_view", fail_view)
    with pytest.raises(RuntimeError, match="view unavailable"):
        import_cnes_master(codes=[PJ_RR], target=target, only_missing=False)
    assert set(_master_names(target)) == {PJ_RR, FORA_DO_ST}


@respx.mock
def test_a_clean_stored_name_stays_when_the_api_now_writes_a_cpf(tmp_path: Path) -> None:
    """The CPF answer is not written, and the clean name already stored is kept: the rule
    removes names with a CPF, not the codes whose source now has one. The FTP path does
    the same."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _load_st_rr(lake)
    _mock(PJ_RR, "HOSPITAL")
    import_cnes_master(codes=[PJ_RR], target=target)
    respx.routes.clear()
    _mock(PJ_RR, f"FULANO DE TAL {CPF_SINTETICO}")

    assert import_cnes_master(codes=[PJ_RR], target=target, only_missing=False) == 0
    assert _master_names(target) == {PJ_RR: "HOSPITAL"}


@respx.mock
def test_a_null_pf_pj_is_not_pessoa_juridica(tmp_path: Path) -> None:
    """A month whose ST row has no pf_pj cannot tell a pessoa física apart: not fetched."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        _load_st_rr(lake)
        lake.connect().execute(
            f"UPDATE {lake.alias}.cnes_estabelecimentos SET pf_pj = NULL WHERE cnes = '{PJ_RR}'"
        )
    route = _mock(PJ_RR, "HOSPITAL")
    assert import_cnes_master(codes=[PJ_RR], target=target) == 0
    assert not route.called
