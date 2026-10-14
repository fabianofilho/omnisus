"""`sus.read`: a lake table or view, or the scopes `load` returns, without the server.

Real data: the packaged vocabularies of `auxiliares-bootstrap.zip` (each file hashed in
the source registry); `sim_rr_2023_mini.dbc`, DORR2023.dbc (3 311 rows);
`sinan_chagas_br_2023.dbc`, CHAGBR23.dbc (6 253 rows); `sih_rr_2024_01_mini.dbc`,
RDRR2401.dbc (3 714 rows). The fake DATASUS listing in `tests/support/fake_datasus.py`
serves them to `load`; `read` runs with the listing and the download refused.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import polars as pl
import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

RR_2023 = ScopeKey(uf="RR", ano=2023)


@pytest.fixture
def target(tmp_path: Path) -> str:
    target = f"ducklake:{tmp_path}/lake.ducklake"
    with sus.Lake.local(target) as lake:
        lake.bootstrap_auxiliares()
    return target


def test_read_returns_a_vocabulary_as_polars(target: str) -> None:
    cid10 = sus.read("aux_cid10", target=target)

    with sus.LakeReader(target) as lake:
        expected = lake.connect().sql("FROM lake.aux_cid10").pl()
    assert isinstance(cid10, pl.DataFrame)
    assert cid10.sort("codigo").equals(expected.sort("codigo"))


def test_read_returns_the_rows_load_imported(target: str, monkeypatch, dbc_fixture) -> None:
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): payload})
    sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    obitos = sus.read("sim_obitos", target=target)

    assert obitos.height == 3311
    assert set(obitos["uf"]) == {"RR"}
    assert sus.read(sus.resolve("sim_obitos"), target=target).equals(obitos)


def test_read_returns_a_view(target: str) -> None:
    """`ibge_populacao` is a view; DuckDB's `.table()` does not resolve DuckLake views."""
    with sus.Lake.local(target) as lake:
        lake.connect().execute(
            "CREATE VIEW lake.uf_norte AS FROM lake.aux_uf WHERE codigo_ibge < '20'"
        )

    assert sorted(sus.read("uf_norte", target=target)["sigla"]) == [
        "AC", "AM", "AP", "PA", "RO", "RR", "TO",
    ]  # fmt: skip


def test_read_names_what_to_run_for_a_missing_table(target: str) -> None:
    with pytest.raises(LookupError, match=r"ibge_populacao.*import_ibge_populacao"):
        sus.read("ibge_populacao", target=target)


@pytest.fixture
def server_down(monkeypatch: pytest.MonkeyPatch):
    """The listing and the download raise as when the FTP refuses connections (#92)."""

    def refuse(*_args: object, **_kw: object):
        raise sus.FtpUnavailable("ftp.datasus.gov.br: timeout no connect")

    def apply() -> None:
        monkeypatch.setattr("omnisus.sources.datasus_ftp._runner.list_sources", refuse)
        monkeypatch.setattr("omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", refuse)

    return apply


def test_read_returns_the_scopes_load_returned_with_the_server_down(
    target: str, monkeypatch, dbc_fixture, server_down
) -> None:
    """Same rows, columns and harmonised categories as `load`; no call to the server."""
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {RR_2023: payload})
    loaded = sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)
    server_down()
    with pytest.raises(sus.FtpUnavailable):
        sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)

    dados = sus.read("sim_obitos", years=[2023], ufs=["RR"], target=target)

    assert "idade_anos_completos" in dados.columns
    assert dados.equals(loaded)


def test_read_warns_about_the_scopes_the_lake_lacks(
    target: str, monkeypatch, dbc_fixture, server_down
) -> None:
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {RR_2023: payload})
    sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)
    server_down()

    with pytest.warns(UserWarning, match=r"the lake does not have.*RR_2022.*sus\.load"):
        dados = sus.read("sim_obitos", years=[2022, 2023], ufs=["RR"], target=target)

    assert dados.height == 3311
    assert set(dados["ano"]) == {2023}


def test_read_raises_when_the_lake_has_none_of_the_scopes(
    target: str, monkeypatch, dbc_fixture, server_down
) -> None:
    server_down()
    with pytest.raises(LookupError, match=r"the lake has none of these sim_obitos scopes"):
        sus.read("sim_obitos", years=[2023], ufs=["RR"], target=target)

    fake_datasus.serve(
        monkeypatch, "sim_obitos", {RR_2023: dbc_fixture("sim_rr_2023_mini").read_bytes()}
    )
    sus.load("sim_obitos", years=[2023], ufs=["RR"], target=target)
    server_down()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no harmonised-categories warning for zero rows
        with pytest.raises(LookupError, match=r"AC_2023"):
            sus.read("sim_obitos", years=[2023], ufs=["AC"], target=target)


def test_read_a_national_dataset_filters_by_source_year(
    target: str, monkeypatch, dbc_fixture, server_down
) -> None:
    """SINAN rows carry the notification year, not the file's; the scope is `_source_ano`."""
    chagas = sus.resolve("sinan_chagas")
    payload = dbc_fixture("sinan_chagas_br_2023").read_bytes()
    fake_datasus.serve(monkeypatch, chagas, {ScopeKey(uf=None, ano=2023): payload})
    with pytest.warns(UserWarning, match="harmonised"):
        loaded = sus.load(chagas, years=[2023], target=target)
    server_down()

    with pytest.warns(UserWarning, match="harmonised"):
        dados = sus.read(chagas, years=[2023], target=target)

    assert dados.height == 6253
    assert dados.equals(loaded)


def test_read_a_monthly_dataset_returns_only_the_requested_months(
    target: str, monkeypatch, dbc_fixture, server_down
) -> None:
    """RDRR2401 served as January and February of 2024; read asks for January."""
    payload = dbc_fixture("sih_rr_2024_01_mini").read_bytes()
    months = {ScopeKey(uf="RR", ano=2024, mes=m): payload for m in (1, 2)}
    fake_datasus.serve(monkeypatch, "sih_aih_reduzida", months)
    with pytest.warns(UserWarning, match="harmonised"):
        sus.load("sih_aih_reduzida", years=[2024], ufs=["RR"], months=[1, 2], target=target)
    server_down()

    with pytest.warns(UserWarning, match="harmonised"):
        dados = sus.read("sih_aih_reduzida", years=[2024], ufs=["RR"], months=[1], target=target)

    assert dados.height == 3714
    assert set(dados["mes"]) == {1}


def test_read_validates_ufs_and_months_like_load() -> None:
    with pytest.raises(ValueError, match=r"ufs=.*sus\.ALL_UFS"):
        sus.read("sim_obitos", years=[2023])
    with pytest.raises(ValueError, match="national"):
        sus.read("sinan_chagas", years=[2023], ufs=["RR"])
    with pytest.raises(ValueError, match=r"years="):
        sus.read("sim_obitos", ufs=["RR"])
