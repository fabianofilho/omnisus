"""One fake DATASUS server for runner-level tests: listing and downloads from given bytes.

``block_ftp_listing`` is the other side: no listing reaches the real server.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import pytest

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import Dataset, Release, resolve
from omnisus.sources.datasus_ftp.inventory import FtpEntry, ResolvedSource
from tests.support.datasus_names import filename_for
from tests.support.listings import fixture_entry


def serve(
    monkeypatch: pytest.MonkeyPatch,
    dataset: str | Dataset,
    payloads: Mapping[ScopeKey, bytes | Sequence[bytes]],
    *,
    release: Release = "final",
    modified: datetime | None = None,
) -> list[str]:
    """Serve ``payloads`` as the only files the server lists for ``dataset``.

    A scope missing from ``payloads`` is not listed. ``modified`` is every file's
    server time (default: :func:`fixture_entry`'s). Returns the fetched paths.
    """
    d = resolve(dataset)
    directory = d.directories()[release]
    content: dict[str, bytes] = {}
    sources: dict[ScopeKey, ResolvedSource] = {}
    for scope, value in payloads.items():
        parts = [value] if isinstance(value, (bytes, bytearray)) else list(value)
        entries = []
        for number, raw in enumerate(parts, start=1):
            name = filename_for(d, scope, None if len(parts) == 1 else str(number))
            entry = fixture_entry(directory, name, raw, modified)
            content[entry.path] = raw
            entries.append(entry)
        sources[scope] = ResolvedSource(release=release, files=tuple(entries))
    fetched: list[str] = []

    async def fetch(entry: FtpEntry, **_kw: object) -> bytes:
        fetched.append(entry.path)
        return content[entry.path]

    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp._runner.list_sources", lambda d, **_kw: sources
    )
    monkeypatch.setattr("omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", fetch)
    return fetched


def block_ftp_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every DATASUS-FTP listing fail loudly instead of reaching the server.

    ``tests/unit/conftest.py`` applies it to every unit test. A module-scoped fixture
    is set up before that function-scoped guard, so one that imports applies it itself.
    """

    def _refuse(path: str, timeout_seconds: float) -> list[str]:
        raise AssertionError(f"network: unit test attempted to LIST {path!r} over FTP")

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", _refuse)
