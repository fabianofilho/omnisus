"""Structured age semantics and actual DuckDB parity, independent of a lake."""

import sys
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path

import duckdb
import pytest

from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.age import Age, age_expressions, decode_age
from omnisus.transforms.cnv import cnv_map, parse_cnv
from omnisus.transforms.dictionaries import load_dicionario

SIM = {
    "kind": "sim",
    "units": {
        "0": {"unit": "minute"},
        "1": {"unit": "hour"},
        "2": {"unit": "day"},
        "3": {"unit": "month"},
        "4": {"unit": "year"},
        "5": {"unit": "year", "offset": 100},
    },
    "ignored_values": ["000"],
    "ignored_units": ["9"],
    "under_one_year": ["400"],
}
SIH = {
    "kind": "sih",
    "units": {key: value for key, value in SIM["units"].items() if key in "2345"},
    "ignored_units": ["0", "9"],
    "maximum_value": 99,
}
SINAN = load_dicionario("sinan_chagas").raw["x-analytics"]["age"]


@pytest.mark.parametrize(
    ("raw", "quantity", "unit", "years", "status", "label"),
    [
        ("000", None, None, None, "ignored", "Ignorada"),
        ("045", 45, "minute", 0, "valid", "45 minutos"),
        ("001", 1, "minute", 0, "valid", "1 minuto"),
        ("122", 22, "hour", 0, "valid", "22 horas"),
        ("101", 1, "hour", 0, "valid", "1 hora"),
        ("229", 29, "day", 0, "valid", "29 dias"),
        ("201", 1, "day", 0, "valid", "1 dia"),
        ("310", 10, "month", 0, "valid", "10 meses"),
        ("301", 1, "month", 0, "valid", "1 mês"),
        ("312", 12, "month", 1, "valid", "12 meses"),
        ("399", 99, "month", 8, "valid", "99 meses"),
        ("400", 0, "year", 0, "valid", "Menor de 1 ano"),
        ("401", 1, "year", 1, "valid", "1 ano"),
        ("499", 99, "year", 99, "valid", "99 anos"),
        ("500", 0, "year", 100, "valid", "100 anos"),
        ("501", 1, "year", 101, "valid", "101 anos"),
        ("599", 99, "year", 199, "valid", "199 anos"),
        ("999", None, None, None, "ignored", "Ignorada"),
        ("900", None, None, None, "ignored", "Ignorada"),
        (None, None, None, None, "missing", None),
        ("", None, None, None, "missing", None),
        ("-10", None, None, None, "invalid", None),
        ("abc", None, None, None, "invalid", None),
        ("45", None, None, None, "invalid", None),
        ("0400", None, None, None, "invalid", None),
        ("635", 35, None, None, "unsupported", None),
    ],
)
def test_sim_interprets_quantity_unit_years_and_display(raw, quantity, unit, years, status, label):
    age = decode_age(SIM, raw)
    assert (age.value, age.unit, age.years_completed, age.status) == (
        quantity,
        unit,
        years,
        status,
    )
    assert age.display() == label
    assert age.quantity == (None if status != "valid" else years if unit == "year" else quantity)


@pytest.mark.parametrize(
    ("unit", "raw", "years", "status"),
    [
        ("2", 30, 0, "valid"),
        ("3", 11, 0, "valid"),
        ("3", 24, 2, "valid"),
        ("4", 35, 35, "valid"),
        ("5", 2, 102, "valid"),
        (None, 35, None, "missing"),
        ("", 35, None, "missing"),
        ("8", 35, None, "unsupported"),
        ("04", 35, None, "unsupported"),
        ("4", 999, None, "unsupported"),
        ("5", 999, None, "unsupported"),
        ("0", 999, None, "ignored"),
        ("9", 999, None, "ignored"),
        ("4", 35.5, None, "invalid"),
        ("4", 35.0, None, "invalid"),
        (4.0, 35, None, "invalid"),
        ("4", "-1", None, "invalid"),
        ("4", "0035", 35, "valid"),
    ],
)
def test_sih_requires_declared_unit_and_domain(unit, raw, years, status):
    age = decode_age(SIH, raw, unit)
    assert (age.years_completed, age.status) == (years, status)


