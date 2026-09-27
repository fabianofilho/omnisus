"""`sus.label` and `sus.display_row`: one lookup from code to the dictionary's label.

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


def _expected(decode_map: dict, code: object) -> str | None:
    """Independent oracle: the key as written, stripped, or as an integer."""
    keys = {str(k): v for k, v in decode_map.items()}
    if code is None:
        return None
    text = str(code).strip()
    if text in keys:
        return keys[text]
    return keys.get(str(int(text))) if text.isdigit() else None


def test_label_adds_a_rotulo_column_after_each_coded_column(sim: pl.DataFrame) -> None:
    dicionario = load_dicionario("sim_obitos")
    coded = [c for c in sim.columns if (dicionario.field_def(c) or {}).get("x-decode")]

    rotulado = sus.label("sim_obitos", sim)

    assert coded, "SIM has coded columns"
    for column in coded:
        position = rotulado.columns.index(column)
        assert rotulado.columns[position + 1] == f"{column}_rotulo"
        pairs = rotulado.select(column, f"{column}_rotulo").unique().rows()
        decode_map = dicionario.field_def(column)["x-decode"]
        assert all(label == _expected(decode_map, code) for code, label in pairs), column
    assert rotulado.drop([f"{c}_rotulo" for c in coded]).equals(sim)


def test_label_keeps_the_code_and_labels_sexo(sim: pl.DataFrame) -> None:
    rotulado = sus.label("sim_obitos", sim, columns=["sexo"])

    assert rotulado.columns == [
        *sim.columns[: sim.columns.index("sexo") + 1],
        "sexo_rotulo",
        *sim.columns[sim.columns.index("sexo") + 1 :],
    ]
    feminino = rotulado.filter(pl.col("sexo") == "2")
    assert feminino.height > 0
    assert set(feminino["sexo_rotulo"]) == {"Feminino"}


@pytest.mark.parametrize("column", ["dtobito", "nao_existe"])
def test_label_refuses_a_column_without_a_code_map(sim: pl.DataFrame, column: str) -> None:
    with pytest.raises(ValueError, match=column):
        sus.label("sim_obitos", sim, columns=[column])


def test_a_code_the_dictionary_does_not_know_has_a_null_label(sia: pl.DataFrame) -> None:
    dataset = "sia_bpa_individualizado"
    dicionario = load_dicionario(dataset)
    unknown = [
        u
        for u in decode_coverage(dataset, duckdb.from_arrow(sia.to_arrow()))
        if u.value.strip()
        and _expected(dicionario.field_def(u.field)["x-decode"], u.value) is None
    ]
    assert unknown, "BIRR2201 publishes tpidadepac codes the dictionary does not label"

    rotulado = sus.label(dataset, sia, columns=sorted({u.field for u in unknown}))

    for u in unknown:
        rows = rotulado.filter(pl.col(u.field).cast(pl.String) == u.value)
        assert rows.height == u.rows
        assert rows[f"{u.field}_rotulo"].null_count() == u.rows
        assert sus.display_row(dataset, {u.field: u.value})[u.field] is None


def test_display_row_labels_codes_and_leaves_other_fields_as_published() -> None:
    row = {"dtobito": "01012023", "horaobito": "1040", "idade": "435", "sexo": "2"}

    assert sus.display_row("sim_obitos", row) == {**row, "sexo": "Feminino"}
