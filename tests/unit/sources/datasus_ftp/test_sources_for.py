"""Scope resolution from real listings: parts, supersession, national files."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, release_of
from omnisus.sources.datasus_ftp.inventory import (
    Listing,
    _parse_msdos_line,
    available,
    list_sources,
    sources_for,
)
from tests.support.listings import listing_lines, serve_listings

BI = REGISTRY["sia_bpa_individualizado"]
SIM = REGISTRY["sim_obitos"]
SIA_DIR = "/dissemin/publicos/SIASUS/200801_/Dados"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))


def _listing(fixture: str, path: str) -> Listing:
    entries = [_parse_msdos_line(line, path) for line in listing_lines(fixture)]
    return Listing(entries=tuple(e for e in entries if e is not None), skipped=0, path=path)


def test_a_month_published_only_as_parts_resolves_to_its_parts_in_order() -> None:
    resolved = sources_for(BI, {"final": _listing("siasus_200801_dados", SIA_DIR)})
    source = resolved[ScopeKey("MG", 2024, 12)]
    assert source.release == "final"
    assert [e.name for e in source.files] == ["BIMG2412_1.dbc", "BIMG2412_2.dbc"]


def test_parts_supersede_the_whole_file_of_the_same_month() -> None:
    resolved = sources_for(BI, {"final": _listing("siasus_200801_dados", SIA_DIR)})
    names = [e.name for e in resolved[ScopeKey("MG", 2024, 1)].files]
    assert "BIMG2401.dbc" not in names
    assert names[0] == "BIMG2401_1.dbc"


def test_months_that_were_invisible_before_are_now_available(monkeypatch) -> None:
    serve_listings(monkeypatch, {SIA_DIR: "siasus_200801_dados"})
    scopes = available(BI, years=[2024], ufs=["MG"])
    assert ScopeKey("MG", 2024, 12) in scopes
    assert len(scopes) == 12


def test_the_national_file_is_not_a_scope(monkeypatch) -> None:
    """The real CID10/DORES listing has DOBR files. ``list_sources`` lists both
    of the row's directories and no SIM PRELIM listing is committed, so the
    real SINASC PRELIM listing answers that directory: its DN names never carry
    SIM's DO prefix, so it adds no SIM scope."""
    serve_listings(
        monkeypatch,
        {SIM.ftp_dir: "sim_cid10_dores", SIM.prelim_dir: "sinasc_prelim_dnres"},
    )
    assert all(s.uf != "BR" for s in list_sources(SIM))


def test_a_scope_in_two_release_directories_raises() -> None:
    listing = _listing("sim_cid10_dores", SIM.ftp_dir)
    with pytest.raises(ValueError, match="published as both"):
        sources_for(SIM, {"final": listing, "prelim": listing})


def test_release_of_names_the_directory_of_the_row() -> None:
    assert release_of(SIM, SIM.ftp_dir) == "final"
    assert release_of(SIM, SIM.prelim_dir + "/") == "prelim"
    assert release_of(SIM, "/dissemin/publicos/SIM/CID9/DORES") is None


RD_DIR = "/dissemin/publicos/SIHSUS/199201_200712/Dados"


@pytest.mark.parametrize(
    ("dataset", "months"),
    [
        ("sih_aih_reduzida_1992_1997", {(y, m) for y in range(1992, 1998) for m in range(1, 13)}),
        ("sih_aih_reduzida_1998_2007", {(y, m) for y in range(1998, 2008) for m in range(1, 13)}),
    ],
)
def test_the_rd_eras_share_a_directory_and_each_resolves_only_its_months(
    monkeypatch, dataset, months
) -> None:
    """Issue #12, decision 1: one directory, two rows cut by `coverage` at 1998-01."""
    assert REGISTRY[dataset].ftp_dir == RD_DIR
    serve_listings(monkeypatch, {RD_DIR: "sihsus_199201_200712_dados_rd"})
    scopes = available(REGISTRY[dataset], ufs=["RR"])
    assert {(s.ano, s.mes) for s in scopes} <= months
    assert {(s.ano, s.mes) for s in scopes} >= {min(months), max(months)}
