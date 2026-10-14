"""RD 1992-2007: the dictionary declares every field the era's DBF layouts publish (#30).

The files of `SIHSUS/199201_200712/Dados` the census read (one RR file a month, AP where
RR is missing, and SP and MG in the months a layout changes) have 19 layouts
(evidence/2026-10-01-rd-1992-2007-layouts/census.csv). Three whole RR files and an excerpt
of a fourth carry every field of them; each field is declared with the type
scripts/gen_dicionario.py gives it.

`diag_princ` holds CID-9 until 1997-12 and CID-10 from 1998-01, and the dictionary says so
(docs/sources/vocabularios.md, "CID-9 e CID-10 nos sistemas do SUS").
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from importlib.resources import files
from pathlib import Path

import polars as pl
import pytest
from scripts.gen_dicionario import fields_of

from omnisus.sources.datasus_ftp import dbc
from omnisus.sources.datasus_ftp.inventory import _parse_msdos_line
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.cnv import parse_def
from omnisus.transforms.dictionaries import load_dicionario
from tests.support.listings import listing_lines

ROOT = Path(__file__).resolve().parents[3]
CENSUS = ROOT / "evidence/2026-10-01-rd-1992-2007-layouts/census.csv"
DATASET = "sih_aih_reduzida_1992_2007"
DIRECTORY = "/dissemin/publicos/SIHSUS/199201_200712/Dados"
LISTING = "sihsus_199201_200712_dados_rd"
FIXTURES = [
    "sih_rd_rr_1994_12_mini",
    "sih_rd_rr_1997_09_mini",
    "sih_rd_rr_2004_07_excerpt",
    "sih_rd_rr_2007_12_mini",
]
# C in some layouts, N in others (census.csv): no one type is the DBF's. The dictionary
# keeps the type it had from RDRR0712 until that is decided (#40).
CHANGES_TYPE = {"num_proc", "insc_pn", "seq_aih5"}


def census_rows() -> list[dict[str, str]]:
    with CENSUS.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def census() -> dict[str, set[tuple[str, int]]]:
    """Every field of the census, lowercased, with each (DBF type, decimals) it has."""
    out: dict[str, set[tuple[str, int]]] = {}
    for row in census_rows():
        words = row["fields"].split(" ")
        for name, spec in zip(words[::2], words[1::2], strict=True):
            out.setdefault(name.lower(), set()).add((spec[0], int(spec.split(".")[1])))
    return out


def declared() -> dict[str, str]:
    return {f["name"]: f["type"] for f in load_dicionario(DATASET).fields}


def fixture_fields(dbc_fixture, fixture: str) -> dict[str, str]:
    raw = dbc_fixture(fixture).read_bytes()
    return {f["name"]: f["type"] for f in fields_of(dbc.decompress_bytes(raw))}


@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_fixture_field_is_declared_with_the_generator_type(dbc_fixture, fixture):
    published = fixture_fields(dbc_fixture, fixture)
    types = declared()
    assert set(published) <= set(types)
    assert {n: types[n] for n in published if n not in CHANGES_TYPE} == {
        n: t for n, t in published.items() if n not in CHANGES_TYPE
    }


def test_the_dictionary_declares_the_fields_of_every_layout(dbc_fixture):
    """The four fixtures hold every field of the 19 layouts, and the dictionary no other."""
    in_fixtures = {n for fixture in FIXTURES for n in fixture_fields(dbc_fixture, fixture)}
    assert set(declared()) == set(census()) == in_fixtures


def test_only_these_fields_change_dbf_type_between_layouts():
    assert {name for name, types in census().items() if len(types) > 1} == CHANGES_TYPE


def test_the_fields_that_change_type_keep_their_rdrr0712_type(dbc_fixture):
    published = fixture_fields(dbc_fixture, "sih_rd_rr_2007_12_mini")
    types = declared()
    assert {n: types[n] for n in CHANGES_TYPE} == {n: published[n] for n in CHANGES_TYPE}


def test_the_census_reads_ap_exactly_where_the_listing_has_no_rr():
    """Rule 1: "RR is missing" is read from the directory's listing (FIXTURES.md)."""
    entries = (_parse_msdos_line(line, DIRECTORY) for line in listing_lines(LISTING))
    listed = {e.name: e for e in entries if e is not None}
    rows = census_rows()
    assert {r["file"]: (int(r["size_bytes"]), r["server_modified"]) for r in rows} == {
        r["file"]: (listed[r["file"]].size_bytes, f"{listed[r['file']].modified:%Y-%m-%dT%H:%M}")
        for r in rows
        if r["file"] in listed
    }
    no_rr = {
        r["month"] for r in rows if f"RDRR{r['month'][2:4]}{r['month'][5:]}.dbc" not in listed
    }
    assert {r["month"] for r in rows if r["file"].startswith("RDAP")} == no_rr


# CID-9 and CID-10 in one column. The 6-digit codes are not decomposed into CID-9 codes
# here: the CID-9 tables RD.DEF names are not packaged.
CNV = files("omnisus.data.dicionarios") / "sources" / "cnv"
ERA_PACKAGES = ["sih_199201_199712", "sih_199801_200307", "sih_200308_200712"]
LEADING_ZERO = {
    "cid_morte": {"0I64": 6, "0I10": 3, "0B24": 2, "0D77": 1},
    "cid_asso": {"0I10": 1},
}


def _frame(dbc_fixture, fixture: str) -> pl.DataFrame:
    raw = dbc_fixture(fixture).read_bytes()
    return dbc_bytes_to_lazyframe(raw, dataset=DATASET).collect()


def _spec(row: dict[str, str], field: str) -> str | None:
    """The DBF spec of `field` in one census row (`C6.0`), or None if the file lacks it."""
    words = row["fields"].split(" ")
    return dict(zip(words[::2], words[1::2], strict=True)).get(field)