# Every character str.strip() removes (the scalar path), taken from Python, not from age.py.
PYTHON_WHITESPACE = "".join(filter(str.isspace, map(chr, range(sys.maxunicode + 1))))
RAW_CASES = [
    None,
    "",
    " ",
    "000",
    "045",
    "122",
    "229",
    "310",
    "400",
    "401",
    "499",
    "500",
    "501",
    "599",
    "999",
    "0000",
    " 401 ",
    "\t401\n",
    "\u00a0401\u00a0",
    "\u2003401\u3000",
    # Synthetic: padded with every PYTHON_WHITESPACE character, so SQL must trim each one.
    PYTHON_WHITESPACE + "401" + PYTHON_WHITESPACE,
    "1",
    "0035",
    "-35",
    "+35",
    "35.5",
    "35.0",
    "1e2",
    "4 1",
    "\uff13\uff15",
    "abc",
    "nan",
    "2147483647",
    "2147483648",
    "9223372036854775807",
    "9223372036854775808",
    "9" * 5000,
    "0" * 5000 + "35",
    "0" * 5000,
    "4088",
    "2029",
    "3011",
    "4106",
    "0088",
    "408",
    "40888",
]
UNIT_CASES = [None, "", "0", "1", "2", "3", "4", "5", "9", "8", "04", "4.0", "x", "-4", " 4 "]


@pytest.mark.parametrize("rule", [SIM, SINAN, SIH])
def test_native_duckdb_matches_scalar_for_malformed_and_boundary_values(rule):
    cases = [(raw, unit) for raw in RAW_CASES for unit in UNIT_CASES]
    sql = age_expressions(rule, '"raw"', '"unit"')
    with duckdb.connect() as con:
        con.execute("CREATE TABLE cases (i INTEGER, raw VARCHAR, unit VARCHAR)")
        con.executemany(
            "INSERT INTO cases VALUES (?, ?, ?)", [(i, *case) for i, case in enumerate(cases)]
        )
        rows = con.execute(
            f"SELECT {sql.years}, {sql.status}, {sql.quantity}, {sql.unit} FROM cases ORDER BY i"
        ).fetchall()
    expected = [
        (
            age.years_completed,
            age.status,
            age.quantity,
            age.unit if age.status == "valid" else None,
        )
        for raw, unit in cases
        for age in [decode_age(rule, raw, unit)]
    ]
    assert rows == expected


@pytest.mark.parametrize("raw", [35, 35.0, 35.5, True, False, None])
def test_duckdb_typed_values_match_scalar(raw):
    years, status = age_expressions(SIH, "raw", "unit")[:2]
    with duckdb.connect() as con:
        actual = con.execute(
            f"SELECT {years}, {status} FROM (SELECT ? AS raw, 4 AS unit)", [raw]
        ).fetchone()
    age = decode_age(SIH, raw, 4)
    assert actual == (age.years_completed, age.status)


def test_rule_changes_apply_to_both_executors():
    rule = {
        **SIH,
        "units": {"5": {"unit": "year", "offset": 90, "maximum_value": 2}},
        "ignored_values": ["1"],
    }
    years, status = age_expressions(rule, "raw", "'5'")[:2]
    with duckdb.connect() as con:
        for raw, expected in [
            ("0", (90, "valid")),
            ("1", (None, "ignored")),
            ("2", (92, "valid")),
            ("3", (None, "unsupported")),
        ]:
            scalar = decode_age(rule, raw, "5")
            assert (scalar.years_completed, scalar.status) == expected
            assert (
                con.execute(f"SELECT {years}, {status} FROM (SELECT ? AS raw)", [raw]).fetchone()
                == expected
            )


def test_subyear_without_confirmed_domain_is_unsupported():
    rule = {key: value for key, value in SIH.items() if key != "maximum_value"}
    years, status = age_expressions(rule, "'30'", "'2'")[:2]
    assert decode_age(rule, "30", "2").status == "unsupported"
    with duckdb.connect() as con:
        assert con.execute(f"SELECT {years}, {status}").fetchone() == (None, "unsupported")


