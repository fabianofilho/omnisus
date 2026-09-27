"""Tests for the top-level API: scopes_for, import_dataset."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY
from omnisus.sources.datasus_ftp.inventory import FtpEntry, ResolvedSource
from tests.support import fake_datasus


def test_scopes_for_yearly_ignores_months() -> None:
    assert sus.scopes_for("sim_obitos", years=[2023], ufs=["RR"], months=[1, 2]) == [
        ScopeKey(uf="RR", ano=2023)
    ]


def test_scopes_for_monthly_defaults_to_twelve_months() -> None:
    scopes = sus.scopes_for("sih_aih_reduzida", years=[2024], ufs=["RR"])
    assert len(scopes) == 12
    assert scopes[0] == ScopeKey(uf="RR", ano=2024, mes=1)
    assert scopes[-1] == ScopeKey(uf="RR", ano=2024, mes=12)


def test_scopes_for_all_ufs_when_none() -> None:
    assert len(sus.scopes_for("sim_obitos", years=[2023])) == len(sus.ALL_UFS) == 27


def test_scopes_for_order_is_year_then_uf_then_month() -> None:
    scopes = sus.scopes_for(
        "sih_aih_reduzida", years=[2023, 2024], ufs=["AC", "RR"], months=[1, 2]
    )
    assert [(s.ano, s.uf, s.mes) for s in scopes] == [
        (2023, "AC", 1),
        (2023, "AC", 2),
        (2023, "RR", 1),
        (2023, "RR", 2),
        (2024, "AC", 1),
        (2024, "AC", 2),
        (2024, "RR", 1),
        (2024, "RR", 2),
    ]


def test_scopes_for_accepts_a_dataset_value() -> None:
    by_key = sus.scopes_for("sim_obitos", years=[2023], ufs=["RR"])
    by_value = sus.scopes_for(REGISTRY["sim_obitos"], years=[2023], ufs=["RR"])
    assert by_key == by_value == [ScopeKey(uf="RR", ano=2023)]


def test_import_dataset_reaches_the_sia_family(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    """Seven SIA datasets had no public door. Now every row has one."""
    fake_datasus.serve(
        monkeypatch,
        "sia_apac_tratamento_dialitico",
        {ScopeKey(uf="RR", ano=2024, mes=1): dbc_fixture("sia_atd_rr_2024_01_mini").read_bytes()},
    )
    target = f"ducklake:{tmp_path}/api.ducklake"

    report = sus.import_dataset(
        "sia_apac_tratamento_dialitico",
        scopes=sus.scopes_for(
            "sia_apac_tratamento_dialitico", years=[2024], ufs=["RR"], months=[1]
        ),
        target=target,
    )

    assert len(report.outcomes) == 1
    assert report.ok[0].result is not None
    assert report.rows > 0
    with Lake.local(target) as lake:
        assert "sia_apac_tratamento_dialitico" in lake.tables()


def test_import_dataset_accepts_hand_built_scopes(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """Planning is composition: any list[ScopeKey] works."""
    fake_datasus.serve(
        monkeypatch,
        "sim_obitos",
        {ScopeKey(uf="RR", ano=2023): dbc_fixture("sim_rr_2023_mini").read_bytes()},
    )
    target = f"ducklake:{tmp_path}/handbuilt.ducklake"

    report = sus.import_dataset("sim_obitos", scopes=[ScopeKey(uf="RR", ano=2023)], target=target)

    assert report.rows > 0
    with Lake.local(target) as lake:
        assert "sim_obitos" in lake.tables()


def test_public_import_functions_are_the_readable_ones() -> None:
    """One generic FTP entry point plus the importers that carry behaviour of
    their own. Short-name aliases (``import_sim`` …) were removed in 0.2.0."""
    importers = sorted(name for name in sus.__all__ if name.startswith("import_"))
    assert importers == [
        "import_cnes_master",
        "import_dataset",
        "import_ibge_populacao",
        "import_research",
        "import_sigtap",
    ]


def test_import_aborted_error_is_public_and_retains_progress_payload() -> None:
    report = sus.ImportReport(outcomes=())
    unresolved = ((0, ScopeKey(uf="RR", ano=2023)),)

    error = sus.ImportAbortedError(report, unresolved)

    assert isinstance(error, RuntimeError)
    assert error.report is report
    assert error.unresolved == unresolved


_FIXTURE_FOR: dict[str, tuple[str, ScopeKey]] = {
    "sinan_chagas": ("sinan_chagas_br_2023", ScopeKey(uf=None, ano=2023)),
    "sinan_hanseniase": ("sinan_hanseniase_br_2026", ScopeKey(uf=None, ano=2026)),
    "sinan_tuberculose": ("sinan_tuberculose_br_2020_excerpt", ScopeKey(uf=None, ano=2020)),
    "sim_obitos": ("sim_rr_2023_mini", ScopeKey(uf="RR", ano=2023)),
    "sinasc_nascidos_vivos": ("sinasc_rr_2022_mini", ScopeKey(uf="RR", ano=2022)),
    "sih_aih_reduzida": ("sih_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_bpa_individualizado": ("sia_bi_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_apac_medicamentos": ("sia_am_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_apac_quimioterapia": ("sia_aq_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_apac_tratamento_dialitico": (
        "sia_atd_rr_2024_01_mini",
        ScopeKey(uf="RR", ano=2024, mes=1),
    ),
    "sia_apac_laudos_diversos": ("sia_ad_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_psicossocial": ("sia_ps_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_apac_cirurgia_bariatrica": (
        "sia_abo_sp_2024_01_mini",
        ScopeKey(uf="SP", ano=2024, mes=1),
    ),
    "cnes_estabelecimentos": ("cnes_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_producao_ambulatorial": ("sia_pa_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sia_producao_ambulatorial_1994_2007": (
        "sia_pa_rr_2007_12_mini",
        ScopeKey(uf="RR", ano=2007, mes=12),
    ),
    "sih_aih_rejeitada": ("sih_rj_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sih_servicos_profissionais": ("sih_sp_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sih_aih_rejeitada_erro": ("sih_er_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "sih_aih_reduzida_1992_2007": ("sih_rd_rr_2007_12_mini", ScopeKey(uf="RR", ano=2007, mes=12)),
    "cnes_dados_complementares": ("cnes_dc_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_equipamentos": ("cnes_eq_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_equipes": ("cnes_ep_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_gestao_metas": ("cnes_gm_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_habilitacoes": ("cnes_hb_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_incentivos": ("cnes_in_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_leitos": ("cnes_lt_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_regras_contratuais": ("cnes_rc_rr_2024_01_mini", ScopeKey(uf="RR", ano=2024, mes=1)),
    "cnes_servicos_especializados": (
        "cnes_sr_rr_2024_01_mini",
        ScopeKey(uf="RR", ano=2024, mes=1),
    ),
    "cnes_estabelecimentos_filantropicos": (
        "cnes_ef_ap_2024_01_mini",
        ScopeKey(uf="AP", ano=2024, mes=1),
    ),
    "sim_obitos_fetais": ("sim_dofet_br_2023_excerpt", ScopeKey(uf=None, ano=2023)),
    "sim_obitos_externos": ("sim_doext_br_2023_excerpt", ScopeKey(uf=None, ano=2023)),
    "sim_obitos_infantis": ("sim_doinf_br_2023_excerpt", ScopeKey(uf=None, ano=2023)),
    "sim_obitos_maternos": ("sim_domat_br_2023_mini", ScopeKey(uf=None, ano=2023)),
    "sim_obitos_cid9": ("sim_cid9_rr_1995_mini", ScopeKey(uf="RR", ano=1995)),
    "sinasc_1994_1995": ("sinasc_rr_1995_mini", ScopeKey(uf="RR", ano=1995)),
    "cnes_estabelecimentos_ensino": (
        "cnes_ee_rr_2019_12_mini",
        ScopeKey(uf="RR", ano=2019, mes=12),
    ),
    "sia_apac_acompanhamento_bariatrica": (
        "sia_ab_se_2025_07_mini",
        ScopeKey(uf="SE", ano=2025, mes=7),
    ),
    "sia_apac_fistula_arteriovenosa": (
        "sia_acf_rr_2024_01_mini",
        ScopeKey(uf="RR", ano=2024, mes=1),
    ),
    "sia_apac_acompanhamento_multiprofissional": (
        "sia_amp_df_2024_01_mini",
        ScopeKey(uf="DF", ano=2024, mes=1),
    ),
    "sia_apac_nefrologia": ("sia_an_pa_2014_10_mini", ScopeKey(uf="PA", ano=2014, mes=10)),
    "sia_apac_radioterapia": ("sia_ar_ac_2024_01_mini", ScopeKey(uf="AC", ano=2024, mes=1)),
    "sia_atencao_domiciliar": ("sia_sad_ma_2018_10_mini", ScopeKey(uf="MA", ano=2018, mes=10)),
}


def test_fixture_map_covers_every_registry_row() -> None:
    """A new registry row without a fixture here would silently skip Tier 2
    coverage — assert the map is complete instead."""
    assert set(_FIXTURE_FOR) == set(REGISTRY)


def test_the_fixture_builder_can_rebuild_every_fixture_this_map_names() -> None:
    """conftest tells a developer with a missing fixture to run
    scripts/build_fixtures.py. That was a dead end for 6 of the 11 datasets,
    because the script carried its own hand-copied path map covering 5. Assert
    the two agree, so the instruction stays true."""
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "build_fixtures.py"
    spec = importlib.util.spec_from_file_location("build_fixtures", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    built = {
        dataset: (fname.removesuffix(".dbc"), scope) for dataset, scope, fname in module.TARGETS
    }
    assert built == _FIXTURE_FOR


@pytest.mark.parametrize("dataset_name", sorted(REGISTRY))
def test_import_dataset_reaches_every_registry_row(
    dataset_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dbc_fixture
) -> None:
    """Tier 2: every registry row is proven end to end, not just sia_apac_tratamento_dialitico and
    sia_bpa_individualizado — this is what makes the SIA gap impossible."""
    fixture_name, scope = _FIXTURE_FOR[dataset_name]
    fake_datasus.serve(monkeypatch, dataset_name, {scope: dbc_fixture(fixture_name).read_bytes()})
    target = f"ducklake:{tmp_path}/{dataset_name}.ducklake"

    report = sus.import_dataset(dataset_name, scopes=[scope], target=target)

    assert not report.failed, report.failed
    assert report.rows > 0
    with Lake.local(target) as lake:
        assert dataset_name in lake.tables()


def test_available_and_browse_are_exported() -> None:
    import omnisus as sus

    for name in (
        "available",
        "available_releases",
        "browse",
        "FtpEntry",
        "FtpPathNotFound",
        "FtpUnavailable",
    ):
        assert name in sus.__all__, name
        assert hasattr(sus, name), name


def test_policy_type_and_dataset_resolver_are_exported() -> None:
    from typing import get_args

    assert {"ImportPolicy", "resolve"} <= set(sus.__all__)
    assert get_args(sus.ImportPolicy) == ("append", "skip_same", "error_if_exists", "replace")
    assert sus.resolve("sim_obitos").name == "sim_obitos"


def test_catalog_attach_error_is_exported() -> None:
    from omnisus.lake import CatalogAttachError

    assert "CatalogAttachError" in sus.__all__
    assert sus.CatalogAttachError is CatalogAttachError
    assert issubclass(CatalogAttachError, RuntimeError)


def test_lake_reader_is_exported() -> None:
    from omnisus.lake import LakeReader

    assert "LakeReader" in sus.__all__
    assert sus.LakeReader is LakeReader


def test_products_state_what_each_importer_family_supports() -> None:
    """The Omnisus app rebuilt this catalog by hand, treating ibge_populacao and
    cnes_master as special cases. One frozen record per family says it here."""
    from dataclasses import FrozenInstanceError
    from typing import get_args

    products = {p.name: p for p in sus.products()}
    assert set(products) == set(REGISTRY) | {"ibge_populacao", "cnes_master"}
    assert [d.name for d in sus.datasets()] == list(REGISTRY)
    for dataset in sus.datasets():
        product = products[dataset.name]
        assert product.dataset is dataset
        if dataset.geography == "national":
            assert product.scope_fields == ("ano",)
        else:
            assert product.scope_fields == (
                ("uf", "ano", "mes") if dataset.monthly else ("uf", "ano")
            )
        assert product.policies == get_args(sus.ImportPolicy)
        assert (product.reconcile_by, product.inventory) == ("run_id", True)
    assert products["ibge_populacao"] == sus.Product(
        "ibge_populacao", None, ("product", "ano"), ("append",), "publication_id", False
    )
    assert products["cnes_master"] == sus.Product(
        "cnes_master", None, (), ("append",), "rerun", False
    )
    with pytest.raises(FrozenInstanceError):
        products["ibge_populacao"].inventory = True  # type: ignore[misc]
    assert {"Product", "datasets", "products"} <= set(sus.__all__)


def test_deletion_result_is_exported() -> None:
    from omnisus.lake.publication import DeletionResult

    assert "DeletionResult" in sus.__all__
    assert sus.DeletionResult is DeletionResult


def test_available_needs_no_lake(monkeypatch, tmp_path: Path) -> None:
    """Discovery is decoupled from the lake — it works before `init`."""
    import omnisus as sus
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))
    sim_dir = REGISTRY["sim_obitos"].ftp_dir

    def fake(path: str, _t: float) -> list[str]:
        if path == sim_dir:
            return ["01-31-20  02:48PM                76107 DOAC1996.dbc"]
        return []

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", fake)
    assert sus.available("sim_obitos") == [ScopeKey(uf="AC", ano=1996)]
    assert not list(tmp_path.glob("*.ducklake"))


def _listed(path: str) -> FtpEntry:
    """A server listing entry at ``path``, for tests that only care about the path."""
    return FtpEntry(
        name=path.rsplit("/", 1)[-1],
        path=path,
        parent=path.rsplit("/", 1)[0],
        is_dir=False,
        size_bytes=1,
        modified=datetime(2024, 1, 1, 0, 0),
    )


def test_outdated_lists_scopes_whose_directory_moved(tmp_path, monkeypatch) -> None:
    import polars as pl

    target = f"ducklake:{tmp_path}/l.ducklake"
    with Lake.local(target) as lake:
        for year, release in ((2024, "FINAIS"), (2025, "PRELIM"), (2026, "PRELIM")):
            p = tmp_path / "d.parquet"
            pl.DataFrame({"_source_ano": [year], "v": [1]}).write_parquet(p)
            lake.publish_scope(
                "sinan_chagas",
                p,
                scope=ScopeKey(uf=None, ano=year),
                source_sha256=str(year) * 16,
                parser_version="v1",
                source_uri=f"ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/{release}/CHAGBR{year % 100}.dbc",
            )
    server = {
        # 2024 is still listed as final, at the same path: unchanged.
        ScopeKey(uf=None, ano=2024): ResolvedSource(
            "final",
            (_listed("/dissemin/publicos/SINAN/DADOS/FINAIS/CHAGBR24.dbc"),),
        ),
        # 2025 moved from PRELIM to FINAIS under a new path: outdated.
        ScopeKey(uf=None, ano=2025): ResolvedSource(
            "final",
            (_listed("/dissemin/publicos/SINAN/DADOS/FINAIS/CHAGBR25.dbc"),),
        ),
        ScopeKey(uf=None, ano=2027): ResolvedSource("prelim", ()),
    }
    monkeypatch.setattr("omnisus.list_sources", lambda *a, **k: server)
    with Lake.local(target) as lake:
        # 2026 is in the lake but no longer on the server: a withdrawal, not an outdated file
        assert sus.outdated("sinan_chagas", lake=lake) == [ScopeKey(uf=None, ano=2025)]


def test_outdated_lists_the_single_directory_row_too(tmp_path, monkeypatch) -> None:
    """sia_bpa_individualizado has no preliminary directory, but its final
    directory can still be republished under the same name, so outdated()
    lists it like any other row instead of special-casing it away. With
    nothing published here, the answer is still []."""
    sia_dir = REGISTRY["sia_bpa_individualizado"].ftp_dir
    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))

    def fake(path: str, _t: float) -> list[str]:
        if path == sia_dir:
            return []
        raise AssertionError(f"unexpected LIST {path!r}")

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", fake)
    with Lake.local(f"ducklake:{tmp_path}/l.ducklake") as lake:
        assert sus.outdated("sia_bpa_individualizado", lake=lake) == []
