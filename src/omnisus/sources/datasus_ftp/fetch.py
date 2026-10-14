"""Async DBC fetcher for DATASUS via anonymous FTP."""

from __future__ import annotations

import asyncio
import contextlib
import ftplib
import io
import socket
import threading
from contextvars import ContextVar

import structlog

from omnisus.sources.datasus_ftp._ftp import (
    TRANSIENT_FTP_ERRORS,
    DataConnectionLost,
    ftp_host,
    is_missing,
)
from omnisus.sources.datasus_ftp.inventory import FtpEntry

logger = structlog.get_logger(__name__)

DEFAULT_MAX_PAYLOAD_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_INFLIGHT_BYTES = 1024 * 1024 * 1024
_DOWNLOAD_LIMIT: ContextVar[int] = ContextVar("download_limit", default=DEFAULT_MAX_PAYLOAD_BYTES)


@contextlib.contextmanager
def download_limit(max_bytes: int):
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_payload_bytes must be a positive integer")
    token = _DOWNLOAD_LIMIT.set(max_bytes)
    try:
        yield
    finally:
        _DOWNLOAD_LIMIT.reset(token)


class _DownloadControl:
    """Own control/data sockets so cancellation can stop a blocking transfer."""

    def __init__(self):
        self.cancelled = threading.Event()
        self.ftp = None
        self.sockets = []
        self.guard = threading.Lock()

    def check(self):
        if self.cancelled.is_set():
            raise InterruptedError("download cancelled")

    def track(self, connection):
        if connection is not None:
            with self.guard:
                self.sockets.append(connection)
            if self.cancelled.is_set():
                self.cancel()
                self.check()

    def cancel(self):
        self.cancelled.set()
        with self.guard:
            connections = list(self.sockets)
        # FTP.connect assigns sock before reading the server greeting, so it
        # may already exist even though connect has not returned to track it.
        if self.ftp is not None:
            connection = getattr(self.ftp, "sock", None)
            if connection is not None:
                connections.append(connection)
        for connection in connections:
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                connection.close()

    def close_ftp(self):
        # BufferedReader.close can wait for a worker holding its read lock.
        # Only call this off the event loop, after shutting down known sockets.
        if self.ftp is not None:
            with contextlib.suppress(OSError):
                self.ftp.close()


_ACTIVE_DOWNLOAD: ContextVar[_DownloadControl | None] = ContextVar("active_download", default=None)


async def _download(remote_dir: str, filename: str, timeout_seconds: float) -> bytes:
    control = _DownloadControl()
    token = _ACTIVE_DOWNLOAD.set(control)
    try:
        worker = asyncio.create_task(
            asyncio.to_thread(_blocking_fetch, remote_dir, filename, timeout_seconds)
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            control.cancel()
            closing = asyncio.create_task(asyncio.to_thread(control.close_ftp))
            finished = asyncio.gather(worker, closing, return_exceptions=True)
            # A reservation cannot be released while its worker still owns
            # bytes. Connect/DNS stages that cannot be interrupted must finish
            # (or time out); repeated task cancellation does not orphan them.
            while not finished.done():
                try:
                    await asyncio.shield(finished)
                except asyncio.CancelledError:
                    continue
            # Do not keep a completed worker's payload in a cancellation
            # traceback after the caller releases its byte reservation.
            del worker, closing, finished
            raise
    finally:
        _ACTIVE_DOWNLOAD.reset(token)


class FtpFileNotFound(Exception):  # noqa: N818
    """A file the caller asked for is not on the server. Terminal — never retried.

    Raised for a 550 on RETR that SIZE confirms, and by ``import_scope`` for a scope
    the server listing does not have; the message says which. Files are fetched only after
    the listing named them, so a 550 means the file vanished between LIST and
    RETR: the scope is ``failed`` and worth retrying after a fresh listing,
    never ``skipped``. Distinct from
    :class:`FtpUnavailable`, which is a transient failure that exhausted its
    retries.
    """


class FtpUnavailable(Exception):  # noqa: N818
    """The file could not be fetched within the retry budget."""


class FtpSizeMismatch(Exception):  # noqa: N818
    """The downloaded file is not the size the listing reported. Terminal.

    The file changed on the server after it was listed; list again and retry.
    """


def _still_there(ftp: ftplib.FTP, filename: str) -> bool:
    """Whether SIZE, on the control connection alone, finds ``filename``."""
    try:
        ftp.size(filename)
    except ftplib.error_perm as exc:
        if is_missing(exc):
            return False
        raise
    return True


def _blocking_fetch(remote_dir: str, filename: str, timeout_seconds: float) -> bytes:
    """Synchronous FTP fetch returning bytes. Run via asyncio.to_thread."""
    control = _ACTIVE_DOWNLOAD.get() or _DownloadControl()
    max_bytes = _DOWNLOAD_LIMIT.get()

    class TrackedFTP(ftplib.FTP):
        def ntransfercmd(self, *args, **kwargs):
            connection, size = super().ntransfercmd(*args, **kwargs)
            control.track(connection)
            return connection, size

    # Closing BytesIO also releases storage referenced by an exception
    # traceback, so retries and queued errors cannot retain previous payloads.
    with io.BytesIO() as buf:

        def write(chunk: bytes) -> None:
            control.check()
            if buf.tell() + len(chunk) > max_bytes:
                raise ValueError(f"download exceeds payload limit of {max_bytes} bytes")
            buf.write(chunk)

        with contextlib.closing(TrackedFTP(timeout=timeout_seconds)) as ftp:
            control.ftp = ftp
            control.check()
            ftp.connect(ftp_host())
            control.track(getattr(ftp, "sock", None))
            control.check()
            ftp.login()
            ftp.cwd(remote_dir)
            try:
                ftp.retrbinary(f"RETR {filename}", write)
            except ftplib.error_perm as exc:
                if is_missing(exc) and _still_there(ftp, filename):
                    raise DataConnectionLost(str(exc)) from exc
                raise
            control.check()
        return buf.getvalue()


async def fetch_dbc_bytes(
    entry: FtpEntry,
    *,
    timeout_seconds: float = 120.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    max_bytes: int | None = None,
) -> bytes:
    """Download one listed file, with exponential retry.

    Raises:
        FtpFileNotFound: the server answered 550 for a file it had listed, and SIZE
            confirmed it is gone. Terminal.
        FtpUnavailable: transient failures exhausted ``max_retries``.
        FtpSizeMismatch: the bytes are not the listed size. Terminal.

    Only a 550 is terminal among FTP errors: DATASUS answers ``530 maximum
    number of allowed clients`` when its anonymous pool is full, a throttle.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            with download_limit(_DOWNLOAD_LIMIT.get() if max_bytes is None else max_bytes):
                data = await _download(entry.parent, entry.name, timeout_seconds)
                if len(data) > _DOWNLOAD_LIMIT.get():
                    del data
                    raise ValueError("download exceeds payload bytes limit")
        except TRANSIENT_FTP_ERRORS as exc:
            if is_missing(exc):
                raise FtpFileNotFound(f"{entry.path}: {exc}") from exc
            last_exc = exc
            if attempt + 1 < max_retries:
                await asyncio.sleep(backoff_seconds * (2**attempt))
            continue
        if len(data) != entry.size_bytes:
            raise FtpSizeMismatch(
                f"{entry.path}: downloaded {len(data)} bytes, listing says {entry.size_bytes}"
            )
        logger.info("datasus_ftp.fetched", path=entry.path, bytes=len(data), attempt=attempt)
        return data
    raise FtpUnavailable(f"{entry.path}: {max_retries} attempts failed") from last_exc