def _open_issue(field: str, issue: str) -> str:
    issues = load_dicionario(DATASET).field_def(field)["x-metadata"]["issues"]
    (entry,) = [i for i in issues if i["id"] == issue]
    assert entry["status"] == "open"
    return entry["description"]


def test_diag_princ_is_c6_until_1997_12_and_c4_from_1998_01_in_every_uf_read():
    rows = census_rows()
    assert {_spec(r, "DIAG_PRINC") for r in rows if r["month"] <= "1997-12"} == {"C6.0"}
    assert {_spec(r, "DIAG_PRINC") for r in rows if r["month"] >= "1998-01"} == {"C4.0"}
    spec = {r["file"]: _spec(r, "DIAG_PRINC") for r in rows}
    for uf in ("RR", "SP", "MG"):
        assert (spec[f"RD{uf}9712.dbc"], spec[f"RD{uf}9801.dbc"]) == ("C6.0", "C4.0")
    # DIAG_SEC (C6) only in 1997; DIAG_SECUN (C4) in every file from 1998-01 and none before.
    assert {r["month"][:4] for r in rows if _spec(r, "DIAG_SEC") == "C6.0"} == {"1997"}
    assert {r["month"] >= "1998-01" for r in rows if _spec(r, "DIAG_SECUN") == "C4.0"} == {True}
    assert all(_spec(r, "DIAG_SECUN") == "C4.0" for r in rows if r["month"] >= "1998-01")


@pytest.mark.parametrize("fixture", ["sih_rd_rr_1994_12_mini", "sih_rd_rr_1997_09_mini"])
def test_diag_princ_holds_six_digits_until_1997(dbc_fixture, fixture):
    values = _frame(dbc_fixture, fixture)["diag_princ"].to_list()
    assert values and all(len(v) == 6 and v.isdecimal() for v in values)


@pytest.mark.parametrize("fixture", ["sih_rd_rr_2004_07_excerpt", "sih_rd_rr_2007_12_mini"])
def test_diag_princ_starts_with_a_letter_from_1998(dbc_fixture, fixture):
    values = [v for v in _frame(dbc_fixture, fixture)["diag_princ"].to_list() if v]
    assert values and all(v[0].isalpha() and len(v) in (3, 4) for v in values)


def _binds(tables: set[str], cid: str) -> bool:
    if cid == "CID9":
        return any("CID9" in t for t in tables)
    return any("CID10" in t or t.startswith("CIDX") for t in tables)


@pytest.mark.parametrize("package", ERA_PACKAGES)
def test_rd_def_binds_diag_princ_to_both_cid_tables(package):
    """DIAG_PRINC to CID-10 and CID-9 tables, DIAG_SEC to CID-9 only, DIAG_SECUN to
    CID-10 only: the DEF does not tell the eras apart."""
    text = (CNV / package / "RD.DEF").read_bytes().decode("latin-1")
    tables: dict[str, set[str]] = {}
    for binding in parse_def(text):
        tables.setdefault(binding.field, set()).add(binding.table.upper())
    assert _binds(tables["DIAG_PRINC"], "CID9") and _binds(tables["DIAG_PRINC"], "CID10")
    assert _binds(tables["DIAG_SEC"], "CID9") and not _binds(tables["DIAG_SEC"], "CID10")
    assert _binds(tables["DIAG_SECUN"], "CID10") and not _binds(tables["DIAG_SECUN"], "CID9")


def test_diag_princ_has_an_open_issue_on_the_two_classifications():
    description = _open_issue("diag_princ", "diag-princ-cid9-ate-1997")
    for fact in (
        "1992-01",
        "1997-12",
        "1998-01",
        "C6",
        "C4",
        "evidence/2026-10-01-rd-1992-2007-layouts/census.csv",
        "sih_rd_rr_1994_12_mini",
        "sih_rd_rr_1997_09_mini",
        "sih_rd_rr_2004_07_excerpt",
        "sih_rd_rr_2007_12_mini",
        "'065099'",
        "'O800'",
        "RD.DEF",
        "LIKE 'I21%'",
    ):
        assert fact in description, fact


@pytest.mark.parametrize("field", sorted(LEADING_ZERO))
def test_cid_morte_and_cid_asso_write_a_category_after_a_zero(dbc_fixture, field):
    """RDRR0712: a 3-character CID-10 category after a '0'. aux_cid10.codigo starts with a
    letter, so no such value joins; without the '0' each is a valid code."""
    values = Counter(_frame(dbc_fixture, "sih_rd_rr_2007_12_mini")[field].to_list())
    zero_letter = {v: n for v, n in values.items() if v[:1] == "0" and v[1:2].isalpha()}
    assert zero_letter == LEADING_ZERO[field]
    pattern = load_dicionario("aux_cid10").field_def("codigo")["constraints"]["pattern"]
    assert not any(re.fullmatch(pattern, v) for v in zero_letter)
    assert all(re.fullmatch(pattern, v[1:]) for v in zero_letter)


@pytest.mark.parametrize("field", sorted(LEADING_ZERO))
def test_cid_morte_and_cid_asso_have_an_open_issue_on_the_leading_zero(field):
    description = _open_issue(field, "cid-zero-a-esquerda")
    assert all(f"'{v}'" in description for v in LEADING_ZERO[field])
    assert "sih_rd_rr_2007_12_mini" in description and "aux_cid10" in description
    # "O campo existe de 2006-04 a 2007-12", as the census reads it.
    months = {r["month"] for r in census_rows() if _spec(r, field.upper()) == "C4.0"}
    assert months == {r["month"] for r in census_rows() if r["month"] >= "2006-04"}
    assert "de 2006-04 a 2007-12" in description
