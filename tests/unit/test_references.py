"""Declared references hold on real data.

Every field whose ``foreignKeys`` points at a bootstrap table is joined with
``reference_join_sql`` over its real mini fixture. The join must not multiply rows, and
the non-blank values that find no row are listed exactly.
"""

from __future__ import annotations

import io
import json
import zipfile
from importlib.resources import files

import duckdb
import polars as pl
import pytest

import omnisus as sus
from omnisus.sources.datasus_ftp.dbc import decompress_bytes
from omnisus.sources.datasus_ftp.dbf_contract import _read_field_descriptors
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.dictionaries import load_dicionario

CNV = files("omnisus.data.dicionarios") / "sources" / "cnv"
BOOTSTRAP = {"aux_uf", "aux_municipios", "aux_cid10", "aux_ocupacoes", "aux_paises"}

# (dataset, fixture, ano, uf) -> every (field, value, rows) that finds no reference row.
# Counted 2026-09-22. SIH writes 0000 where there is no secondary, associated or death
# cause; 150475 (Mojuí dos Campos, PA) was installed after the 2011 CADMUN on the server.
# SIA (2026-10-07, #82): 0000 is "CID NAO INFORMADO" in S_CID.DBF of TAB_SIA.zip, not a
# CID-10 code.
UNRESOLVED: dict[tuple[str, str, int, str], list[tuple[str, str, int]]] = {
    ("cnes_estabelecimentos", "cnes_rr_2024_01_mini", 2024, "RR"): [],
    ("sih_aih_reduzida", "sih_rr_2024_01_mini", 2024, "RR"): [
        ("diag_secun", "0000", 3714),
        ("cid_asso", "0000", 3714),
        ("cid_morte", "0000", 3714),
    ],
    # Layout 6 (RDRR2503 excerpt): the same three fields, and diag_princ and diagsec1-8
    # checked on 2025 data.
    ("sih_aih_reduzida", "sih_rd_rr_2025_03_excerpt", 2025, "RR"): [
        ("diag_secun", "0000", 30),
        ("cid_asso", "0000", 30),
        ("cid_morte", "0000", 30),
    ],
    ("sim_obitos", "sim_rr_2023_mini", 2023, "RR"): [("codmunnatu", "150475", 1)],
    ("sinasc_nascidos_vivos", "sinasc_rr_2022_mini", 2022, "RR"): [],
    ("sia_producao_ambulatorial", "sia_pa_rr_2024_01_mini", 2024, "RR"): [
        ("pa_cidpri", "0000", 14540),
        ("pa_cidsec", "0000", 21310),
        ("pa_cidcas", "0000", 19644),
    ],
    # PARR0712 writes 0 in both CID fields of every row with pa_docorig 'B'; S_CID calls
    # it "CID NÃO IDENTIFICADO" (evidence/2026-10-07-sia-cid-widths/values.csv).
    ("sia_producao_ambulatorial_1994_2007", "sia_pa_rr_2007_12_mini", 2007, "RR"): [
        ("pa_cidpri", "0", 14123),
        ("pa_cidsec", "0", 14123),
    ],
    ("sia_apac_quimioterapia", "sia_aq_rr_2024_01_mini", 2024, "RR"): [
        ("ap_cidcas", "0000", 17),
        ("ap_cidsec", "0000", 17),
    ],
    ("sia_apac_radioterapia", "sia_ar_ac_2024_01_mini", 2024, "AC"): [
        ("ap_cidcas", "0000", 39),
        ("ap_cidsec", "0000", 39),
    ],
    ("sia_apac_radioterapia", "sia_ar_sp_2022_12_excerpt", 2022, "SP"): [
        ("ap_cidcas", "0000", 1),
        ("ap_cidsec", "0000", 1),
    ],
    ("sia_apac_laudos_diversos", "sia_ad_rr_2024_01_mini", 2024, "RR"): [
        ("ap_cidcas", "0000", 667),
        ("ap_cidsec", "0000", 661),
    ],
    ("sia_apac_laudos_diversos", "sia_ad_sp_2022_10_excerpt", 2022, "SP"): [
        ("ap_cidcas", "0000", 1),
        ("ap_cidsec", "0000", 1),
    ],
    ("sia_apac_laudos_diversos", "sia_ad_sp_2022_12_excerpt", 2022, "SP"): [
        ("ap_cidcas", "0000", 2),
        ("ap_cidpri", "0000", 2),
        ("ap_cidsec", "0000", 2),
    ],
    ("sia_apac_medicamentos", "sia_am_rr_2024_01_mini", 2024, "RR"): [
        ("ap_cidcas", "0000", 2083),
        ("ap_cidsec", "0000", 2083),
    ],
    ("sia_apac_nefrologia", "sia_an_pa_2014_10_mini", 2014, "PA"): [
        ("ap_cidcas", "0000", 2),
        ("ap_cidsec", "0000", 2),
    ],
    ("sia_apac_tratamento_dialitico", "sia_atd_rr_2024_01_mini", 2024, "RR"): [
        ("ap_cidcas", "0000", 342),
        ("ap_cidpri", "0000", 358),
        ("ap_cidsec", "0000", 358),
    ],
    ("sia_atencao_domiciliar", "sia_sad_ma_2018_10_mini", 2018, "MA"): [],
    ("sia_psicossocial", "sia_ps_rr_2024_01_mini", 2024, "RR"): [],
    ("sia_psicossocial", "sia_ps_sp_2022_12_a_excerpt", 2022, "SP"): [],
    ("sia_psicossocial", "sia_ps_sp_2022_12_b_excerpt", 2022, "SP"): [],
}


