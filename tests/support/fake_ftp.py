"""An `ftplib.FTP` that answers with replies the DATASUS server gave.

The replies are in `evidence/2026-10-14-ftp-550-conexao-de-dados.md`. Unlike
`fake_datasus`, which replaces the listing and the download functions, this stands in
for the FTP connection itself, so `_blocking_list` and `_blocking_fetch` run as they do
against the server.
"""

from __future__ import annotations

import ftplib
from collections.abc import Callable

import pytest

NOT_FOUND = ftplib.error_perm("550 The system cannot find the file specified. ")
ABORTED = ftplib.error_perm("550 The network connection was aborted by the local system. ")
CWD_OK = "250 CWD command successful."


def serve(monkeypatch: pytest.MonkeyPatch, **replies: list[object]) -> list[str]:
    """Answer each command (`CWD`, `LIST`, `RETR`, `SIZE`) with its replies in turn.

    A reply is an exception to raise or the value to return (`LIST`: the lines; `RETR`:
    the bytes; `SIZE`: the size); the last one repeats. Returns the commands sent.
    """
    sent: list[str] = []

    class ScriptedFTP:
        encoding = "utf-8"
        sock = None

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            sent.append("connect")

        def connect(self, *_args: object) -> None: ...

        def login(self) -> None: ...

        def voidcmd(self, _command: str) -> None: ...

        def close(self) -> None: ...

        def _answer(self, command: str) -> object:
            sent.append(command)
            queue = replies[command]
            reply = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(reply, BaseException):
                raise reply
            return reply

        def cwd(self, _path: str) -> object:
            return self._answer("CWD")

        def dir(self, callback: Callable[[str], object]) -> None:
            for line in self._answer("LIST"):  # type: ignore[attr-defined]
                callback(line)

        def retrbinary(self, _command: str, callback: Callable[[bytes], object]) -> None:
            callback(self._answer("RETR"))  # type: ignore[arg-type]

        def size(self, _filename: str) -> object:
            return self._answer("SIZE")

    monkeypatch.setattr(ftplib, "FTP", ScriptedFTP)
    return sent
