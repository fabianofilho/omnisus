"""Primitives shared by every DATASUS-FTP transport in this package.

These lived in duplicate in ``fetch.py`` and ``inventory.py``, and the
duplication had already cost a bug: when the error contract was narrowed so
that only a 550 counts as terminal, the fix was applied to one copy and not
the other. One home, so a fix reaches both.
"""

from __future__ import annotations

import ftplib
import os

DEFAULT_FTP_HOST = "ftp.datasus.gov.br"


def ftp_host() -> str:
    """The DATASUS FTP host; ``OMNISUS_FTP_HOST`` overrides it (e.g. a mirror)."""
    return os.environ.get("OMNISUS_FTP_HOST") or DEFAULT_FTP_HOST


TRANSIENT_FTP_ERRORS: tuple[type[BaseException], ...] = (
    *ftplib.all_errors,
    OSError,
    TimeoutError,
)
"""Named so mypy can verify an ``except`` clause; it cannot check through a
starred tuple literal written inline."""


def is_missing(exc: BaseException) -> bool:
    """True iff ``exc`` says the remote path does not exist.

    ``ftplib.error_perm`` is *any* 5xx, so it is not on its own a "not found":
    ``530 maximum number of allowed clients`` is DATASUS's ordinary
    anonymous-connection throttle and is entirely transient, and ``500 Command
    not understood`` is what the server answers to MLSD. Only ``550`` is
    terminal. Treating the whole class as permanent turns a
    throttled connection into a false "this dataset does not exist".
    """
    return isinstance(exc, ftplib.error_perm) and str(exc).startswith("550")


class DataConnectionLost(ftplib.Error):
    """A 550 on LIST or RETR for a path the control connection says exists. Transient.

    DATASUS answers ``550 The network connection was aborted by the local system.``
    when the passive data connection drops, the same code as ``550 The system cannot
    find the file specified.`` (evidence/2026-10-14-ftp-550-conexao-de-dados.md). The
    control connection tells them apart: CWD answered 250 before the LIST, and SIZE
    answers 213 for a file that is there. Being an ``ftplib.Error`` and not an
    ``error_perm``, it is retried and :func:`is_missing` is false for it.
    """