@pytest.fixture(scope="module")
def con():
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS lake")
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for table in BOOTSTRAP:
            frame = pl.read_parquet(io.BytesIO(zf.read(f"{table}.parquet")))
            con.register("staged", frame.to_arrow())
            con.execute(f"CREATE TABLE lake.{table} AS SELECT * FROM staged")
            con.unregister("staged")
    yield con
    con.close()


def referenced_fields(dataset: str) -> list[str]:
    return [
        field["name"]
        for field in load_dicionario(dataset).fields
        if any(fk["reference"]["resource"] in BOOTSTRAP for fk in field.get("foreignKeys", []))
    ]


@pytest.mark.parametrize(("dataset", "fixture", "ano", "uf"), sorted(UNRESOLVED))
def test_declared_references_resolve_on_real_fixtures(con, dbc_fixture, dataset, fixture, ano, uf):
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture(fixture).read_bytes(), dataset=dataset, ano=ano, uf=uf
    ).collect()
    con.register("d", frame.to_arrow())
    found = []
    for field in referenced_fields(dataset):
        if field not in frame.columns:  # declared for other years of the layout
            continue
        join = sus.reference_join_sql(dataset, field, alias="d")
        joined = con.execute(f"SELECT count(*) FROM d {join}").fetchone()
        assert joined == (frame.height,), f"{dataset}.{field} multiplies rows"
        ref = f"ref_{field}"
        key = next(fk for fk in (load_dicionario(dataset).field_def(field) or {})["foreignKeys"])
        found += [
            (field, value, rows)
            for value, rows in con.execute(
                f'SELECT d."{field}", count(*) FROM d {join} '
                f'WHERE d."{field}" IS NOT NULL AND d."{field}" <> \'\' '
                f'AND {ref}."{key["reference"]["fields"]}" IS NULL GROUP BY 1 ORDER BY 1'
            ).fetchall()
        ]
    con.unregister("d")
    assert found == UNRESOLVED[(dataset, fixture, ano, uf)]


@pytest.mark.parametrize(("dataset", "fixture", "ano", "uf"), sorted(UNRESOLVED))
def test_a_declared_reference_fits_the_published_field(
    con, dbc_fixture, dataset, fixture, ano, uf
):
    """A field narrower than every key of its reference never joins, filled or not (#67).

    The width is the DBF header's, so the check holds even where the fixture leaves the
    field blank in every row."""
    dbf = decompress_bytes(dbc_fixture(fixture).read_bytes())
    widths = {f.name.strip().lower(): f.width for f in _read_field_descriptors(dbf)}
    narrow = []
    for field in referenced_fields(dataset):
        if field not in widths:  # declared for other years of the layout
            continue
        fk = next(iter((load_dicionario(dataset).field_def(field) or {})["foreignKeys"]))
        table, key = fk["reference"]["resource"], fk["reference"]["fields"]
        (shortest,) = con.execute(f'SELECT min(length("{key}")) FROM lake.{table}').fetchone()
        if widths[field] < shortest:
            narrow.append((field, widths[field], f"{table}.{key}", shortest))
    assert narrow == []


