"""Import tolerance: a gap in the range must not kill the run.

The server is ``tests/support/fake_datasus``: a scope it does not list is a
gap. Where the fetch path itself is the subject, the real fetcher runs over
a patched ``_blocking_fetch`` — the synchronous seam — never ``ftplib.FTP``.
No network.
"""

from __future__ import annotations

import ftplib
from pathlib import Path
from unittest.mock import patch

import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp import fetch
from tests.support import fake_datasus


def test_a_gap_mid_run_is_skipped_and_the_run_continues(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """The old defect: the first missing file aborted the whole run and
    discarded every result already collected, including rows already committed.

    Three scopes, the middle one absent upstream. Before tolerance this raised
    on scope 2 and lost scope 1's result; now all three are reported.
    """
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    scopes = [ScopeKey(uf="RR", ano=y) for y in (2021, 2022, 2023)]
    fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: raw, scopes[2]: raw})

    report = sus.import_dataset(
        "sim_obitos", scopes=scopes, target=f"ducklake:{tmp_path}/t.ducklake"
    )

    assert len(report.outcomes) == 3, "every scope must be accounted for"
    assert [o.status for o in report.outcomes] == ["ok", "skipped", "ok"]
    assert report.outcomes[1].code == "not_listed"
    assert len(report.ok) == 2
    assert not report.failed
    # The scope after the gap was still imported — the run did not stop.
    assert report.ok[-1].scope == ScopeKey(uf="RR", ano=2023)
    assert report.rows > 0


def test_a_missing_scope_is_skipped_never_failed(monkeypatch, tmp_path: Path) -> None:
    """`skipped` and `failed` are different facts. A dataset DATASUS never
    published for a UF is not an error, and must not make the CLI exit 1."""
    fetched = fake_datasus.serve(monkeypatch, "sim_obitos", {})

    report = sus.import_dataset(
        "sim_obitos",
        scopes=[ScopeKey(uf="RR", ano=2023)],
        target=f"ducklake:{tmp_path}/t.ducklake",
    )

    assert len(report.skipped) == 1
    assert report.skipped[0].code == "not_listed"
    assert not report.failed
    assert report.rows == 0
    assert fetched == []


def test_a_transient_failure_is_failed_never_skipped(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """The other direction, and the one that matters for orchestration: a
    server that is merely busy must not be reported as 'this does not exist'."""
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): raw})
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", fetch.fetch_dbc_bytes
    )

    def always_throttled(*_a: object) -> bytes:
        raise ftplib.error_perm("530 maximum number of allowed clients")

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        side_effect=always_throttled,
    ):
        report = sus.import_dataset(
            "sim_obitos",
            scopes=[ScopeKey(uf="RR", ano=2023)],
            target=f"ducklake:{tmp_path}/t.ducklake",
        )

    assert len(report.failed) == 1
    assert report.failed[0].code == "fetch_failed"
    assert not report.skipped, "a throttle is not a missing file"


def test_out_of_coverage_scopes_are_never_downloaded(monkeypatch, tmp_path: Path) -> None:
    """The cheapest filter. sim_obitos starts in 1996, so 1990 cannot exist — and
    the run must not spend a download finding that out."""
    fetched = fake_datasus.serve(monkeypatch, "sim_obitos", {})
    report = sus.import_dataset(
        "sim_obitos",
        scopes=[ScopeKey(uf="RR", ano=1990), ScopeKey(uf="RR", ano=1991)],
        target=f"ducklake:{tmp_path}/t.ducklake",
    )

    assert fetched == [], "coverage must reject these before any download"
    assert len(report.skipped) == 2
    assert all("coverage" in (o.reason or "") for o in report.skipped)
    assert all(o.code == "outside_coverage" for o in report.skipped)


def test_a_monthly_dataset_without_a_month_fails_fast(tmp_path: Path) -> None:
    """A caller bug, not an upstream condition: it affects every scope equally,
    so it raises before the run rather than becoming N identical failures that
    look like a server problem. No listing is faked: the unit-test network
    guard turns a LIST into a failure, so this also proves none is made."""
    with (
        patch("omnisus.sources.datasus_ftp.fetch._blocking_fetch") as spy,
        pytest.raises(ValueError, match="monthly"),
    ):
        sus.import_dataset(
            "sih_aih_reduzida",
            scopes=[ScopeKey(uf="RR", ano=2024)],
            target=f"ducklake:{tmp_path}/t.ducklake",
        )
    assert spy.call_count == 0


def test_report_counts_rows_only_from_successful_scopes(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): raw})
    report = sus.import_dataset(
        "sim_obitos",
        scopes=[ScopeKey(uf="RR", ano=2022), ScopeKey(uf="RR", ano=2023)],
        target=f"ducklake:{tmp_path}/t.ducklake",
    )
    assert report.rows == sum(o.result.rows for o in report.ok if o.result)
    assert report.rows > 0
