from pathlib import Path

import polars as pl
import pytest

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.identity import validate_identity
from omnisus.transforms.dictionaries import Dicionario


def _dic(**identity) -> Dicionario:
    raw = {"name": "t", "schema": {"fields": []}}
    if identity:
        raw["x-identity"] = identity
    return Dicionario(
        name="t",
        title="t",
        encoding="latin-1",
        fields=[],
        primary_key=[],
        partitions=[],
        source_format="dbc",
        version="1",
        raw=raw,
    )


def _staging(tmp_path: Path, **columns) -> Path:
    p = tmp_path / "s.parquet"
    pl.DataFrame(columns).write_parquet(p)
    return p


SCOPE = ScopeKey(uf=None, ano=2025)


def test_no_block_means_no_check(tmp_path) -> None:
    validate_identity(_staging(tmp_path, nu_ano=["1999"]), _dic(), SCOPE)


def test_mode_of_year_must_equal_the_scope_year(tmp_path) -> None:
    ok = _staging(
        tmp_path, nu_ano=["2025", "2025", "2026"]
    )  # a few off-year records are normal (TB)
    validate_identity(ok, _dic(year_column="nu_ano"), SCOPE)
    bad = _staging(tmp_path, nu_ano=["2024", "2024", "2025"])
    with pytest.raises(ValueError, match="year"):
        validate_identity(bad, _dic(year_column="nu_ano"), SCOPE)


def test_missing_year_column_and_empty_file_are_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="nu_ano"):
        validate_identity(_staging(tmp_path, other=["x"]), _dic(year_column="nu_ano"), SCOPE)
    with pytest.raises(ValueError, match="empty"):
        validate_identity(
            _staging(tmp_path, nu_ano=pl.Series([], dtype=pl.String)),
            _dic(year_column="nu_ano"),
            SCOPE,
        )


def test_code_mode_must_match_when_the_column_exists(tmp_path) -> None:
    dic = _dic(year_column="nu_ano", code_column="id_agravo", code="A309")
    validate_identity(
        _staging(tmp_path, nu_ano=["2025"] * 3, id_agravo=["A309", "A309", "A30."]), dic, SCOPE
    )
    with pytest.raises(ValueError, match="A309"):
        validate_identity(
            _staging(tmp_path, nu_ano=["2025"] * 3, id_agravo=["", "", "A309"]), dic, SCOPE
        )  # AIDABR24 shape
    validate_identity(
        _staging(tmp_path, nu_ano=["2025"]), dic, SCOPE
    )  # pre-2007 layout: no code column


def test_values_are_trimmed_and_compared_as_text(tmp_path) -> None:
    validate_identity(
        _staging(tmp_path, nu_ano=[" 2025 "], id_agravo=[" A309"]),
        _dic(year_column="nu_ano", code_column="id_agravo", code="A309"),
        SCOPE,
    )


def _rr(ano: int = 2024, mes: int = 1) -> ScopeKey:
    return ScopeKey(uf="RR", ano=ano, mes=mes)


# (dataset, whole real file, its scope, month column, UF column). Modes measured 2026-09-23
# over the whole files: in every record the month column is the file's AAAAMM and the UF
# column starts with the file's UF code. APAC's ap_cmp is not the file's month (AQRR2401
# holds 202310 throughout); ap_mvm, the processing month, is.
SIA_IDENTITY = [
    ("sia_bpa_individualizado", "sia_bi_rr_2024_01_mini", _rr(), "dt_process", "ufmun"),
    ("sia_apac_medicamentos", "sia_am_rr_2024_01_mini", _rr(), "ap_mvm", "ap_ufmun"),
    ("sia_apac_quimioterapia", "sia_aq_rr_2024_01_mini", _rr(), "ap_mvm", "ap_ufmun"),
    ("sia_apac_tratamento_dialitico", "sia_atd_rr_2024_01_mini", _rr(), "ap_mvm", "ap_ufmun"),
    ("sia_apac_laudos_diversos", "sia_ad_rr_2024_01_mini", _rr(), "ap_mvm", "ap_ufmun"),
    (
        "sia_apac_cirurgia_bariatrica",
        "sia_abo_sp_2024_01_mini",
        ScopeKey(uf="SP", ano=2024, mes=1),
        "ap_mvm",
        "ap_ufmun",
    ),
    ("sia_psicossocial", "sia_ps_rr_2024_01_mini", _rr(), "dt_process", "ufmun"),
    ("sia_producao_ambulatorial", "sia_pa_rr_2024_01_mini", _rr(), "pa_mvm", "pa_ufmun"),
    (
        "sia_apac_acompanhamento_bariatrica",
        "sia_ab_se_2025_07_mini",
        ScopeKey(uf="SE", ano=2025, mes=7),
        "ap_mvm",
        "ap_ufmun",
    ),
    ("sia_apac_fistula_arteriovenosa", "sia_acf_rr_2024_01_mini", _rr(), "ap_mvm", "ap_ufmun"),
    (
        "sia_apac_acompanhamento_multiprofissional",
        "sia_amp_df_2024_01_mini",
        ScopeKey(uf="DF", ano=2024, mes=1),
        "ap_mvm",
        "ap_ufmun",
    ),
    (
        "sia_apac_nefrologia",
        "sia_an_pa_2014_10_mini",
        ScopeKey(uf="PA", ano=2014, mes=10),
        "ap_mvm",
        "ap_ufmun",
    ),
    (
        "sia_apac_radioterapia",
        "sia_ar_ac_2024_01_mini",
        ScopeKey(uf="AC", ano=2024, mes=1),
        "ap_mvm",
        "ap_ufmun",
    ),
    (
        "sia_atencao_domiciliar",
        "sia_sad_ma_2018_10_mini",
        ScopeKey(uf="MA", ano=2018, mes=10),
        "dt_process",
        "ufmun",
    ),
]


@pytest.mark.parametrize(("dataset", "fixture", "real", "month", "ufmun"), SIA_IDENTITY)
@pytest.mark.parametrize("wrong", ["uf", "month"])
def test_sia_bytes_of_another_uf_or_month_are_rejected(
    monkeypatch, tmp_path, dbc_fixture, dataset, fixture, real, month, ufmun, wrong
) -> None:
    """Served as another UF (MG) or another month of its coverage, a real SIA file fails
    instead of publishing."""
    import omnisus as sus
    from tests.support import fake_datasus

    scope = (
        ScopeKey(uf="MG", ano=real.ano, mes=real.mes)
        if wrong == "uf"
        else ScopeKey(uf=real.uf, ano=real.ano, mes=real.mes - 1 if real.mes > 1 else 2)
    )
    raw = dbc_fixture(fixture).read_bytes()
    fake_datasus.serve(monkeypatch, dataset, {scope: raw})
    report = sus.import_dataset(dataset, scopes=[scope], target=f"ducklake:{tmp_path}/x.ducklake")
    assert [o.code for o in report.outcomes] == ["ingest_failed"]
    assert (ufmun if wrong == "uf" else month) in (report.outcomes[0].reason or "")


def test_uf_codes_are_tabuf_codes() -> None:
    """UF_CODES (used by uf_column) equals TABUF.DBF as packaged in the bootstrap zip."""
    import io
    import zipfile
    from importlib.resources import files

    from omnisus.sources._base import ALL_UFS, UF_CODES

    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        tabuf = pl.read_parquet(io.BytesIO(zf.read("aux_uf.parquet")))
    assert dict(zip(tabuf["sigla"], tabuf["codigo_ibge"], strict=True)) == UF_CODES
    assert set(UF_CODES) == set(ALL_UFS)