def test_missing_unit_sql_and_unknown_rule():
    years, status = age_expressions(SIH, "'35'")[:2]
    with duckdb.connect() as con:
        assert con.execute(f"SELECT {years}, {status}").fetchone() == (None, "missing")
    for operation in (
        lambda: decode_age({"kind": "unknown"}, 35),
        lambda: age_expressions({"kind": "unknown"}, "raw"),
    ):
        with pytest.raises(ValueError, match="Unsupported age rule kind"):
            operation()


def test_age_is_immutable():
    age = Age(35, "year", 35, "valid")
    with pytest.raises(FrozenInstanceError):
        age.value = 40


@pytest.mark.parametrize(
    ("unit", "raw", "expected"),
    [
        ("0", "0", (None, "invalid")),
        ("0", "000", (None, "invalid")),
        ("9", "99", (None, "invalid")),
        ("9", "099", (None, "invalid")),
        ("4", "999", (None, "unsupported")),
        ("9", "999", (None, "unsupported")),
        ("3", "0", (None, "unsupported")),
        ("4", "0", (None, "unsupported")),
        ("2", "0", (0, "valid")),
        # IDADEDET.CNV lists 230 with "1 mês"; an exact-quantity rule cannot say that.
        ("2", "30", (None, "unsupported")),
        ("2", "31", (None, "unsupported")),
        ("3", "11", (0, "valid")),
        ("3", "12", (None, "unsupported")),
        ("4", "1", (1, "valid")),
        ("5", "0", (100, "valid")),
        ("5", "30", (130, "valid")),
        ("5", "31", (None, "unsupported")),
        ("0", "0.0", (None, "invalid")),
        ("9", "99.0", (None, "invalid")),
    ],
)
def test_packaged_sih_domains_and_invalid_composites(unit, raw, expected):
    rule = load_dicionario("sih_aih_reduzida").raw["x-analytics"]["age"]
    age = decode_age(rule, raw, unit)
    assert (age.years_completed, age.status) == expected
    years, status = age_expressions(rule, "raw", "unit")[:2]
    with duckdb.connect() as con:
        assert (
            con.execute(
                f"SELECT {years}, {status} FROM (SELECT ? AS raw, ? AS unit)", [raw, unit]
            ).fetchone()
            == expected
        )


def test_minimum_domain_from_rule_and_unit_override():
    rule = {
        **SIH,
        "minimum_value": 2,
        "units": {
            "4": {"unit": "year"},
            "5": {"unit": "year", "offset": 100, "minimum_value": 0},
        },
    }
    years, status = age_expressions(rule, "raw", "unit")[:2]
    with duckdb.connect() as con:
        for unit, raw, expected in [
            ("4", "1", (None, "unsupported")),
            ("4", "2", (2, "valid")),
            ("5", "0", (100, "valid")),
        ]:
            age = decode_age(rule, raw, unit)
            assert (age.years_completed, age.status) == expected
            assert (
                con.execute(
                    f"SELECT {years}, {status} FROM (SELECT ? AS raw, ? AS unit)", [raw, unit]
                ).fetchone()
                == expected
            )


YEARS = {
    "kind": "years",
    "units": {"year": {"unit": "year", "minimum_value": 1, "maximum_value": 65}},
    "ignored_values": ["0", "00", "99"],
}


