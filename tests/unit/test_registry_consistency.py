"""Tier 2: the registry is internally consistent and every row is
reachable. This is the test that makes the SIA gap (seven SIA datasets with
no public door) impossible.
"""

from __future__ import annotations

from importlib.resources import files

import pytest

import omnisus as sus
import omnisus.cli.main as cli_main
from omnisus.cli.main import dataset_choices
from omnisus.sources.datasus_ftp.datasets import REGISTRY

NON_FTP_DATASETS = set(cli_main._NON_FTP.values())
"""Datasets with their own importer and YAML but no registry row.
Derived from the CLI's own dispatch table — one fact source."""


def _packaged_yaml_stems() -> set[str]:
    root = files("omnisus.data.dicionarios")
    return {p.name.removesuffix(".yaml") for p in root.iterdir() if p.name.endswith(".yaml")}


def test_a_every_row_has_a_packaged_dictionary() -> None:
    missing = {name for name in REGISTRY if name not in _packaged_yaml_stems()}
    assert not missing, f"registry rows without dicionarios/<name>.yaml: {sorted(missing)}"


def test_b_cli_accepts_every_row_and_non_ftp_entry() -> None:
    assert set(dataset_choices()) == set(REGISTRY) | set(cli_main._NON_FTP)


def test_b_python_api_accepts_every_row() -> None:
    for name in REGISTRY:
        filters = {} if REGISTRY[name].geography == "national" else {"ufs": ["RR"], "months": [1]}
        scopes = sus.scopes_for(name, years=[2024], **filters)
        assert scopes, name


def test_d_prefixes_are_unique() -> None:
    """Per directory: RD and PA each have a row in two directories (one per era)."""
    keys = [(d.prefix, d.ftp_dir) for d in REGISTRY.values()]
    assert len(keys) == len(set(keys)), sorted(keys)


def test_e_cadence_agrees_with_partition_layout() -> None:
    """Agreement between two distinct facts — never derivation."""
    for d in REGISTRY.values():
        assert d.monthly == ("mes" in d.partition_by), d.name


def test_f_every_non_aux_yaml_has_exactly_one_owner() -> None:
    owners = set(REGISTRY) | NON_FTP_DATASETS
    yamls = {s for s in _packaged_yaml_stems() if not s.startswith("aux_")}
    assert yamls == owners, (
        f"unowned yaml: {sorted(yamls - owners)}; owner without yaml: {sorted(owners - yamls)}"
    )


def test_keys_equal_names() -> None:
    for key, d in REGISTRY.items():
        assert key == d.name


def test_coverage_is_well_formed() -> None:
    """``coverage`` is written but never checked elsewhere — validate the
    shape here so a bad ``(year, month)`` pair can't silently sit in the
    registry (a row must not lie)."""
    for d in REGISTRY.values():
        first, last = d.coverage
        assert 1 <= first[1] <= 12, d.name
        assert first[0] >= 1979, d.name
        if last is not None:
            assert 1 <= last[1] <= 12, d.name
            assert last >= first, d.name


def test_d_inventory_advertises_exactly_what_available_accepts() -> None:
    """The CLI's advertised set and the function's accepted set are the same
    set. A name offered in help that `available` rejects is a lie in the UI."""
    from omnisus.cli.main import ftp_dataset_choices

    assert set(ftp_dataset_choices()) == set(REGISTRY)


def _file(name: str, when: str = "01-31-20  02:48PM", size: int = 76107) -> str:
    return f"{when}         {size:>12} {name}"


def test_c_available_accepts_exactly_the_registry(monkeypatch, tmp_path) -> None:
    """Tier 2: available() accepts every registry key, and
    rejects everything else. Offline — the stubbed listing includes one
    real line, so this doesn't also pass against an available() that always
    returns []."""
    from omnisus.sources._base import ScopeKey
    from omnisus.sources.datasus_ftp.datasets import REGISTRY
    from omnisus.sources.datasus_ftp.inventory import available

    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))
    prelim_dirs = {d.prelim_dir for d in REGISTRY.values() if d.prelim_dir is not None}

    def fake(path: str, _t: float) -> list[str]:
        return [] if path in prelim_dirs else [_file("DOAC1996.dbc")]

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", fake)
    for name in REGISTRY:
        available(name)  # accepted: must not raise, for every registry key
    assert available("sim_obitos") == [ScopeKey(uf="AC", ano=1996)], (
        "the row whose prefix matches the stubbed line must decode it"
    )
    with pytest.raises(ValueError, match="unknown dataset"):
        available("definitely_not_a_dataset")
