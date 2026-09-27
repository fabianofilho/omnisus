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
