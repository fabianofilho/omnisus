"""Tier 1: the (dataset, scope) -> filename codec is exactly right
for every registry row, plus a round-trip property over the whole space.

Centralizing facts centralizes blast radius: if a row's prefix were wrong,
every derived surface would be consistently wrong. This table is the
independent statement of what the filenames must be.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from omnisus import ALL_UFS
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, resolve
from omnisus.sources.datasus_ftp.filenames import decode_for
from tests.support.datasus_names import filename_for

# fmt: off
GOLDEN: list[tuple[str, ScopeKey, str]] = [
    ("sinan_chagas", ScopeKey(uf=None, ano=2023), "CHAGBR23.dbc"),
    ("sinan_hanseniase", ScopeKey(uf=None, ano=2026), "HANSBR26.dbc"),
    ("sinan_tuberculose", ScopeKey(uf=None, ano=2020), "TUBEBR20.dbc"),
    ("sinan_dengue", ScopeKey(uf=None, ano=2023), "DENGBR23.dbc"),
    ("sinan_violencia", ScopeKey(uf=None, ano=2023), "VIOLBR23.dbc"),
    ("sim_obitos",    ScopeKey(uf="SP", ano=2024),         "DOSP2024.dbc"),
    ("sim_obitos",    ScopeKey(uf="RR", ano=1996),         "DORR1996.dbc"),
    ("sinasc_nascidos_vivos", ScopeKey(uf="MG", ano=2022),         "DNMG2022.dbc"),
    ("sih_aih_reduzida",    ScopeKey(uf="SP", ano=2024, mes=1),  "RDSP2401.dbc"),
    ("sih_aih_reduzida",    ScopeKey(uf="AC", ano=2008, mes=12), "RDAC0812.dbc"),
    ("sia_bpa_individualizado",    ScopeKey(uf="RR", ano=2024, mes=1),  "BIRR2401.dbc"),
    ("sia_apac_medicamentos",    ScopeKey(uf="RR", ano=2024, mes=1),  "AMRR2401.dbc"),
    ("sia_apac_quimioterapia",    ScopeKey(uf="RR", ano=2024, mes=1),  "AQRR2401.dbc"),
    ("sia_apac_tratamento_dialitico",   ScopeKey(uf="RR", ano=2024, mes=1),  "ATDRR2401.dbc"),  # 3-letter: ATD+RR, never AT+DR
    ("sia_apac_laudos_diversos",    ScopeKey(uf="AC", ano=2024, mes=1),  "ADAC2401.dbc"),   # AD+AC, never ADA+C
    ("sia_apac_cirurgia_bariatrica",   ScopeKey(uf="SP", ano=2024, mes=1),  "ABOSP2401.dbc"),  # ABO+SP, never AB+OS
    ("sia_psicossocial",    ScopeKey(uf="RR", ano=2024, mes=1),  "PSRR2401.dbc"),
    ("cnes_estabelecimentos",   ScopeKey(uf="RR", ano=2024, mes=1),  "STRR2401.dbc"),
    # two-digit years: the century is the row's, counted from its first covered year
    ("sih_aih_reduzida_1992_2007", ScopeKey(uf="SP", ano=1999, mes=6), "RDSP9906.dbc"),
    ("sih_aih_reduzida_1992_2007", ScopeKey(uf="SP", ano=2007, mes=12), "RDSP0712.dbc"),
    ("sim_obitos_cid9",     ScopeKey(uf="RR", ano=1979),         "DORRR79.dbc"),
    ("sim_obitos_cid9",     ScopeKey(uf="RR", ano=1995),         "DORRR95.dbc"),
    # One real listed name per row (listings of 2026-09-22)
    ("sia_producao_ambulatorial", ScopeKey(uf="RR", ano=2024, mes=1), "PARR2401.dbc"),
    ("sia_producao_ambulatorial_1994_2007", ScopeKey(uf="RR", ano=1994, mes=7), "PARR9407.dbc"),
    ("sih_aih_rejeitada",   ScopeKey(uf="RR", ano=2024, mes=1),  "RJRR2401.dbc"),
    ("sih_servicos_profissionais", ScopeKey(uf="RR", ano=2024, mes=1), "SPRR2401.dbc"),
    ("sih_aih_rejeitada_erro", ScopeKey(uf="RR", ano=2024, mes=1), "ERRR2401.dbc"),
    ("cnes_dados_complementares", ScopeKey(uf="RR", ano=2024, mes=1), "DCRR2401.dbc"),
    ("cnes_equipamentos",   ScopeKey(uf="RR", ano=2024, mes=1),  "EQRR2401.dbc"),
    ("cnes_equipes",        ScopeKey(uf="RR", ano=2024, mes=1),  "EPRR2401.dbc"),
    ("cnes_estabelecimentos_ensino", ScopeKey(uf="RR", ano=2019, mes=12), "EERR1912.dbc"),
    ("cnes_estabelecimentos_filantropicos", ScopeKey(uf="AP", ano=2024, mes=1), "EFAP2401.dbc"),
    ("cnes_gestao_metas",   ScopeKey(uf="RR", ano=2024, mes=1),  "GMRR2401.dbc"),
    ("cnes_habilitacoes",   ScopeKey(uf="RR", ano=2024, mes=1),  "HBRR2401.dbc"),
    ("cnes_incentivos",     ScopeKey(uf="RR", ano=2024, mes=1),  "INRR2401.dbc"),
    ("cnes_leitos",         ScopeKey(uf="RR", ano=2024, mes=1),  "LTRR2401.dbc"),
    ("cnes_regras_contratuais", ScopeKey(uf="RR", ano=2024, mes=1), "RCRR2401.dbc"),
    ("cnes_servicos_especializados", ScopeKey(uf="RR", ano=2024, mes=1), "SRRR2401.dbc"),
    ("sim_obitos_fetais",   ScopeKey(uf=None, ano=2023),         "DOFET23.dbc"),
    ("sim_obitos_externos", ScopeKey(uf=None, ano=1996),         "DOEXT96.dbc"),
    ("sim_obitos_infantis", ScopeKey(uf=None, ano=2023),         "DOINF23.dbc"),
    ("sim_obitos_maternos", ScopeKey(uf=None, ano=2023),         "DOMAT23.dbc"),
    ("sinasc_1994_1995",    ScopeKey(uf="RR", ano=1995),         "DNRRR1995.dbc"),
    # SIA families, one real listed name each (listing of 2026-09-23); AMP+DF, never AM+PD
    ("sia_apac_acompanhamento_bariatrica", ScopeKey(uf="SE", ano=2025, mes=7), "ABSE2507.dbc"),
    ("sia_apac_fistula_arteriovenosa", ScopeKey(uf="RR", ano=2024, mes=1), "ACFRR2401.dbc"),
    ("sia_apac_acompanhamento_multiprofissional", ScopeKey(uf="DF", ano=2024, mes=1), "AMPDF2401.dbc"),
    ("sia_apac_nefrologia", ScopeKey(uf="PA", ano=2014, mes=10), "ANPA1410.dbc"),
    ("sia_apac_radioterapia", ScopeKey(uf="AC", ano=2024, mes=1), "ARAC2401.dbc"),
    ("sia_atencao_domiciliar", ScopeKey(uf="MA", ano=2018, mes=10), "SADMA1810.dbc"),
]
# fmt: on

_IDS = [g[2] for g in GOLDEN]


@pytest.mark.parametrize(("dataset", "scope", "filename"), GOLDEN, ids=_IDS)
def test_filename_for_golden(dataset: str, scope: ScopeKey, filename: str) -> None:
    assert filename_for(resolve(dataset), scope) == filename


@pytest.mark.parametrize(("dataset", "scope", "filename"), GOLDEN, ids=_IDS)
def test_decode_for_inverts_filename_for(dataset: str, scope: ScopeKey, filename: str) -> None:
    assert decode_for(REGISTRY[dataset], filename) == scope


@pytest.mark.parametrize(("dataset", "scope", "filename"), GOLDEN, ids=_IDS)
def test_no_other_row_claims_the_name(dataset: str, scope: ScopeKey, filename: str) -> None:
    """ATDRR2401 must decode for the ATD row only, never for AD; ADAC2401 for AD only."""
    folders = set(REGISTRY[dataset].directories().values())
    claimants = {
        name
        for name, d in REGISTRY.items()
        if folders & set(d.directories().values()) and decode_for(d, filename) is not None
    }
    assert claimants == {dataset}


def test_every_registry_row_has_a_golden_case() -> None:
    assert {g[0] for g in GOLDEN} == set(REGISTRY)


# --- round-trip property over the whole space ------------------------------
# A two-digit year round-trips within the hundred years from the row's first year.


@settings(max_examples=300)
@given(
    dataset=st.sampled_from(sorted(REGISTRY)),
    uf=st.sampled_from(ALL_UFS),
    offset=st.integers(min_value=0, max_value=99),
    mes=st.integers(min_value=1, max_value=12),
)
def test_round_trip_property(dataset: str, uf: str, offset: int, mes: int) -> None:
    d = REGISTRY[dataset]
    ano = d.coverage[0][0] + offset
    scope = (
        ScopeKey(uf=None, ano=ano)
        if d.geography == "national"
        else ScopeKey(uf=uf, ano=ano, mes=mes if d.monthly else None)
    )
    assert decode_for(d, filename_for(d, scope)) == scope


def test_decode_for_rejects_foreign_and_malformed_names() -> None:
    d = REGISTRY["sim_obitos"]
    assert decode_for(d, "DNSP2024.dbc") is None
    assert decode_for(d, "DOSP24.dbc") is None
    assert decode_for(d, "DOSP2024.DBC") == ScopeKey(uf="SP", ano=2024)
    assert decode_for(REGISTRY["sih_aih_reduzida"], "RDSP2413.dbc") is None
