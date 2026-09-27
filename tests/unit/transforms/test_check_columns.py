"""`sus.check_columns`: what the dictionary says and what the rows show, per column.

Real data: SIM RR 2023 (`sim_rr_2023_mini`, DORR2023.dbc) and SIA BPA-I RR 2022-01
(`sia_bi_rr_2022_01_mini`, BIRR2201.dbc), read back through `sus.load`.
"""

from __future__ import annotations

import duckdb
import polars as pl
import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from omnisus.transforms.dictionaries import decode_coverage, load_dicionario
from tests.support.lake_rows import load_fixture

COLUMNS = [
    "column",
    "label",
    "rule",
    "pct_empty",
    "distinct",
    "example_code",
    "example_label",
    "unlabelled_codes",
    "unlabelled_rows",
    "pct_invalid_dates",
    "date_min",
    "date_max",
]


@pytest.fixture(scope="module")
def sim(tmp_path_factory) -> pl.DataFrame:
    scope = ScopeKey(uf="RR", ano=2023)
    return load_fixture("sim_obitos", "sim_rr_2023_mini", scope, tmp_path_factory.mktemp("sim"))


@pytest.fixture(scope="module")
def sia(tmp_path_factory) -> pl.DataFrame:
    scope = ScopeKey(uf="RR", ano=2022, mes=1)
    return load_fixture(
        "sia_bpa_individualizado", "sia_bi_rr_2022_01_mini", scope, tmp_path_factory.mktemp("sia")
    )


def _filled(df: pl.DataFrame, column: str) -> pl.Series:
    text = df[column].cast(pl.String).str.strip_chars()
    return text.filter(text.is_not_null() & (text != ""))


def test_one_row_per_column_in_input_order(sim: pl.DataFrame) -> None:
    report = sus.check_columns("sim_obitos", sim)

    assert report.columns == COLUMNS
    assert report["column"].to_list() == sim.columns
    assert report.schema["date_min"] == pl.Date and report.schema["date_max"] == pl.Date
    assert report.schema["unlabelled_codes"] == pl.List(pl.String)


def test_empty_counts_null_and_blank(sim: pl.DataFrame) -> None:
    report = sus.check_columns("sim_obitos", sim).rows_by_key("column", named=True, unique=True)

    for column in sim.columns:
        expected = round(100 * (1 - _filled(sim, column).len() / sim.height), 1)
        assert report[column]["pct_empty"] == expected, column
        assert report[column]["distinct"] == _filled(sim, column).n_unique(), column


def test_dictionary_facts_and_example(sim: pl.DataFrame) -> None:
    dicionario = load_dicionario("sim_obitos")
    report = sus.check_columns("sim_obitos", sim).rows_by_key("column", named=True, unique=True)

    sexo = report["sexo"]
    assert sexo["label"] == dicionario.field_def("sexo")["label"]
    assert sexo["rule"] == f"code map ({len(dicionario.field_def('sexo')['x-decode'])} codes)"
    assert sexo["example_label"] == dicionario.decode("sexo", sexo["example_code"])
    assert report["dtobito"]["rule"] == "date ddMMyyyy"
    assert report["dtobito"]["example_label"] is None


def test_unlabelled_codes_are_the_coverage_gaps_the_lookup_cannot_label(sia: pl.DataFrame) -> None:
    dataset = "sia_bpa_individualizado"
    dicionario = load_dicionario(dataset)
    report = sus.check_columns(dataset, sia).rows_by_key("column", named=True, unique=True)

    gaps = [
        u
        for u in decode_coverage(dataset, duckdb.from_arrow(sia.to_arrow()))
        if u.value.strip() and dicionario.decode(u.field, u.value) is None
    ]
    assert gaps, "BIRR2201 publishes codes the dictionary does not label"
    for column in {u.field for u in gaps}:
        mine = [u for u in gaps if u.field == column]
        assert sorted(report[column]["unlabelled_codes"]) == sorted(u.value for u in mine)
        assert report[column]["unlabelled_rows"] == sum(u.rows for u in mine)
    assert all(
        row["unlabelled_rows"] == 0
        for name, row in report.items()
        if name not in {u.field for u in gaps}
    )


def test_dates_are_typed_and_invalid_ones_are_counted(sia: pl.DataFrame) -> None:
    dicionario = load_dicionario("sia_bpa_individualizado")
    report = sus.check_columns("sia_bpa_individualizado", sia).rows_by_key(
        "column", named=True, unique=True
    )
    dates = [
        c
        for c in sia.columns
        if (dicionario.field_def(c) or {}).get("type") == "date"
        and dicionario.field_def(c).get("x-format") in {"ddMMyyyy", "yyyyMMdd"}
    ]

    assert dates, "BPA-I has formatted date fields"
    for column in dates:
        pattern = {"ddMMyyyy": "%d%m%Y", "yyyyMMdd": "%Y%m%d"}[
            dicionario.field_def(column)["x-format"]
        ]
        filled = _filled(sia, column)
        parsed = filled.str.strptime(pl.Date, pattern, strict=False)
        assert report[column]["date_min"] == parsed.min(), column
        assert report[column]["date_max"] == parsed.max(), column
        expected = round(100 * parsed.null_count() / filled.len(), 1) if filled.len() else None
        assert report[column]["pct_invalid_dates"] == expected, column
    other = next(c for c in sia.columns if c not in dates)
    assert report[other]["pct_invalid_dates"] is None and report[other]["date_min"] is None


def test_a_column_with_nothing_filled_reports_none_instead_of_failing(sim: pl.DataFrame) -> None:
    """`exame` is coded and blank in every DORR2023 row; `Series.mean()` of an empty
    series is None, which tutorial 06 learned to guard."""
    assert _filled(sim, "exame").len() == 0

    exame = sus.check_columns("sim_obitos", sim).rows_by_key("column", named=True, unique=True)[
        "exame"
    ]

    assert exame["pct_empty"] == 100.0
    assert exame["distinct"] == 0
    assert exame["example_code"] is None and exame["example_label"] is None
    assert exame["unlabelled_codes"] == [] and exame["unlabelled_rows"] == 0


def test_a_column_outside_the_dictionary_is_reported_not_skipped(sim: pl.DataFrame) -> None:
    renamed = sim.select(pl.col("sexo").alias("minha_coluna"))

    (row,) = sus.check_columns("sim_obitos", renamed).rows(named=True)

    assert row["rule"] == "not in dictionary"
    assert row["label"] is None and row["example_label"] is None
