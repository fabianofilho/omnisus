"""Fetch overlaps parse; both stay bounded.

The listing comes from ``tests/support/fake_datasus``; downloads run through
the real fetcher, patched at ``_blocking_fetch`` — the synchronous seam — so
the probe counts real in-flight transfers. No network.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp import fetch
from tests.support import fake_datasus


def _list(monkeypatch: pytest.MonkeyPatch, scopes: list[ScopeKey], payload: bytes) -> None:
    """List ``scopes`` for sim_obitos, and download them with the real fetcher."""
    fake_datasus.serve(monkeypatch, "sim_obitos", dict.fromkeys(scopes, payload))
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", fetch.fetch_dbc_bytes
    )


class _ConcurrencyProbe:
    """Counts how many fetches are genuinely in flight at once."""

    def __init__(self, payload: bytes, delay: float = 0.05) -> None:
        self.payload = payload
        self.delay = delay
        self._live = 0
        self.peak = 0
        self.total = 0
        self._lock = threading.Lock()

    def __call__(self, _remote_dir: str, _filename: str, _timeout: float) -> bytes:
        with self._lock:
            self._live += 1
            self.total += 1
            self.peak = max(self.peak, self._live)
        try:
            time.sleep(self.delay)
            return self.payload
        finally:
            with self._lock:
                self._live -= 1


def test_fetches_overlap_instead_of_running_one_at_a_time(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """Before this, fetch and parse were fully serialized — connect, RETR,
    parse, insert, one at a time — so a wide import paid
    sum(fetch) + sum(parse+sink)."""
    probe = _ConcurrencyProbe(dbc_fixture("sim_rr_2023_mini").read_bytes())
    scopes = [ScopeKey(uf="RR", ano=y) for y in range(2015, 2024)]
    _list(monkeypatch, scopes, probe.payload)

    with patch("omnisus.sources.datasus_ftp.fetch._blocking_fetch", probe):
        report = sus.import_dataset(
            "sim_obitos", scopes=scopes, target=f"ducklake:{tmp_path}/c.ducklake", concurrency=4
        )

    assert not report.failed, report.failed
    assert probe.total == len(scopes)
    assert probe.peak > 1, "fetches must overlap; serial execution defeats the whole change"


def test_concurrency_is_bounded_because_datasus_is_shared(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """DATASUS FTP is a shared public resource. This is deliberately not
    'as fast as the network allows' — the bound is the point."""
    probe = _ConcurrencyProbe(dbc_fixture("sim_rr_2023_mini").read_bytes())
    scopes = [ScopeKey(uf="RR", ano=y) for y in range(2010, 2024)]
    _list(monkeypatch, scopes, probe.payload)

    with patch("omnisus.sources.datasus_ftp.fetch._blocking_fetch", probe):
        sus.import_dataset(
            "sim_obitos", scopes=scopes, target=f"ducklake:{tmp_path}/b.ducklake", concurrency=3
        )

    assert probe.peak <= 3, f"never more than 3 connections in flight, saw {probe.peak}"


@pytest.mark.parametrize("concurrency", [0, -1])
def test_concurrency_must_be_positive(tmp_path: Path, concurrency: int) -> None:
    with pytest.raises(ValueError, match="concurrency"):
        sus.import_dataset(
            "sim_obitos",
            scopes=[ScopeKey(uf="RR", ano=2023)],
            target=f"ducklake:{tmp_path}/x.ducklake",
            concurrency=concurrency,
        )


def test_scopes_commit_in_batches_not_one_snapshot_each(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """Batching end to end: 6 scopes at batch_size=2 is 3 commits, not 6."""
    from omnisus.lake import Lake

    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    scopes = [ScopeKey(uf="RR", ano=y) for y in range(2018, 2024)]
    target = f"ducklake:{tmp_path}/s.ducklake"
    _list(monkeypatch, scopes, payload)

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        lambda *_a: payload,
    ):
        report = sus.import_dataset("sim_obitos", scopes=scopes, target=target, batch_size=2)

    assert len(report.ok) == 6
    with Lake.local(target) as lake:
        inserts = [s for s in lake.snapshots() if "insert" in str(s["changes"]).lower()]
    assert len(inserts) == 3, f"6 scopes / batch_size 2 = 3 commits, got {len(inserts)}"


def test_the_report_is_ordered_by_the_scopes_the_caller_asked_for(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """Fetches complete out of order; the report must not."""
    payload = dbc_fixture("sim_rr_2023_mini").read_bytes()
    scopes = [ScopeKey(uf="RR", ano=y) for y in range(2018, 2024)]
    _list(monkeypatch, scopes, payload)

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        _ConcurrencyProbe(payload, delay=0.01),
    ):
        report = sus.import_dataset(
            "sim_obitos", scopes=scopes, target=f"ducklake:{tmp_path}/o.ducklake", concurrency=6
        )

    assert [o.scope for o in report.outcomes] == scopes
