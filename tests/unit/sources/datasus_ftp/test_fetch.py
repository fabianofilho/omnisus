"""Tests for datasus_ftp.fetch — FTP DBC fetcher."""

from __future__ import annotations

import ftplib
from unittest.mock import patch

import pytest

from omnisus.sources.datasus_ftp.fetch import (
    FtpFileNotFound,
    FtpUnavailable,
    fetch_dbc_bytes,
)
from tests.support import fake_ftp
from tests.support.listings import fixture_entry

SIM_DIR = "/dissemin/publicos/SIM/CID10/DORES"


@pytest.mark.asyncio
async def test_fetch_dbc_bytes_returns_payload() -> None:
    payload = b"\x00\x01FAKE_DBC_BYTES"

    def fake_blocking_fetch(remote_dir: str, filename: str, timeout: float) -> bytes:
        assert remote_dir == "/dissemin/publicos/SIM/CID10/DORES"
        assert filename == "DOSP2024.dbc"
        return payload

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        side_effect=fake_blocking_fetch,
    ):
        data = await fetch_dbc_bytes(fixture_entry(SIM_DIR, "DOSP2024.dbc", payload))
    assert data == payload


@pytest.mark.asyncio
async def test_fetch_dbc_bytes_retries_on_transient_error() -> None:
    payload = b"OK"
    call_count = 0

    def fake_blocking_fetch(*_args: object) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("connection reset")
        return payload

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        side_effect=fake_blocking_fetch,
    ):
        data = await fetch_dbc_bytes(
            fixture_entry(SIM_DIR, "DOSP2024.dbc", b"OK"),
            max_retries=3,
            backoff_seconds=0,
        )
    assert data == payload
    assert call_count == 2


@pytest.mark.asyncio
async def test_a_550_is_terminal_and_typed() -> None:
    """A 550 on a listed file is never retried, and it arrives as
    FtpFileNotFound so the caller can tell it apart without string-matching."""
    call_count = 0

    def fake_blocking_fetch(*_args: object) -> bytes:
        nonlocal call_count
        call_count += 1
        raise ftplib.error_perm("550 No such file")

    with (
        patch(
            "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
            side_effect=fake_blocking_fetch,
        ),
        pytest.raises(FtpFileNotFound),
    ):
        await fetch_dbc_bytes(
            fixture_entry(SIM_DIR, "DOSP2024.dbc", b"OK"),
            max_retries=3,
            backoff_seconds=0,
        )
    assert call_count == 1


@pytest.mark.asyncio
async def test_a_530_throttle_is_retried_not_mistaken_for_a_missing_file() -> None:
    """The defect this contract replaces.

    ``ftplib.error_perm`` is *any* 5xx, and DATASUS answers 530 when its
    anonymous-connection pool is full. Treating the whole class as permanent
    made a busy server indistinguishable from an absent dataset — so a wide
    import would report scopes as missing that exist and were merely throttled.
    """
    call_count = 0

    def fake_blocking_fetch(*_args: object) -> bytes:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ftplib.error_perm("530 maximum number of allowed clients")
        return b"OK"

    with patch(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
        side_effect=fake_blocking_fetch,
    ):
        data = await fetch_dbc_bytes(
            fixture_entry(SIM_DIR, "DOSP2024.dbc", b"OK"),
            max_retries=3,
            backoff_seconds=0,
        )
    assert data == b"OK"
    assert call_count == 3, "530 must be retried to the full budget, not treated as terminal"


@pytest.mark.asyncio
async def test_a_530_that_never_clears_is_unavailable_not_not_found() -> None:
    """Exhausting the budget on a throttle is 'failed', never 'skipped'."""

    def fake_blocking_fetch(*_args: object) -> bytes:
        raise ftplib.error_perm("530 maximum number of allowed clients")

    with (
        patch(
            "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
            side_effect=fake_blocking_fetch,
        ),
        pytest.raises(FtpUnavailable) as exc_info,
    ):
        await fetch_dbc_bytes(
            fixture_entry(SIM_DIR, "DOSP2024.dbc", b"OK"),
            max_retries=2,
            backoff_seconds=0,
        )
    assert not isinstance(exc_info.value, FtpFileNotFound)