@pytest.mark.parametrize(
    ("raw", "years", "status"),
    [
        ("25", 25, "valid"),
        (25, 25, "valid"),
        (" 11 ", 11, "valid"),
        ("01", 1, "valid"),
        ("65", 65, "valid"),
        ("66", None, "unsupported"),
        ("98", None, "unsupported"),
        ("99", None, "ignored"),
        ("00", None, "ignored"),
        (0, None, "ignored"),
        (None, None, "missing"),
        ("", None, "missing"),
        (25.0, None, "invalid"),
        ("25.5", None, "invalid"),
        ("-1", None, "invalid"),
        ("abc", None, "invalid"),
    ],
)
def test_declared_years_age_needs_no_unit_column(raw, years, status):
    scalar = decode_age(YEARS, raw)
    assert (scalar.years_completed, scalar.status) == (years, status)
    value_sql, status_sql = age_expressions(YEARS, "raw")[:2]
    with duckdb.connect() as con:
        result = con.execute(
            f"SELECT {value_sql}, {status_sql} FROM (SELECT ? AS raw)", [raw]
        ).fetchone()
    assert result == (years, status)
    if status == "valid":
        assert scalar.display() == f"{years} {'ano' if years == 1 else 'anos'}"


def test_declared_years_sql_scalar_parity_for_malformed_and_large_values():
    test_native_duckdb_matches_scalar_for_malformed_and_boundary_values(YEARS)


def test_packaged_sinasc_age_domain_matches_sql_and_scalar():
    rule = load_dicionario("sinasc_nascidos_vivos").raw["x-analytics"]["age"]
    years, status = age_expressions(rule, "raw")[:2]
    with duckdb.connect() as con:
        for number in range(101):
            raw = f"{number:02d}"
            expected = (
                (number, "valid")
                if 1 <= number <= 65
                else (None, "ignored")
                if number in (0, 99)
                else (None, "unsupported")
            )
            age = decode_age(rule, raw)
            assert (age.years_completed, age.status) == expected
            assert (
                con.execute(f"SELECT {years}, {status} FROM (SELECT ? AS raw)", [raw]).fetchone()
                == expected
            )


SINAN_FILES = [
    # dataset, fixture, rows whose NU_IDADE_N is 4088, statuses seen (counted on 2026-09-21/22)
    ("sinan_chagas", "sinan_chagas_br_2023", 11, {"valid"}),
    ("sinan_hanseniase", "sinan_hanseniase_br_2026", 16, {"valid"}),
    ("sinan_tuberculose", "sinan_tuberculose_br_2020_excerpt", 1, {"valid", "missing"}),
]


@pytest.mark.parametrize(("dataset", "fixture", "rows_4088", "statuses"), SINAN_FILES)
def test_sinan_age_reads_three_quantity_digits_in_both_paths(
    dbc_fixture, dataset, fixture, rows_4088, statuses
):
    """Real NU_IDADE_N: 4088 is 88 years in SQL and Python; every row agrees."""
    rule = load_dicionario(dataset).raw["x-analytics"]["age"]
    frame = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
    sql = age_expressions(rule, "nu_idade_n")
    with duckdb.connect() as con:
        con.register("source", frame)
        rows = con.execute(
            f"SELECT nu_idade_n, {sql.years}, {sql.status}, {sql.quantity}, {sql.unit} FROM source"
        ).fetchall()
    assert len(rows) == frame.height
    for value, *outputs in rows:
        age = decode_age(rule, value)
        assert tuple(outputs) == (age.years_completed, age.status, age.quantity, age.unit), value
    assert [row[1:] for row in rows if row[0] == 4088] == [(88, "valid", 88, "year")] * rows_4088
    assert {row[2] for row in rows} == statuses
    # The SIM rule reads one unit + two digits; it rejects 4088 instead of reading 8.
    sim = load_dicionario("sim_obitos").raw["x-analytics"]["age"]
    assert decode_age(sim, 4088).status == "invalid"


# TAB_SIA CNV/IDADEDET.CNV (tests/fixtures/FIXTURES.md). RAAS_Psicossocial.def binds it to
# TPIDADEPAC; it compares 3 characters, TPIDADEPAC followed by IDADEPAC.
IDADEDET = cnv_map(
    parse_cnv(
        (Path(__file__).resolve().parents[2] / "fixtures/cnv/IDADEDET.CNV")
        .read_bytes()
        .decode("latin-1")
    )
)
SIA_AGE = ["sia_bpa_individualizado", "sia_psicossocial", "sia_atencao_domiciliar"]


