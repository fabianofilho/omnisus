"""list_dir error contract.

Empty and failed are never the same value; retries are bounded.
Patched at _blocking_list — the same seam fetch.py uses. No network.
"""

from __future__ import annotations

import ftplib
from unittest.mock import patch

import pytest

from omnisus.sources.datasus_ftp import inventory
from omnisus.sources.datasus_ftp.inventory import (
    FtpPathNotFound,
    FtpUnavailable,
    list_dir,
)
from tests.support import fake_ftp

PATH = "/dissemin/publicos/SIM/CID10/DORES"
LINE = "01-31-20  02:48PM                76107 DOAC1996.dbc"


def test_returns_parsed_entries() -> None:
    with patch("omnisus.sources.datasus_ftp.inventory._blocking_list", return_value=[LINE]):
        listing = list_dir(PATH)
    assert listing.path == PATH
    assert len(listing.entries) == 1
    assert listing.entries[0].name == "DOAC1996.dbc"
    assert listing.skipped == 0


def test_existing_but_empty_directory_returns_empty_listing_not_an_error() -> None:
    """An empty directory is a legitimate answer."""
    with patch("omnisus.sources.datasus_ftp.inventory._blocking_list", return_value=[]):
        listing = list_dir(PATH)
    assert listing.entries == ()
    assert listing.skipped == 0


def test_malformed_lines_are_counted_not_dropped_silently() -> None:
    with patch(
        "omnisus.sources.datasus_ftp.inventory._blocking_list",
        return_value=[LINE, "garbage", "also garbage"],
    ):
        listing = list_dir(PATH)
    assert len(listing.entries) == 1
    assert listing.skipped == 2


def test_550_raises_path_not_found_and_is_never_retried() -> None:
    calls = 0

    def boom(*_a: object, **_k: object) -> list[str]:
        nonlocal calls
        calls += 1
        raise ftplib.error_perm("550 The system cannot find the file specified.")

    with (
        patch("omnisus.sources.datasus_ftp.inventory._blocking_list", side_effect=boom),
        pytest.raises(FtpPathNotFound, match="/dissemin"),
    ):
        list_dir(PATH)
    assert calls == 1, "550 is terminal — it must not be retried"


def test_530_is_retried_to_the_full_budget_and_raises_unavailable() -> None:
    """Only 550 means "path not found". 530 (login incorrect) is a
    5xx from ftplib.error_perm too, but it is not the path being missing — it
    must get the same bounded retry as any other transient failure."""
    calls = 0

    def boom(*_a: object, **_k: object) -> list[str]:
        nonlocal calls
        calls += 1
        raise ftplib.error_perm("530 Login incorrect.")

    with (
        patch("omnisus.sources.datasus_ftp.inventory._blocking_list", side_effect=boom),
        pytest.raises(FtpUnavailable),
    ):
        list_dir(PATH, max_retries=3, backoff_seconds=0)
    assert calls == 3, "530 is not a missing path — it must get the full retry budget"


def test_transient_error_retries_then_raises_unavailable_within_budget() -> None:
    calls = 0

    def flaky(*_a: object, **_k: object) -> list[str]:
        nonlocal calls
        calls += 1
        raise TimeoutError("dropped")

    with (
        patch("omnisus.sources.datasus_ftp.inventory._blocking_list", side_effect=flaky),
        pytest.raises(FtpUnavailable),
    ):
        list_dir(PATH, max_retries=3, backoff_seconds=0)
    assert calls == 3, "retries must be bounded by max_retries"


def test_transient_error_then_success_returns_the_listing() -> None:
    calls = 0

    def flaky_once(*_a: object, **_k: object) -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("dropped")
        return [LINE]

    with patch("omnisus.sources.datasus_ftp.inventory._blocking_list", side_effect=flaky_once):
        listing = list_dir(PATH, backoff_seconds=0)
    assert len(listing.entries) == 1
    assert calls == 2


def test_trailing_slash_is_normalised_once_on_entry() -> None:
    """Controller amendment: path.rstrip("/") happens once, before the retry loop.

    A caller passing a trailing slash must get back a Listing.path and entry
    .parent values without it, so /x/ and /x cache to the same canonical form
    (the inventory cache depends on this). Entries themselves must be unaffected.
    """
    with patch("omnisus.sources.datasus_ftp.inventory._blocking_list", return_value=[LINE]):
        listing = list_dir(PATH + "/")
    assert listing.path == PATH
    assert len(listing.entries) == 1
    assert listing.entries[0].parent == PATH
    assert listing.entries[0].name == "DOAC1996.dbc"


# The real `_blocking_list`, taken before `tests/unit/conftest.py` replaces it: these
# tests run it against `fake_ftp`, which answers as the server did
# (evidence/2026-10-14-ftp-550-conexao-de-dados.md).
_LIST_ON_THE_CONNECTION = inventory._blocking_list


def test_a_550_on_list_after_cwd_succeeded_is_the_data_connection_and_is_retried(
    monkeypatch,
) -> None:
    """CWD answered 250, so the directory exists; the 550 is the data connection
    dropping, as the server answers from molab."""
    monkeypatch.setattr(inventory, "_blocking_list", _LIST_ON_THE_CONNECTION)
    sent = fake_ftp.serve(monkeypatch, CWD=[fake_ftp.CWD_OK], LIST=[fake_ftp.ABORTED, [LINE]])

    listing = list_dir(PATH, backoff_seconds=0)

    assert [e.name for e in listing.entries] == ["DOAC1996.dbc"]
    assert sent.count("LIST") == 2


def test_a_list_whose_data_connection_never_holds_is_unavailable_not_not_found(
    monkeypatch,
) -> None:
    monkeypatch.setattr(inventory, "_blocking_list", _LIST_ON_THE_CONNECTION)
    fake_ftp.serve(monkeypatch, CWD=[fake_ftp.CWD_OK], LIST=[fake_ftp.ABORTED])

    with pytest.raises(FtpUnavailable) as raised:
        list_dir(PATH, backoff_seconds=0)
    assert "aborted by the local system" in str(raised.value.__cause__)


def test_a_550_on_cwd_is_still_path_not_found(monkeypatch) -> None:
    monkeypatch.setattr(inventory, "_blocking_list", _LIST_ON_THE_CONNECTION)
    sent = fake_ftp.serve(monkeypatch, CWD=[fake_ftp.NOT_FOUND], LIST=[[LINE]])

    with pytest.raises(FtpPathNotFound, match="cannot find the file"):
        list_dir(PATH, backoff_seconds=0)
    assert sent == ["connect", "CWD"]
