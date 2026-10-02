"""RD 1992-2007: the dictionary declares every field the era's DBF layouts publish (#30).

The files of `SIHSUS/199201_200712/Dados` the census read (one RR file a month, AP where
RR is missing, and SP and MG in the months a layout changes) have 19 layouts
(evidence/2026-10-01-rd-1992-2007-layouts/census.csv). Three whole RR files and an excerpt
of a fourth carry every field of them; each field is declared with the type
scripts/gen_dicionario.py gives it.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from scripts.gen_dicionario import fields_of

from omnisus.sources.datasus_ftp import dbc
from omnisus.transforms.dictionaries import load_dicionario

ROOT = Path(__file__).resolve().parents[3]
CENSUS = ROOT / "evidence/2026-10-01-rd-1992-2007-layouts/census.csv"
DATASET = "sih_aih_reduzida_1992_2007"
FIXTURES = [
    "sih_rd_rr_1994_12_mini",
    "sih_rd_rr_1997_09_mini",
    "sih_rd_rr_2004_07_excerpt",
    "sih_rd_rr_2007_12_mini",
]
# C in some layouts, N in others (census.csv): no one type is the DBF's. The dictionary
# keeps the type it had from RDRR0712 until that is decided (#40).
CHANGES_TYPE = {"num_proc", "insc_pn", "seq_aih5"}


def census() -> dict[str, set[tuple[str, int]]]:
    """Every field of the census, lowercased, with each (DBF type, decimals) it has."""
    out: dict[str, set[tuple[str, int]]] = {}
    with CENSUS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
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