def test_secondary_diagnoses_declare_the_cid10_reference(con, dbc_fixture):
    """RD2008.DEF, lines 389-406, relates DIAGSEC1-9 to DBF/CID10.DBF (IT_SIHSUS_1603, p. 4:
    "Diagnóstico secundário N"). DIAGSEC1-8 declare aux_cid10 and every filled code of
    RDRR2401 finds its row. DIAGSEC9 is C(1) in the 157 RD files read from 2014-01 to
    2026-07 (evidence/2026-10-06-rd-2008-layouts), too narrow for any CID-10 code, so it declares
    no reference and says why (#67). The UNRESOLVED list above cannot see a lost
    reference: a field without foreignKeys is skipped there, so this test counts the joins
    itself."""
    fields = [f"diagsec{n}" for n in range(1, 9)]
    assert set(fields) <= set(referenced_fields("sih_aih_reduzida"))
    diagsec9 = load_dicionario("sih_aih_reduzida").field_def("diagsec9")
    assert "foreignKeys" not in diagsec9
    (issue,) = [i for i in diagsec9["x-metadata"]["issues"] if i["id"] == "diagsec9-c1"]
    assert issue["status"] == "open"
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture("sih_rr_2024_01_mini").read_bytes(),
        dataset="sih_aih_reduzida",
        ano=2024,
        uf="RR",
    ).collect()
    # (filled, resolved); diagsec3-8 are blank in every row of the file.
    assert _filled_and_resolved(con, frame, "sih_aih_reduzida", fields) == {
        "diagsec1": (622, 622),
        "diagsec2": (15, 15),
    } | {f"diagsec{n}": (0, 0) for n in range(3, 9)}


