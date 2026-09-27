"""`sus.load` adds harmonised categories only for validated sources (ADR 0003).

Real data, read back through `sus.load`:
- SIM RR 2023 (`sim_rr_2023_mini`, DORR2023.dbc): in SIM `validated_sources`;
- SIA BPA-I RR 2022-01 (`sia_bi_rr_2022_01_mini`, BIRR2201.dbc): in SIA `validated_sources`;
- SIH RR 2024-01 (`sih_rr_2024_01_mini`, RDRR2401.dbc): **not** validated.
"""

from __future__ import annotations

import warnings

import polars as pl
import pytest

from omnisus.sources._base import ScopeKey
from omnisus.transforms.age import decode_age
from omnisus.transforms.dictionaries import load_dicionario
from tests.support.lake_rows import load_fixture

HARMONISED = ["idade_anos_completos", "idade_status", "sexo_categoria", "sexo_status"]


def _quiet_load(*args):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return load_fixture(*args)


def test_validated_sim_gets_age_sex_and_dates(tmp_path) -> None:
    dados = _quiet_load("sim_obitos", "sim_rr_2023_mini", ScopeKey(uf="RR", ano=2023), tmp_path)
    rules = load_dicionario("sim_obitos").raw["x-analytics"]

    assert {*HARMONISED, "dtobito_data", "dtobito_data_status"} <= set(dados.columns)
    for idade, anos in dados.select("idade", "idade_anos_completos").unique().rows():
        assert anos == decode_age(rules["age"], idade).years_completed, idade
    for sexo, categoria in dados.select("sexo", "sexo_categoria").unique().rows():
        assert categoria == rules["sex"]["categories"].get(sexo), sexo
    parsed = dados["dtobito"].str.strptime(pl.Date, "%d%m%Y", strict=False)
    assert dados["dtobito_data"].equals(parsed, check_names=False)


def test_validated_sia_age_reads_tpidadepac_and_idadepac(tmp_path) -> None:
    scope = ScopeKey(uf="RR", ano=2022, mes=1)
    dados = _quiet_load("sia_bpa_individualizado", "sia_bi_rr_2022_01_mini", scope, tmp_path)
    rule = load_dicionario("sia_bpa_individualizado").raw["x-analytics"]["age"]

    pairs = dados.select("tpidadepac", "idadepac", "idade_anos_completos").unique().rows()
    assert ("5", "29", 129) in pairs  # born 1892, IDADEDET "1xx anos"
    for unit, value, anos in pairs:
        assert anos == decode_age(rule, value, unit).years_completed, (unit, value)


def test_unvalidated_sih_gets_no_harmonised_columns_and_one_warning(tmp_path) -> None:
    scope = ScopeKey(uf="RR", ano=2024, mes=1)

    with pytest.warns(UserWarning) as caught:
        dados = load_fixture("sih_aih_reduzida", "sih_rr_2024_01_mini", scope, tmp_path)

    assert not set(HARMONISED) & set(dados.columns)
    mine = [w for w in caught if "harmonised" in str(w.message)]
    assert len(mine) == 1
    assert "unconfirmed_source_scope" in str(mine[0].message)
    assert "sexo_categoria" in str(mine[0].message)