# TAB_SIH CNV/IDADEDET.CNV has the same bytes (RD2008.DEF binds it to COD_IDADE).
@pytest.mark.parametrize("dataset", ["sih_aih_reduzida", *SIA_AGE])
def test_age_rule_is_idadedet(dataset):
    """Each IDADEDET code displays the CNV's label, "Idade inválida" is invalid, and the
    rule accepts no other code. 230 ("1 mês") and 312 ("11 meses") are second codes of a
    category; an exact-quantity rule leaves them unsupported, so display keeps the raw value.
    """
    rule = load_dicionario(dataset).raw["x-analytics"]["age"]
    aliases = {"230", "312"}
    for code, label in IDADEDET.items():
        age = decode_age(rule, code[1:], code[0])
        if label == "Idade inválida":
            assert age.status == "invalid", code
        elif code in aliases:
            assert age.status == "unsupported", code
        else:
            assert age.display() == label, code
    valid = {
        f"{unit}{quantity:02d}"
        for unit in "0123456789"
        for quantity in range(100)
        if decode_age(rule, f"{quantity:02d}", unit).status == "valid"
    }
    assert valid == set(IDADEDET) - aliases - {"000", "999"}


SIA_FILES = [
    # dataset, fixture, rows per status (counted on 2026-09-23)
    (
        "sia_bpa_individualizado",
        "sia_bi_rr_2022_01_mini",
        {"valid": 16590, "unsupported": 2, "invalid": 2},
    ),
    ("sia_bpa_individualizado", "sia_bi_rr_2024_01_mini", {"valid": 12099}),
    ("sia_psicossocial", "sia_ps_rr_2024_01_mini", {"valid": 1670}),
    ("sia_atencao_domiciliar", "sia_sad_ma_2018_10_mini", {"valid": 33}),
]


@pytest.mark.parametrize(("dataset", "fixture", "statuses"), SIA_FILES)
def test_sia_age_on_real_rows_in_both_paths(dbc_fixture, dataset, fixture, statuses):
    """Real TPIDADEPAC + IDADEPAC: SQL and Python agree on every row."""
    rule = load_dicionario(dataset).raw["x-analytics"]["age"]
    frame = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
    sql = age_expressions(rule, "idadepac", "tpidadepac")
    with duckdb.connect() as con:
        con.register("source", frame)
        rows = con.execute(
            f"SELECT idadepac, tpidadepac, {sql.years}, {sql.status}, {sql.quantity}, {sql.unit}"
            " FROM source"
        ).fetchall()
    assert len(rows) == frame.height
    for value, unit, *outputs in rows:
        age = decode_age(rule, value, unit)
        # SQL returns the unit only for a valid age (AgeSql).
        valid_unit = age.unit if age.status == "valid" else None
        assert tuple(outputs) == (age.years_completed, age.status, age.quantity, valid_unit)
    assert Counter(row[3] for row in rows) == statuses


@pytest.mark.parametrize(
    ("dataset", "unit", "value", "shown"),
    [
        # BIRR2201: 5 + 29 (born 1892), 9 + 99, 2 + 30 (IDADEDET: "1 mês").
        ("sia_bpa_individualizado", "5", "29", "129 anos"),
        ("sia_bpa_individualizado", "9", "99", "99"),
        ("sia_bpa_individualizado", "2", "30", "30"),
        ("sia_bpa_individualizado", "3", "01", "1 mês"),
        # PSRR2401: 2 + 00.
        ("sia_psicossocial", "2", "00", "0 dias"),
        ("sia_psicossocial", "4", "48", "48 anos"),
        # SADMA1810: 4 + 79.
        ("sia_atencao_domiciliar", "4", "79", "79 anos"),
    ],
)
def test_sia_idadepac_follows_the_idadedet_label(dataset, unit, value, shown):
    """The age rule reads TPIDADEPAC + IDADEPAC; an age it does not accept keeps the code."""
    rule = load_dicionario(dataset).raw["x-analytics"]["age"]
    assert (decode_age(rule, value, unit).display() or value) == shown
