"""Tests for the APAC family datasets (AM, AQ, ATD, AD, ABO) + RAAS-PS.

Stress scenarios these tests encode (all field-measured, 2026-08):

- prefix ambiguity: AM/AQ/AD are 2-letter, ATD/ABO are 3-letter; the
  monthly filename regex must backtrack correctly (AMRR2401 is AM+RR,
  ATDRR2401 is ATD+RR, ABOSP2401 is ABO+SP — never AB+OS).
- ABO schema drift: 86 header fields of which 8 are UNNAMED trailers that
  dbfread2 silently drops (78 parsed columns), and the AP_* core uses
  variant names (AP_TPPRE, AP_APACAN, AP_DTOOCOR, CO_CIDPRIM).
- expected record counts come from each fixture's DBF header (nrec),
  independently verified against parsed rows by the integrity gate.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest

from omnisus.sources import sigtap
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, resolve
from omnisus.sources.datasus_ftp.filenames import decode_for
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.cnv import cnv_map, parse_cnv, parse_def, parse_def_lookups
from omnisus.transforms.dictionaries import load_dicionario
from tests.support.datasus_names import filename_for

# dataset -> (fixture name, measured nrec, measured parsed column floor)
FIXTURES = {
    "sia_apac_medicamentos": ("sia_am_rr_2024_01_mini", 2_083, 51),
    "sia_apac_quimioterapia": ("sia_aq_rr_2024_01_mini", 17, 74),
    "sia_apac_tratamento_dialitico": ("sia_atd_rr_2024_01_mini", 358, 65),
    "sia_apac_laudos_diversos": ("sia_ad_rr_2024_01_mini", 678, 46),
    "sia_apac_cirurgia_bariatrica": ("sia_abo_sp_2024_01_mini", 844, 78),
    "sia_psicossocial": ("sia_ps_rr_2024_01_mini", 1_670, 45),
}


# ---------------------------------------------------------------------------
# inventory: prefix ambiguity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "dataset", "uf"),
    [
        ("AMRR2401.dbc", "sia_apac_medicamentos", "RR"),
        ("AQRR2401.dbc", "sia_apac_quimioterapia", "RR"),
        ("ADRR2401.dbc", "sia_apac_laudos_diversos", "RR"),
        ("ATDRR2401.dbc", "sia_apac_tratamento_dialitico", "RR"),  # 3-letter, backtrack from ATDR
        ("ABOSP2401.dbc", "sia_apac_cirurgia_bariatrica", "SP"),  # 3-letter, never AB+OS
        ("PSRR2401.dbc", "sia_psicossocial", "RR"),
        ("BIRR2401.dbc", "sia_bpa_individualizado", "RR"),  # regression: BI still parses
        ("RDRR2401.dbc", "sih_aih_reduzida", "RR"),  # regression: SIH untouched
    ],
)
def test_decode_for_disambiguates_prefixes(filename: str, dataset: str, uf: str) -> None:
    scope = decode_for(REGISTRY[dataset], filename)
    assert scope == ScopeKey(uf=uf, ano=2024, mes=1)


@pytest.mark.parametrize("dataset", list(FIXTURES))
def test_scope_roundtrip(dataset: str) -> None:
    scope = ScopeKey(uf="RR", ano=2024, mes=1)
    filename = filename_for(resolve(dataset), scope)
    back_scope = decode_for(REGISTRY[dataset], filename)
    assert back_scope == scope


# ---------------------------------------------------------------------------
# registry + dicionários
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dataset", list(FIXTURES))
def test_registry_monthly_uf_partition(dataset: str) -> None:
    cfg = resolve(dataset)
    assert cfg.monthly is True
    assert cfg.partition_by == ("ano", "uf", "mes")


@pytest.mark.parametrize("dataset", list(FIXTURES))
def test_dicionario_latin1_and_cns_marker(dataset: str) -> None:
    dic = load_dicionario(dataset)
    assert dic.encoding == "latin-1"
    crypto = [f["name"] for f in dic.fields if f.get("x-crypto") == "datasus-cns"]
    assert crypto, f"{dataset}: no field marked x-crypto datasus-cns"


def test_apac_core_shares_linkage_fields() -> None:
    """Every APAC dicionário exposes the person/clinical core (variant-aware)."""
    for dataset in (
        "sia_apac_medicamentos",
        "sia_apac_quimioterapia",
        "sia_apac_tratamento_dialitico",
        "sia_apac_laudos_diversos",
    ):
        names = {f["name"] for f in load_dicionario(dataset).fields}
        assert {"ap_cnspcn", "ap_cidpri", "ap_pripal", "ap_obito", "ap_ceppcn"} <= names
    # ABO variant core
    abo = {f["name"] for f in load_dicionario("sia_apac_cirurgia_bariatrica").fields}
    assert {"ap_cnspcn", "co_cidprim", "ab_numaih"} <= abo


# ---------------------------------------------------------------------------
# parse: real fixtures, exact header counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("dataset", "spec"), FIXTURES.items())
def test_parse_fixture_exact_counts(dataset: str, spec, dbc_fixture) -> None:
    fixture, nrec, min_cols = spec
    uf = "SP" if "sp" in fixture else "RR"
    df = dbc_bytes_to_lazyframe(
        dbc_fixture(fixture).read_bytes(), dataset=dataset, ano=2024, uf=uf
    ).collect()
    assert df.height == nrec
    assert len(df.columns) >= min_cols + 2  # +ano +uf
    assert df["uf"].unique().to_list() == [uf]


def test_abo_unnamed_trailer_fields_are_dropped(dbc_fixture) -> None:
    """86 header fields, 8 unnamed -> exactly 78 data columns (+ano/uf)."""
    df = dbc_bytes_to_lazyframe(
        dbc_fixture("sia_abo_sp_2024_01_mini").read_bytes(),
        dataset="sia_apac_cirurgia_bariatrica",
        ano=2024,
        uf="SP",
    ).collect()
    assert len(df.columns) == 78 + 2
    assert "ab_numaih" in df.columns
    # gold-standard bridge: every row carries a 13-digit AIH number
    aihs = [v for v in df["ab_numaih"].to_list() if v and v.strip()]
    assert len(aihs) == df.height
    assert all(len(v.strip()) == 13 for v in aihs)


def test_am_dates_and_competencia_formats(dbc_fixture) -> None:
    df = dbc_bytes_to_lazyframe(
        dbc_fixture("sia_am_rr_2024_01_mini").read_bytes(), dataset="sia_apac_medicamentos"
    ).collect()
    assert df["ap_cmp"].head(50).str.len_chars().unique().to_list() == [6]  # AAAAMM
    inic = [v for v in df["ap_dtinic"].head(100).to_list() if v and v.strip()]
    assert all(len(v) == 8 and v[:2] in ("19", "20") for v in inic)  # AAAAMMDD


# ---------------------------------------------------------------------------
# linkage: the encrypted patient CNS across SIA families
# ---------------------------------------------------------------------------


def test_cross_family_cns_intersection_rr(dbc_fixture) -> None:
    """The encrypted patient CNS, compared as published, is an exact key across families.

    Nothing is decrypted. docs/sources/sia.md states these counts for the RR
    2024-01 fixtures; evidence/2026-09-23-linkage-ampliado.md shows that the
    same value in two families agrees on sex and age.
    """

    def cns(fixture: str, dataset: str, field: str) -> set[str]:
        df = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
        return {v for v in df[field].to_list() if v.strip()}

    bpa_i = cns("sia_bi_rr_2024_01_mini", "sia_bpa_individualizado", "cns_pac")
    medicamentos = cns("sia_am_rr_2024_01_mini", "sia_apac_medicamentos", "ap_cnspcn")
    psicossocial = cns("sia_ps_rr_2024_01_mini", "sia_psicossocial", "cns_pac")
    assert len(bpa_i & medicamentos) == 312
    assert len(bpa_i & psicossocial) == 56


# ---------------------------------------------------------------------------
# bariatric follow-up: AB and ABO, and the TAB_SIA DEF that reads each
# ---------------------------------------------------------------------------

_CNV = files("omnisus.data.dicionarios") / "sources" / "cnv"
_VINCULOS = json.loads((_CNV / "vinculos.json").read_text("utf-8"))
_POS_DEF = "APAC_Pos_Cirurgia_Bariatica.def"
_CIR_DEF = "APAC_Cirurgia_Bariatica.DEF"
# dataset -> (fixture, the DEF whose line 3 reads its files)
_BARIATRIC = {
    "sia_apac_acompanhamento_bariatrica": ("sia_ab_se_2025_07_mini", _CIR_DEF),
    "sia_apac_cirurgia_bariatrica": ("sia_abo_sp_2024_01_mini", _POS_DEF),
}


def _def_text(name: str) -> str:
    return (_CNV / "sia" / name).read_bytes().decode("latin-1")


def _bariatric_frame(dbc_fixture, dataset: str):
    fixture = _BARIATRIC[dataset][0]
    return dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()


def test_each_bariatric_def_reads_the_family_vinculos_gives_it(dbc_fixture) -> None:
    """TAB_SIA.zip: line 3 of APAC_Cirurgia_Bariatica.DEF reads `DADOS\\AB*.DBC`, line 3
    of APAC_Pos_Cirurgia_Bariatica.def reads `DADOS\\ABO*.DBF`. Only the Pos DEF binds the
    13 follow-up fields below; the ABO file of SP has all of them, the AB file of SE none.

    The two DEFs disagree on the names of the common APAC fields (the Pos DEF binds
    AP_DTOCOR and AP_TPATEN, as AB publishes them; the other DEF CO_CIDPRIM and
    AP_TPATEND, as ABO does), so those names cannot tell the DEFs apart. Swapping the
    DEFs in vinculos.json fails here.
    """
    assert _def_text(_CIR_DEF).splitlines()[2] == "ADADOS\\AB*.DBC"
    assert _def_text(_POS_DEF).splitlines()[2] == "ADADOS\\ABO*.DBF"

    def bound(name: str) -> set[str]:
        text = _def_text(name)
        return {b.field for b in parse_def(text)} | {b.field for b in parse_def_lookups(text)}

    def header(dataset: str) -> set[str]:
        return {name.upper() for name in _bariatric_frame(dbc_fixture, dataset).columns}

    follow_up = {
        "AB_PRCAIH4", "AB_PRCAIH5", "AB_PRCAIH6", "AP_MEDICAM", "AP_POLIVIT", "AP_ATV_FIS",
        "AP_REG_PES", "AP_ADESAO", "AP_CID_C1", "AP_CID_C2", "AP_CID_C3", "AP_CID_C4",
        "AP_CID_C5",
    }  # fmt: skip
    assert follow_up <= bound(_POS_DEF) - bound(_CIR_DEF)
    assert follow_up <= header("sia_apac_cirurgia_bariatrica")
    assert not follow_up & header("sia_apac_acompanhamento_bariatrica")
    for dataset, (_, def_name) in _BARIATRIC.items():
        assert _VINCULOS["datasets"][dataset]["def"] == [f"sia/{def_name}"]


def test_abo_is_the_post_surgery_follow_up_and_its_title_says_so(dbc_fixture) -> None:
    """Every row of ABOSP2401 has AP_PRIPAL 0301120056, which SIGTAP 2008-01 names
    'ACOMPANHAMENTO DE PACIENTE POS- CIRURGIA BARIATRICA'; AB_PROCAIH holds the SIH
    surgery (0407010173, a gastroplasty, in 837 of 844 rows). The dataset keeps its name, which an API
    change would take, and only its title says what the file holds."""
    df = _bariatric_frame(dbc_fixture, "sia_apac_cirurgia_bariatrica")
    assert set(df["ap_pripal"]) == {"0301120056"}
    assert df["ab_procaih"].to_list().count("0407010173") == 837
    zip_200801 = Path(__file__).resolve().parents[3] / "fixtures/sigtap/TabelaUnificada_200801.zip"
    procedimentos = sigtap.read_procedimentos(zip_200801.read_bytes())
    names = dict(procedimentos.select("co_procedimento", "no_procedimento").iter_rows())
    assert names["0301120056"] == "ACOMPANHAMENTO DE PACIENTE POS- CIRURGIA BARIATRICA"
    assert names["0407010173"] == "GASTROPLASTIA C/ DERIVACAO INTESTINAL"
    title = load_dicionario("sia_apac_cirurgia_bariatrica").title
    assert title == "SIASUS — APAC de Acompanhamento Pós-Cirurgia Bariátrica (ABO)"


# field -> (CNV both bariatric DEFs bind it to, a code of the fixtures, its label)
_SHARED_LABELS = {
    "ap_catend": ("CARAT_AT.CNV", "01", "ELETIVO"),
    "ap_condic": ("TP_GESTAO.CNV", "PG", "PG Pacto de Gestão"),
    "ap_motsai": ("MOTSAIPE.CNV", "21", "PERMANÊNCIA POR CARACTERÍSTICAS PRÓPRIAS DA DOENÇA"),
    "ap_tpups": ("TP_ESTAB.CNV", "05", "HOSPITAL GERAL"),
}


@pytest.mark.parametrize("dataset", sorted(_BARIATRIC))
@pytest.mark.parametrize("field", sorted(_SHARED_LABELS))
def test_bariatric_labels_come_from_the_cnv_each_def_binds(dbc_fixture, dataset, field) -> None:
    """Each bariatric DEF binds the field at column 1 to the same packaged CNV; the
    dictionary holds that CNV's map, and every value of the AB file of SE and of the ABO
    file of SP is one of its keys. SP is the only committed ABO file:
    evidence/2026-10-08-cns-vazio-sia records only hashes and counts of the others."""
    member, code, label = _SHARED_LABELS[field]
    bindings = {(b.field, b.start, b.table) for b in parse_def(_def_text(_BARIATRIC[dataset][1]))}
    assert (field.upper(), 1, f"CNV/{member}") in bindings
    cnv = cnv_map(parse_cnv((_CNV / "sia" / "CNV" / member).read_bytes().decode("latin-1")))
    decode = load_dicionario(dataset).field_def(field).get("x-decode")
    assert decode == cnv
    assert set(_bariatric_frame(dbc_fixture, dataset)[field]) <= decode.keys()
    assert decode[code] == label
