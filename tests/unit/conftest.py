"""Unit-test safety net: no test in this tree may touch the network.

``_blocking_list`` is the single choke point every DATASUS-FTP listing path
funnels through (``list_dir`` -> ``list_dir_cached`` -> ``list_sources`` /
``available`` / ``crawl``, and every import run). Patching it
here to raise turns a silent, cache-masked network hit into an immediate,
loud test failure instead of a flaky pass-because-the-on-disk-cache-happened-
to-be-warm result.

A test that wants a real (faked) listing already patches ``_blocking_list``
(or ``list_dir_cached``, or ``_runner.list_sources`` via
``tests/support/fake_datasus``) itself — that patch is applied after this fixture's
and wins for the duration of the test, so this is purely a safety net for
whoever forgets.
"""

from __future__ import annotations

import pytest

from tests.support.fake_datasus import block_ftp_listing


@pytest.fixture(autouse=True)
def _block_ftp_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    block_ftp_listing(monkeypatch)
