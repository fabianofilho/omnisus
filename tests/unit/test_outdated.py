"""outdated() notices a moved directory and a same-name republish, from real listings."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._ftp import ftp_host
from omnisus.sources.datasus_ftp._runner import ingest_raw
from omnisus.sources.datasus_ftp.datasets import REGISTRY
from tests.support.listings import fixture_entry, serve_listings

SINASC = REGISTRY["sinasc_nascidos_vivos"]
RR_2022 = Path(__file__).resolve().parents[1] / "fixtures" / "dbc" / "sinasc_rr_2022_mini.dbc"
OLD_DIR = "/dissemin/publicos/SINASC/NOV/DNRES"


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))


def test_the_registry_reads_the_directory_that_has_2023_and_2024() -> None:
    assert SINASC.ftp_dir == "/dissemin/publicos/SINASC/1996_/Dados/DNRES"


def test_final_2023_and_2024_are_available(monkeypatch) -> None:
    serve_listings(
        monkeypatch,
        {SINASC.ftp_dir: "sinasc_1996_dados_dnres", SINASC.prelim_dir: "sinasc_prelim_dnres"},
    )
    releases = sus.available_releases(SINASC.name, years=[2023, 2024], ufs=["RR"])
    assert releases == {ScopeKey("RR", 2023): "final", ScopeKey("RR", 2024): "final"}


def test_a_publication_from_the_old_directory_is_outdated(monkeypatch, tmp_path) -> None:
    raw = RR_2022.read_bytes()
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        # A lake imported before the move: same table, bytes recorded from NOV/DNRES.
        old_row = replace(SINASC, ftp_dir=OLD_DIR)
        entry = fixture_entry(OLD_DIR, "DNRR2022.dbc", raw)
        ingest_raw(old_row, ScopeKey("RR", 2022), [(entry, raw)], lake)
        serve_listings(
            monkeypatch,
            {SINASC.ftp_dir: "sinasc_1996_dados_dnres", SINASC.prelim_dir: "sinasc_prelim_dnres"},
        )
        assert sus.outdated(SINASC.name, lake=lake) == [ScopeKey("RR", 2022)]


def test_a_publication_matching_the_listing_is_current(monkeypatch, tmp_path) -> None:
    from omnisus.sources.datasus_ftp.inventory import list_sources

    serve_listings(
        monkeypatch,
        {SINASC.ftp_dir: "sinasc_1996_dados_dnres", SINASC.prelim_dir: "sinasc_prelim_dnres"},
    )
    entry = list_sources(SINASC)[ScopeKey("RR", 2022)].files[0]
    raw = RR_2022.read_bytes()
    assert len(raw) == entry.size_bytes, "fixture and listing disagree; see FIXTURES.md"
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        ingest_raw(SINASC, ScopeKey("RR", 2022), [(entry, raw)], lake)
        assert sus.outdated(SINASC.name, lake=lake) == []


def test_a_file_republished_at_the_same_path_is_outdated(monkeypatch, tmp_path) -> None:
    """DATASUS can rewrite a file without moving it; the recorded mtime then
    disagrees with what the server lists today, and that alone must be enough
    to report the scope (no fake bytes: same directory, name and size as the
    real listing — only ``modified`` is backdated to simulate the earlier,
    already-superseded publish)."""
    from omnisus.sources.datasus_ftp.inventory import list_sources

    serve_listings(
        monkeypatch,
        {SINASC.ftp_dir: "sinasc_1996_dados_dnres", SINASC.prelim_dir: "sinasc_prelim_dnres"},
    )
    entry = list_sources(SINASC)[ScopeKey("RR", 2022)].files[0]
    raw = RR_2022.read_bytes()
    assert len(raw) == entry.size_bytes, "fixture and listing disagree; see FIXTURES.md"
    stale = fixture_entry(
        entry.parent, entry.name, raw, modified=entry.modified - timedelta(days=1)
    )
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        ingest_raw(SINASC, ScopeKey("RR", 2022), [(stale, raw)], lake)
        assert sus.outdated(SINASC.name, lake=lake) == [ScopeKey("RR", 2022)]


def _legacy_lake(target: str, *, with_source_uri: bool) -> None:
    """A lake from before ``_omnisus_sources``: RR 2022 recorded from the old
    NOV/DNRES directory, then the child table dropped. Without
    ``with_source_uri`` the manifest also loses its URI, as v0.1.0 wrote it."""
    from omnisus.lake.publication import MANIFEST, SOURCES
    from omnisus.lake.sql import qualified

    raw = RR_2022.read_bytes()
    with Lake.local(target) as lake:
        entry = fixture_entry(OLD_DIR, "DNRR2022.dbc", raw)
        ingest_raw(replace(SINASC, ftp_dir=OLD_DIR), ScopeKey("RR", 2022), [(entry, raw)], lake)
        con = lake.connect()
        con.execute(f"DROP TABLE {qualified(lake.alias, SOURCES)}")
        if not with_source_uri:
            con.execute(f"UPDATE {qualified(lake.alias, MANIFEST)} SET source_uri = NULL")


def _serve_sinasc_listings(monkeypatch) -> None:
    serve_listings(
        monkeypatch,
        {SINASC.ftp_dir: "sinasc_1996_dados_dnres", SINASC.prelim_dir: "sinasc_prelim_dnres"},
    )


def test_a_legacy_publication_lists_its_manifest_uri_as_its_one_source(tmp_path) -> None:
    import hashlib

    target = f"ducklake:{tmp_path}/x.ducklake"
    _legacy_lake(target, with_source_uri=True)
    with Lake.local(target) as lake:
        (row,) = lake.publications()
    assert row["sources"] == [
        {
            "ordinal": 0,
            "source_uri": f"ftp://{ftp_host()}{OLD_DIR}/DNRR2022.dbc",
            "source_sha256": hashlib.sha256(RR_2022.read_bytes()).hexdigest(),
            "source_bytes": None,
            "source_modified": None,
        }
    ]


def test_a_publication_without_a_recorded_source_is_always_outdated(monkeypatch, tmp_path) -> None:
    """v0.1.0 manifests have no source_uri: nothing shows they match the server."""
    target = f"ducklake:{tmp_path}/x.ducklake"
    _legacy_lake(target, with_source_uri=False)
    _serve_sinasc_listings(monkeypatch)
    with Lake.local(target) as lake:
        assert lake.publications()[0]["sources"] == []
        assert sus.outdated(SINASC.name, lake=lake) == [ScopeKey("RR", 2022)]


def test_replacing_an_outdated_legacy_publication_records_its_listed_files(
    monkeypatch, tmp_path
) -> None:
    """The migration loop on a lake without ``_omnisus_sources``: outdated ->
    replace -> current, with the new directory's URI, size and mtime recorded."""
    from omnisus.sources.datasus_ftp import _runner
    from omnisus.sources.datasus_ftp.inventory import list_sources

    target = f"ducklake:{tmp_path}/x.ducklake"
    _legacy_lake(target, with_source_uri=True)
    _serve_sinasc_listings(monkeypatch)
    raw = RR_2022.read_bytes()

    async def fetch(entry, **_kw):
        return raw

    monkeypatch.setattr(_runner, "fetch_dbc_bytes", fetch)
    with Lake.local(target) as lake:
        assert sus.outdated(SINASC.name, lake=lake) == [ScopeKey("RR", 2022)]
    report = sus.import_dataset(
        SINASC.name,
        scopes=[ScopeKey("RR", 2022)],
        target=target,
        policy="replace",
        run_id="migrate-rr-2022",
    )
    assert report.outcomes[0].status == "ok", report.outcomes[0].reason
    listed = list_sources(SINASC)[ScopeKey("RR", 2022)].files[0]
    with Lake.local(target) as lake:
        assert sus.outdated(SINASC.name, lake=lake) == []
        (active,) = [p for p in lake.publications() if p["active"]]
    ((uri, size, modified),) = [
        (s["source_uri"], s["source_bytes"], s["source_modified"]) for s in active["sources"]
    ]
    assert uri == f"ftp://{ftp_host()}{SINASC.ftp_dir}/DNRR2022.dbc"
    assert (size, modified) == (listed.size_bytes, listed.modified.strftime("%Y-%m-%dT%H:%M"))