# (dataset, fixture, ano, uf) -> {field: (filled, resolved)} on the real fixture (#82).
# Every field the dataset's DEF relates to S_CID.DBF declares aux_cid10; fields blank in
# every row of the fixture are listed as (0, 0) instead of being skipped. The CID fields
# of PA, AQ and AR are C(4) in every file of the census in
# evidence/2026-10-07-sia-cid-widths (PA of RR, AQ and AR of AL, 2008-01 to 2026-07);
# those of the other datasets are C(4) in every fixture listed here, and
# test_a_declared_reference_fits_the_published_field checks each fixture's header.
SIA_CID = {
    ("sia_producao_ambulatorial", "sia_pa_rr_2024_01_mini", 2024, "RR"): {
        "pa_cidpri": (21341, 6801),
        "pa_cidsec": (21341, 31),
        "pa_cidcas": (19680, 36),
    },
    # PARR0712, the whole file: the 14,123 rows with pa_docorig 'B' hold 0 in both fields.
    ("sia_producao_ambulatorial_1994_2007", "sia_pa_rr_2007_12_mini", 2007, "RR"): {
        "pa_cidpri": (15945, 1822),
        "pa_cidsec": (14368, 245),
    },
    ("sia_apac_quimioterapia", "sia_aq_rr_2024_01_mini", 2024, "RR"): {
        "ap_cidpri": (17, 17),
        "ap_cidsec": (17, 0),
        "ap_cidcas": (17, 0),
        "aq_cid10": (0, 0),
        "aq_cidini1": (1, 1),
        "aq_cidini2": (0, 0),
        "aq_cidini3": (0, 0),
    },
    ("sia_apac_radioterapia", "sia_ar_ac_2024_01_mini", 2024, "AC"): {
        "ap_cidpri": (39, 39),
        "ap_cidsec": (39, 0),
        "ap_cidcas": (39, 0),
        "ar_cid10": (0, 0),
        "ar_cidini1": (0, 0),
        "ar_cidini2": (0, 0),
        "ar_cidini3": (0, 0),
        "ar_cidtr1": (39, 39),
        "ar_cidtr2": (0, 0),
        "ar_cidtr3": (0, 0),
    },
    # ARSP2212: the only fixture where ar_cid10 is filled.
    ("sia_apac_radioterapia", "sia_ar_sp_2022_12_excerpt", 2022, "SP"): {
        "ap_cidpri": (1, 1),
        "ap_cidsec": (1, 0),
        "ap_cidcas": (1, 0),
        "ar_cid10": (1, 1),
        "ar_cidini1": (0, 0),
        "ar_cidini2": (0, 0),
        "ar_cidini3": (0, 0),
        "ar_cidtr1": (1, 1),
        "ar_cidtr2": (0, 0),
        "ar_cidtr3": (0, 0),
    },
    ("sia_apac_laudos_diversos", "sia_ad_rr_2024_01_mini", 2024, "RR"): {
        "ap_cidpri": (678, 678),
        "ap_cidsec": (678, 17),
        "ap_cidcas": (678, 11),
    },
    ("sia_apac_laudos_diversos", "sia_ad_sp_2022_10_excerpt", 2022, "SP"): {
        "ap_cidpri": (1, 1),
        "ap_cidsec": (1, 0),
        "ap_cidcas": (1, 0),
    },
    ("sia_apac_laudos_diversos", "sia_ad_sp_2022_12_excerpt", 2022, "SP"): {
        "ap_cidpri": (2, 0),
        "ap_cidsec": (2, 0),
        "ap_cidcas": (2, 0),
    },
    ("sia_apac_medicamentos", "sia_am_rr_2024_01_mini", 2024, "RR"): {
        "ap_cidpri": (2083, 2083),
        "ap_cidsec": (2083, 0),
        "ap_cidcas": (2083, 0),
    },
    ("sia_apac_nefrologia", "sia_an_pa_2014_10_mini", 2014, "PA"): {
        "ap_cidpri": (2, 2),
        "ap_cidsec": (2, 0),
        "ap_cidcas": (2, 0),
    },
    ("sia_apac_tratamento_dialitico", "sia_atd_rr_2024_01_mini", 2024, "RR"): {
        "ap_cidpri": (358, 0),
        "ap_cidsec": (358, 0),
        "ap_cidcas": (358, 16),
    },
    ("sia_atencao_domiciliar", "sia_sad_ma_2018_10_mini", 2018, "MA"): {
        "cidpri": (11, 11),
        "cidassoc": (0, 0),
        "pa_cid": (2, 2),
    },
    ("sia_psicossocial", "sia_ps_rr_2024_01_mini", 2024, "RR"): {
        "cidpri": (1670, 1670),
        "cidassoc": (9, 9),
    },
    ("sia_psicossocial", "sia_ps_sp_2022_12_a_excerpt", 2022, "SP"): {
        "cidpri": (30, 30),
        "cidassoc": (0, 0),
    },
    ("sia_psicossocial", "sia_ps_sp_2022_12_b_excerpt", 2022, "SP"): {
        "cidpri": (17, 17),
        "cidassoc": (2, 2),
    },
}


# Datasets with no archived DEF, so no DEF line says which fields relate to S_CID.DBF:
# the DEFs of 1994-07 to 2007-12 are in SIASUS/200801_/Auxiliar/TAB_SIA_199407-199910.zip
# and the two archives after it, which the repo has not read (docs/sources/sia.md). Their
# SIA_CID fields are the CID fields of the census instead
# (evidence/2026-10-07-sia-cid-widths/README.md: PA_CIDPRI and PA_CIDSEC).
NO_ARCHIVED_DEF = {"sia_producao_ambulatorial_1994_2007"}


