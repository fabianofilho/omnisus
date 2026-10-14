"""Declared references hold on real data.

Every field whose ``foreignKeys`` points at a bootstrap table is joined with
``reference_join_sql`` over its real mini fixture. The join must not multiply rows, and
the non-blank values that find no row are listed exactly.
"""

from __future__ import annotations

import io
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

BOOTSTRAP = {"aux_uf", "aux_municipios", "aux_cid10", "aux_ocupacoes", "aux_paises"}

# (dataset, fixture, ano) -> every (field, value, rows) that finds no reference row.
# Counted 2026-09-22. SIH writes 0000 where there is no secondary, associated or death
# cause; 150475 (Mojuí dos Campos, PA) was installed after the 2011 CADMUN on the server.
UNRESOLVED: dict[tuple[str, str, int], list[tuple[str, str, int]]] = {
    ("cnes_estabelecimentos", "cnes_rr_2024_01_mini", 2024): [],
    ("sih_aih_reduzida", "sih_rr_2024_01_mini", 2024): [
        ("diag_secun", "0000", 3714),
        ("cid_asso", "0000", 3714),
        ("cid_morte", "0000", 3714),
    ],
    # Layout 6 (RDRR2503 excerpt): the same three fields, and diag_princ and diagsec1-8
    # checked on 2025 data.
    ("sih_aih_reduzida", "sih_rd_rr_2025_03_excerpt", 2025): [
        ("diag_secun", "0000", 30),
        ("cid_asso", "0000", 30),
        ("cid_morte", "0000", 30),
    ],
    ("sim_obitos", "sim_rr_2023_mini", 2023): [("codmunnatu", "150475", 1)],
    ("sinasc_nascidos_vivos", "sinasc_rr_2022_mini", 2022): [],
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


@pytest.mark.parametrize(("dataset", "fixture", "ano"), sorted(UNRESOLVED))
def test_declared_references_resolve_on_real_fixtures(con, dbc_fixture, dataset, fixture, ano):
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture(fixture).read_bytes(), dataset=dataset, ano=ano, uf="RR"
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
    assert found == UNRESOLVED[(dataset, fixture, ano)]


@pytest.mark.parametrize(("dataset", "fixture", "ano"), sorted(UNRESOLVED))
def test_a_declared_reference_fits_the_published_field(con, dbc_fixture, dataset, fixture, ano):
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
    con.register("d", frame.to_arrow())
    counted = {}
    for field in fields:
        assert field in frame.columns, f"{field} missing from RDRR2401"
        join = sus.reference_join_sql("sih_aih_reduzida", field, alias="d")
        counted[field] = con.execute(
            f"SELECT count(*) FILTER (WHERE d.\"{field}\" <> ''), count(ref_{field}.codigo) "
            f"FROM d {join}"
        ).fetchone()
    con.unregister("d")
    # (filled, resolved); diagsec3-8 are blank in every row of the file.
    assert counted == {"diagsec1": (622, 622), "diagsec2": (15, 15)} | {
        f"diagsec{n}": (0, 0) for n in range(3, 9)
    }


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
