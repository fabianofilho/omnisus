"""Tests for the dataset registry."""

from __future__ import annotations

from typing import Any

import pytest

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, Dataset, release_from_uri, resolve

ROWS = {
    "sim_obitos",
    "sinasc_nascidos_vivos",
    "sih_aih_reduzida",
    "sia_bpa_individualizado",
    "sia_apac_medicamentos",
    "sia_apac_quimioterapia",
    "sia_apac_tratamento_dialitico",
    "sia_apac_laudos_diversos",
    "sia_apac_cirurgia_bariatrica",
    "sia_psicossocial",
    "cnes_estabelecimentos",
    "sinan_chagas",
    "sinan_hanseniase",
    "sinan_tuberculose",
    "sinan_dengue",
    "sinan_violencia",
    "sia_producao_ambulatorial",
    "sia_producao_ambulatorial_1994_2007",
    "sih_aih_rejeitada",
    "sih_servicos_profissionais",
    "sih_aih_rejeitada_erro",
    "sih_aih_reduzida_1992_2007",
    "cnes_dados_complementares",
    "cnes_equipamentos",
    "cnes_equipes",
    "cnes_estabelecimentos_ensino",
    "cnes_estabelecimentos_filantropicos",
    "cnes_gestao_metas",
    "cnes_habilitacoes",
    "cnes_incentivos",
    "cnes_leitos",
    "cnes_regras_contratuais",
    "cnes_servicos_especializados",
    "sim_obitos_fetais",
    "sim_obitos_externos",
    "sim_obitos_infantis",
    "sim_obitos_maternos",
    "sim_obitos_cid9",
    "sinasc_1994_1995",
    # SIA families named in Informe Técnico SIASUS 2019-07
    "sia_apac_acompanhamento_bariatrica",
    "sia_apac_fistula_arteriovenosa",
    "sia_apac_acompanhamento_multiprofissional",
    "sia_apac_nefrologia",
    "sia_apac_radioterapia",
    "sia_atencao_domiciliar",
}


def _adhoc(**over: Any) -> Dataset:
    base: dict[str, Any] = {
        "name": "custom",
        "prefix": "DO",
        "ftp_dir": "/dissemin/publicos/X",
        "cadence": "yearly",
        "partition_by": ("ano", "uf"),
        "coverage": ((2000, 1), None),
    }
    return Dataset(**{**base, **over})


def test_registry_has_exactly_the_supported_ftp_datasets() -> None:
    assert set(REGISTRY) == ROWS


def test_cnes_professionals_are_out_of_scope() -> None:
    """CNES PF names each professional with CPF and CNS and serves no clinical question."""
    assert "cnes_profissionais" not in REGISTRY


def test_names_are_full_readable_words() -> None:
    """<sistema>_<conteúdo>, never a two-letter file prefix or a release."""
    for name, d in REGISTRY.items():
        _system, _, content = name.partition("_")
        assert content, name
        assert content.lower() != d.prefix.lower(), name
        assert not name.endswith(("_prelim", "_final")), name


def test_module_has_no_alias_surface() -> None:
    import omnisus.sources.datasus_ftp.datasets as m

    assert not hasattr(m, "ALIASES")
    assert not hasattr(m, "get_config")
    assert "aliases" not in Dataset.__dataclass_fields__


def test_registry_keys_equal_row_names() -> None:
    for key, d in REGISTRY.items():
        assert key == d.name


def test_monthly_is_derived_from_cadence_not_partition_by() -> None:
    # cadence (upstream fact) and partition_by (our layout) are distinct
    assert _adhoc(cadence="monthly", partition_by=("ano",)).monthly is True
    assert _adhoc(cadence="yearly", partition_by=("ano", "uf", "mes")).monthly is False


def test_row_is_frozen() -> None:
    d = _adhoc()
    with pytest.raises((AttributeError, TypeError)):
        d.name = "other"  # type: ignore[misc]


def test_dictionary_defaults_to_none_meaning_packaged_yaml() -> None:
    assert REGISTRY["sim_obitos"].dictionary is None


def test_resolve_by_key_returns_the_registry_object() -> None:
    assert resolve("sim_obitos") is REGISTRY["sim_obitos"]


def test_resolve_passes_a_value_through_untouched() -> None:
    d = _adhoc()
    assert resolve(d) is d


def test_resolve_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown dataset"):
        resolve("bogus")


def test_adhoc_dataset_flows_through_codec() -> None:
    """A Dataset value not in REGISTRY works through the same functions."""
    from tests.support.datasus_names import filename_for

    d = _adhoc(name="sim_cid9", prefix="DO", ftp_dir="/dissemin/publicos/SIM/CID9/DORES")
    scope = ScopeKey(uf="SP", ano=1995)
    assert filename_for(d, scope) == "DOSP1995.dbc"
    assert d.directories() == {"final": "/dissemin/publicos/SIM/CID9/DORES"}


def test_adhoc_monthly_dataset_builds_monthly_filename() -> None:
    from tests.support.datasus_names import filename_for

    d = _adhoc(name="sia_pa", prefix="PA", cadence="monthly", partition_by=("ano", "uf", "mes"))
    assert filename_for(d, ScopeKey(uf="RR", ano=2024, mes=3)) == "PARR2403.dbc"


def test_dataset_is_keyword_only() -> None:
    """ADR 0002: ``Dataset`` is constructible only by keyword, never
    positionally — a positional call must raise ``TypeError``."""
    with pytest.raises(TypeError):
        Dataset(  # type: ignore[misc]
            "custom",
            "DO",
            "/dissemin/publicos/X",
            "yearly",
            ("ano", "uf"),
            ((2000, 1), None),
        )


def test_directories_is_final_only_without_prelim_dir() -> None:
    assert _adhoc().directories() == {"final": "/dissemin/publicos/X"}


def test_directories_lists_prelim_after_final() -> None:
    d = _adhoc(prelim_dir="/dissemin/publicos/X/PRELIM")
    assert list(d.directories().items()) == [
        ("final", "/dissemin/publicos/X"),
        ("prelim", "/dissemin/publicos/X/PRELIM"),
    ]


def test_rows_with_a_preliminary_directory_declare_it() -> None:
    assert REGISTRY["sim_obitos"].prelim_dir == "/dissemin/publicos/SIM/PRELIM/DORES"
    assert REGISTRY["sinasc_nascidos_vivos"].prelim_dir == "/dissemin/publicos/SINASC/PRELIM/DNRES"
    chagas = REGISTRY["sinan_chagas"]
    assert chagas.ftp_dir == "/dissemin/publicos/SINAN/DADOS/FINAIS"
    assert chagas.prelim_dir == "/dissemin/publicos/SINAN/DADOS/PRELIM"
    assert chagas.coverage[0] == (2000, 1)


def test_release_from_uri_recognises_both_directories() -> None:
    assert (
        release_from_uri(
            "sim_obitos",
            "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/PRELIM/DORES/DOSP2025.dbc",
        )
        == "prelim"
    )
    assert (
        release_from_uri(
            "sim_obitos", "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DOSP2024.dbc"
        )
        == "final"
    )
    assert release_from_uri("sim_obitos", None) is None
    assert release_from_uri("not_a_row", "ftp://ftp.datasus.gov.br/x/y.dbc") is None
    assert (
        release_from_uri("sim_obitos", "ftp://ftp.datasus.gov.br/elsewhere/DOSP2024.dbc") is None
    )