@pytest.mark.parametrize(("dataset", "fixture", "ano", "uf"), sorted(SIA_CID))
def test_sia_cid_fields_declare_the_cid10_reference(con, dbc_fixture, dataset, fixture, ano, uf):
    """The DEF that vinculos.json gives the dataset relates these fields, and no other, to
    S_CID.DBF of TAB_SIA.zip (#82). Each declares aux_cid10, and the joins are counted
    here because UNRESOLVED skips a field without foreignKeys. A dataset in
    NO_ARCHIVED_DEF has no DEF to compare with, and the test fails once vinculos.json
    gives it one, so the DEF check is not skipped by mistake."""
    expected = SIA_CID[(dataset, fixture, ano, uf)]
    if dataset in NO_ARCHIVED_DEF:
        vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
        assert dataset not in vinculos["datasets"]
    else:
        assert s_cid_fields(dataset) == set(expected)
    assert set(referenced_fields(dataset)) == set(expected)
    dictionary = load_dicionario(dataset)
    assert {f: dictionary.field_def(f)["foreignKeys"] for f in expected} == {
        f: [{"fields": f, "reference": {"resource": "aux_cid10", "fields": "codigo"}}]
        for f in expected
    }
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture(fixture).read_bytes(), dataset=dataset, ano=ano, uf=uf
    ).collect()
    assert _filled_and_resolved(con, frame, dataset, expected) == expected


def s_cid_fields(dataset: str) -> set[str]:
    """Fields that a line of the dataset's DEF relates to S_CID.DBF.

    Not `parse_def_lookups`: Producao_Ambulatorial.DEF writes the lookup twice on one
    line (`PA_CIDPRI, CD_DESCR, DBF/S_CID.DBF, CD_DESCR, DBF/S_CID.DBF`), a shape it
    refuses."""
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    fields = set()
    for member in vinculos["datasets"][dataset]["def"]:
        for line in (CNV / member).read_bytes().decode("latin-1").splitlines():
            parts = [part.strip() for part in line.split(",")]
            if any(p.upper().replace("\\", "/").endswith("S_CID.DBF") for p in parts[2:]):
                fields.add(parts[1].lower())
    return fields


def _filled_and_resolved(con, frame, dataset, fields):
    """Field -> (filled, resolved): the field's rows that are not blank, and those whose
    reference_join_sql finds a row."""
    con.register("d", frame.to_arrow())
    counted = {}
    for field in fields:
        assert field in frame.columns, f"{field} missing from the fixture"
        join = sus.reference_join_sql(dataset, field, alias="d")
        counted[field] = con.execute(
            f"SELECT count(*) FILTER (WHERE d.\"{field}\" <> ''), count(ref_{field}.codigo) "
            f"FROM d {join}"
        ).fetchone()
    con.unregister("d")
    return counted


def test_occupation_joins_cbo2002_from_2006_only(con, dbc_fixture):
    """SIM ``ocup`` resolves against CBO 2002 in 2023; TABOCUP titles never join."""
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture("sim_rr_2023_mini").read_bytes(), dataset="sim_obitos", ano=2023, uf="RR"
    ).collect()
    con.register("d", frame.to_arrow())
    join = sus.reference_join_sql("sim_obitos", "ocup", alias="d")
    rows = con.execute(
        f"SELECT ref_ocup.esquema, count(*) FROM d {join} WHERE d.ocup = '622020' GROUP BY 1"
    ).fetchall()
    assert rows == [("cbo2002", rows[0][1])] and rows[0][1] > 0
    frame_2005 = frame.with_columns(pl.lit(2005).alias("ano"))
    con.register("d", frame_2005.to_arrow())
    assert con.execute(
        f"SELECT count(ref_ocup.codigo) FROM d {join} WHERE d.ocup <> ''"
    ).fetchone() == (0,)
    con.unregister("d")


def test_reference_join_sql_names_the_resource_and_rule():
    assert sus.reference_join_sql("sim_obitos", "ocup", alias="d") == (
        'LEFT JOIN "lake"."aux_ocupacoes" AS "ref_ocup" '
        'ON d."ocup" = "ref_ocup"."codigo" '
        "AND (\"ref_ocup\".esquema = 'cbo2002' AND d.ano >= 2006)"
    )
    with pytest.raises(ValueError, match="no reference"):
        sus.reference_join_sql("sim_obitos", "dtobito")
