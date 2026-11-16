"""Every ``x-format`` against the committed fixtures, and the dates of RJ, SP and ER (#9).

Real data: ``sih_rj_rr_2024_01_mini.dbc`` (RJRR2401, 30 records), ``sih_sp_rr_2024_01_mini.dbc``
(SPRR2401, 35.669) and ``sih_er_rr_2024_01_mini.dbc`` (ERRR2401, 31), read back through
``sus.load``; their server SHA-256 are in ``tests/fixtures/FIXTURES.md``.
"""

from __future__ import annotations

import warnings
from datetime import date
from pathlib import Path

import polars as pl
import pytest

import omnisus as sus
from omnisus.transforms.dictionaries import DATE_FORMATS, load_dicionario
from tests.support.lake_rows import load_fixture
from tests.unit.test_fixture_provenance import load_fixture_rows
from tests.unit.test_public_api import _FIXTURE_FOR

DICIONARIOS = Path(sus.__file__).parent / "data" / "dicionarios"
FORMATTED = sorted(
    dataset
    for dataset in _FIXTURE_FOR
    if any(f.get("x-format") for f in load_dicionario(dataset).raw["schema"]["fields"])
)
RJ_DATES = ("nasc", "dt_inter", "dt_saida")
SP_DATES = ("sp_dtinter", "sp_dtsaida")


@pytest.fixture(scope="module")
def frames(tmp_path_factory) -> dict[str, pl.DataFrame]:
    out = {}
    for dataset in {*FORMATTED, "sih_aih_rejeitada", "sih_servicos_profissionais"}:
        fixture, scope = _FIXTURE_FOR[dataset]
        out[dataset] = load_fixture(dataset, fixture, scope, tmp_path_factory.mktemp(dataset))
    return out


def _field(dataset: str, name: str) -> dict:
    return next(f for f in load_dicionario(dataset).raw["schema"]["fields"] if f["name"] == name)


def _filled(frame: pl.DataFrame, name: str) -> pl.Series:
    values = frame[name].cast(pl.String).str.strip_chars()
    return values.filter(values.is_not_null() & (values != ""))


@pytest.mark.parametrize("dataset", FORMATTED)
def test_every_x_format_reads_the_fixture_strictly(dataset, frames) -> None:
    """Eight digits, a real date, a year from 1900 to ten years ahead (``ap_dtaut`` of the APAC
    fixture reads 2029-12-29); a value the other pattern also reads
    is reported, since the format claim then rests on more than the parse."""
    for field in load_dicionario(dataset).raw["schema"]["fields"]:
        if not field.get("x-format"):
            continue
        values = _filled(frames[dataset], field["name"])
        where = f"{dataset}.{field['name']}"
        assert values.str.contains(r"^\d{8}$").all(), where
        pattern = DATE_FORMATS[field["x-format"]]
        dates = values.str.strptime(pl.Date, pattern, strict=False)
        assert dates.null_count() == 0, where
        if values.len():
            assert dates.min().year >= 1900 and dates.max().year <= date.today().year + 10, where
        other = DATE_FORMATS["ddMMyyyy" if field["x-format"] == "yyyyMMdd" else "yyyyMMdd"]
        both = values.str.strptime(pl.Date, other, strict=False).drop_nulls().len()
        if both:
            warnings.warn(f"{where}: {both} of {values.len()} also read as {other}", stacklevel=1)


@pytest.mark.parametrize(
    ("dataset", "names"),
    [("sih_aih_rejeitada", RJ_DATES), ("sih_servicos_profissionais", SP_DATES)],
)
def test_rj_and_sp_dates_declare_the_format_the_fixtures_show(dataset, names) -> None:
    for name in names:
        field = _field(dataset, name)
        assert field["type"] == "date" and field["x-format"] == "yyyyMMdd", name
        claim = next(c for c in field["x-metadata"]["claims"] if c["target"] == "/field/format")
        assert claim["status"] == "unreviewed" and claim["reviewer"] is None, name
        assert claim["method"] == "fixture-measure", name
        issue = next(
            i for i in field["x-metadata"]["issues"] if i["id"] == "formato-sem-documento"
        )
        assert issue["status"] == "open", name


@pytest.mark.parametrize(
    ("dataset", "fixture", "names"),
    [
        ("sih_aih_rejeitada", "sih_rj_rr_2024_01_mini", RJ_DATES),
        ("sih_servicos_profissionais", "sih_sp_rr_2024_01_mini", SP_DATES),
    ],
)
def test_the_observation_names_the_server_file_and_what_the_fixture_shows(
    dataset, fixture, names, frames
) -> None:
    row = next(r for r in load_fixture_rows() if r["file"] == f"dbc/{fixture}.dbc")
    for name in names:
        (observation,) = _field(dataset, name)["x-metadata"]["observations"]
        assert observation["sha256"] == row["source_sha256"], name
        assert observation["url"] == row["source"], name
        assert observation["file"] == row["source"].rsplit("/", 1)[1], name
        assert observation["field_name"] == name and observation["uf"] == "RR"
        values = _filled(frames[dataset], name)
        observed = observation["observed"]
        assert observed["pattern"] == "yyyyMMdd"
        assert observed["filled"] == values.len() == observed["valid"], name
        parsed = values.str.strptime(pl.Date, "%Y%m%d")
        assert observed["valid_min"] == parsed.min().isoformat(), name
        assert observed["valid_max"] == parsed.max().isoformat(), name
        both = values.str.strptime(pl.Date, "%d%m%Y", strict=False).drop_nulls().len()
        assert observed["also_valid_as_ddMMyyyy"] == both, name


def test_rj_gestor_dt_stays_a_string_because_no_fixture_fills_it(frames) -> None:
    field = _field("sih_aih_rejeitada", "gestor_dt")
    assert field["type"] == "string" and "x-format" not in field
    assert _filled(frames["sih_aih_rejeitada"], "gestor_dt").len() == 0
    assert {i["id"] for i in field["x-metadata"]["issues"]} == {"formato-sem-valor"}


def test_check_columns_now_checks_the_rj_and_sp_dates(frames) -> None:
    for dataset, names in (
        ("sih_aih_rejeitada", RJ_DATES),
        ("sih_servicos_profissionais", SP_DATES),
    ):
        report = sus.check_columns(dataset, frames[dataset]).rows_by_key(
            "column", named=True, unique=True
        )
        for name in names:
            assert report[name]["pct_invalid_dates"] == 0.0, name
            assert report[name]["date_min"] is not None, name


def test_check_columns_and_the_harmonisation_share_the_eight_digit_guard() -> None:
    """``'1012023'`` (the 0 of the day lost) parses with a non-strict pattern; the guard of
    ``analytical_projection`` calls it invalid, and so must ``check_columns``."""
    frame = pl.DataFrame({"dtobito": ["01012023", "1012023", " 02012023 ", "0101202"]})
    report = sus.check_columns("sim_obitos", frame).rows_by_key("column", named=True, unique=True)
    assert report["dtobito"]["pct_invalid_dates"] == 50.0