@pytest.mark.asyncio
async def test_exhausted_retries_raise_unavailable_preserving_the_cause() -> None:
    def fake_blocking_fetch(*_args: object) -> bytes:
        raise OSError("perma-fail")

    with (
        patch(
            "omnisus.sources.datasus_ftp.fetch._blocking_fetch",
            side_effect=fake_blocking_fetch,
        ),
        pytest.raises(FtpUnavailable) as exc_info,
    ):
        await fetch_dbc_bytes(
            fixture_entry(SIM_DIR, "DOSP2024.dbc", b"OK"),
            max_retries=2,
            backoff_seconds=0,
        )
    # The original error is not swallowed — it is the __cause__.
    assert isinstance(exc_info.value.__cause__, OSError)
    assert "perma-fail" in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_a_download_whose_size_differs_from_the_listing_fails(monkeypatch) -> None:
    from omnisus.sources.datasus_ftp.fetch import FtpSizeMismatch, fetch_dbc_bytes
    from tests.support.listings import fixture_entry

    entry = fixture_entry("/dissemin/publicos/SIM/CID10/DORES", "DORR2023.dbc", b"x" * 10)
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp.fetch._blocking_fetch", lambda d, f, t: b"x" * 9
    )
    with pytest.raises(FtpSizeMismatch, match="listing says 10"):
        await fetch_dbc_bytes(entry)


@pytest.mark.asyncio
async def test_fetch_downloads_the_listed_path(monkeypatch) -> None:
    from omnisus.sources.datasus_ftp.fetch import fetch_dbc_bytes
    from tests.support.listings import fixture_entry

    seen = []
    entry = fixture_entry("/dissemin/publicos/SIASUS/200801_/Dados", "BIMG2412_2.dbc", b"abc")

    def fake(remote_dir, filename, timeout):
        seen.append((remote_dir, filename))
        return b"abc"

    monkeypatch.setattr("omnisus.sources.datasus_ftp.fetch._blocking_fetch", fake)
    assert await fetch_dbc_bytes(entry) == b"abc"
    assert seen == [("/dissemin/publicos/SIASUS/200801_/Dados", "BIMG2412_2.dbc")]


def test_the_ftp_host_can_be_overridden(monkeypatch) -> None:
    from omnisus.sources.datasus_ftp._ftp import DEFAULT_FTP_HOST, ftp_host

    monkeypatch.delenv("OMNISUS_FTP_HOST", raising=False)
    assert ftp_host() == DEFAULT_FTP_HOST == "ftp.datasus.gov.br"
    monkeypatch.setenv("OMNISUS_FTP_HOST", "mirror.example.org")
    assert ftp_host() == "mirror.example.org"


# Against `fake_ftp`, which answers as the server did
# (evidence/2026-10-14-ftp-550-conexao-de-dados.md): `_blocking_fetch` runs as it does
# against the server.
DORR2022 = b"\x03" * 275221  # what matters here is the size the listing reports


@pytest.mark.asyncio
async def test_a_550_on_retr_of_a_file_size_still_finds_is_retried(monkeypatch) -> None:
    """SIZE answers on the control connection: 213 means the file is there, so the 550
    on RETR is the data connection dropping, as the server answers from molab."""
    sent = fake_ftp.serve(
        monkeypatch,
        CWD=[fake_ftp.CWD_OK],
        RETR=[fake_ftp.ABORTED, DORR2022],
        SIZE=[len(DORR2022)],
    )

    data = await fetch_dbc_bytes(
        fixture_entry(SIM_DIR, "DORR2022.dbc", DORR2022), backoff_seconds=0
    )

    assert data == DORR2022
    assert sent.count("RETR") == 2


@pytest.mark.asyncio
async def test_a_retr_whose_data_connection_never_holds_is_unavailable(monkeypatch) -> None:
    fake_ftp.serve(
        monkeypatch, CWD=[fake_ftp.CWD_OK], RETR=[fake_ftp.ABORTED], SIZE=[len(DORR2022)]
    )

    with pytest.raises(FtpUnavailable) as raised:
        await fetch_dbc_bytes(fixture_entry(SIM_DIR, "DORR2022.dbc", DORR2022), backoff_seconds=0)
    assert "aborted by the local system" in str(raised.value.__cause__)


@pytest.mark.asyncio
async def test_a_550_on_retr_that_size_confirms_is_file_not_found(monkeypatch) -> None:
    sent = fake_ftp.serve(
        monkeypatch, CWD=[fake_ftp.CWD_OK], RETR=[fake_ftp.NOT_FOUND], SIZE=[fake_ftp.NOT_FOUND]
    )

    with pytest.raises(FtpFileNotFound, match="cannot find the file"):
        await fetch_dbc_bytes(fixture_entry(SIM_DIR, "DORR2022.dbc", DORR2022), backoff_seconds=0)
    assert sent.count("RETR") == 1
