"""DATASUS FTP inventory: list, crawl, and decode what the server actually has.

Three layers over one primitive:

    list_dir(path)      -> Listing          one LIST. The primitive.
    crawl(path, depth=) -> Iterator[FtpEntry]  bounded recursion, open-world.
    available(dataset)  -> list[ScopeKey]   registry-decoded, closed-world.

``available`` and ``crawl`` are the same mechanism at two levels of
interpretation — the only difference is whether filenames get decoded. The
registry names every directory that matters, so the oracle path never
recurses: no queue, no thread pool, no locks.

This module has no dependency on ``Lake``.
"""

from __future__ import annotations

import contextlib
import ftplib
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import structlog

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._ftp import (
    TRANSIENT_FTP_ERRORS,
    ftp_host,
    is_missing,
)
from omnisus.sources.datasus_ftp.datasets import Dataset, Release, resolve
from omnisus.sources.datasus_ftp.filenames import parse_name

logger = structlog.get_logger(__name__)

_DIR_MARKER = "<DIR>"


class FtpPathNotFound(Exception):  # noqa: N818
    """The remote directory does not exist, or access was denied (550).

    Terminal — never retried. Distinct from an existing but empty directory,
    which returns an empty :class:`Listing`.
    """


class FtpUnavailable(Exception):  # noqa: N818
    """The server could not be reached within the retry budget."""


@dataclass(frozen=True)
class FtpEntry:
    """One line of a DATASUS FTP directory listing."""

    name: str
    """File or directory name, spaces preserved."""

    path: str
    """Absolute remote path."""

    parent: str
    """Absolute path of the containing directory."""

    is_dir: bool

    size_bytes: int
    """0 for directories. Exceeds 32 bits in the wild."""

    modified: datetime
    """Server-reported mtime. Detects DATASUS republishing a file we ingested."""


@dataclass(frozen=True)
class Listing:
    """The result of one LIST, including what could not be parsed.

    ``skipped`` is structural, not a log line: the Tier 3 probe asserts it is
    zero for registry directories, and an empty ``entries`` with a missing
    directory is impossible — that raises :class:`FtpPathNotFound`.
    """

    entries: tuple[FtpEntry, ...]
    skipped: int
    path: str

    @property
    def files(self) -> tuple[FtpEntry, ...]:
        return tuple(e for e in self.entries if not e.is_dir)

    @property
    def dirs(self) -> tuple[FtpEntry, ...]:
        return tuple(e for e in self.entries if e.is_dir)


def _parse_msdos_line(line: str, parent: str) -> FtpEntry | None:
    """Parse one MS-DOS-format LIST line, or ``None`` if it is malformed.

    DATASUS answers ``500 Command not understood`` to MLSD, so LIST is the
    only option and its format is MS-DOS, not Unix::

        01-31-20  02:48PM                76107 DOAC1996.dbc
        02-24-18  07:38AM       <DIR>          199407_200712

    Field 2 is the byte size or ``<DIR>``; the name is everything after it,
    rejoined, because DATASUS names contain spaces.

    Note the two-digit year here goes through ``strptime`` (``%y``: 00-68 ->
    2000s), which is deliberately NOT how the filename codec dates a name (the
    century from the row's first covered year). These are different clocks and
    must not be conflated.
    """
    parts = line.split()
    if len(parts) < 4:
        return None
    marker = parts[2]
    is_dir = marker == _DIR_MARKER
    if not is_dir:
        try:
            size = int(marker)
        except ValueError:
            return None
    else:
        size = 0
    try:
        modified = datetime.strptime(f"{parts[0]} {parts[1]}", "%m-%d-%y %I:%M%p")
    except ValueError:
        return None
    name = " ".join(parts[3:])
    if not name:
        return None
    base = parent.rstrip("/")
    return FtpEntry(
        name=name,
        path=f"{base}/{name}",
        parent=parent,
        is_dir=is_dir,
        size_bytes=size,
        modified=modified,
    )


def _blocking_list(path: str, timeout_seconds: float) -> list[str]:
    """One anonymous-FTP LIST of ``path``. The patch seam for tests.

    ``encoding = "latin-1"`` is required: ftplib defaults to UTF-8 and raises
    UnicodeDecodeError on real DATASUS listings.
    """
    lines: list[str] = []
    with contextlib.closing(ftplib.FTP(ftp_host(), timeout=timeout_seconds)) as ftp:
        ftp.encoding = "latin-1"
        ftp.login()  # anonymous
        ftp.voidcmd("TYPE I")
        ftp.cwd(path)
        ftp.dir(lines.append)
    return lines


def list_dir(
    path: str,
    *,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> Listing:
    """List one remote directory. The primitive every other layer builds on.

    Raises:
        FtpPathNotFound: the directory is missing or access was denied (550).
            Terminal — never retried.
        FtpUnavailable: transient failures exhausted ``max_retries``.

    An existing but empty directory returns an empty :class:`Listing`; empty
    and failed are never the same value. Every connection attempt is
    fresh, because a long-lived FTP control connection to DATASUS does not
    survive a transient error.

    ``path`` is normalised exactly once, on entry — trailing slashes stripped
    — so ``Listing.path`` and every ``FtpEntry.parent`` carry the canonical
    form regardless of what the caller passed (a caller-supplied ``/x/`` and
    ``/x`` must never diverge downstream, e.g. in the inventory cache).
    """
    path = path.rstrip("/") or "/"
    last_exc: BaseException | None = None
    for attempt in range(max_retries):
        try:
            raw = _blocking_list(path, timeout_seconds)
        except TRANSIENT_FTP_ERRORS as exc:
            # ftplib.error_perm is itself a member of TRANSIENT_FTP_ERRORS
            # (via ftplib.all_errors), so this single clause also catches it;
            # only a 550 ("path not found") is terminal.
            if is_missing(exc):
                raise FtpPathNotFound(f"{path}: {exc}") from exc
            last_exc = exc
            if attempt + 1 < max_retries:
                time.sleep(backoff_seconds * (2**attempt))
            continue
        entries: list[FtpEntry] = []
        skipped = 0
        for line in raw:
            entry = _parse_msdos_line(line, path)
            if entry is None:
                skipped += 1
            else:
                entries.append(entry)
        if skipped:
            logger.warning("inventory.skipped_lines", path=path, skipped=skipped)
        logger.info("inventory.listed", path=path, entries=len(entries), skipped=skipped)
        return Listing(entries=tuple(entries), skipped=skipped, path=path)
    raise FtpUnavailable(f"{path}: {max_retries} attempts failed") from last_exc


def list_dir_cached(
    path: str,
    *,
    refresh: bool = False,
    ttl_hours: float = 24.0,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> Listing:
    """:func:`list_dir` with the Parquet cache in front of it.

    The cache is never authoritative: a miss, a stale entry or an
    unreadable file all fall through to the network.
    """
    # Imported inside the function, not at module scope: _cache imports this
    # module (inventory) at module scope, so a top-level import here would be
    # a cycle and fail at import time.
    from omnisus.sources.datasus_ftp import _cache

    if not refresh:
        cached = _cache.read_cached(path, ttl_hours=ttl_hours)
        if cached is not None:
            logger.debug("inventory.cache_hit", path=path, entries=len(cached.entries))
            return cached
    listing = list_dir(
        path,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )
    try:
        _cache.write_cache(listing)
    except Exception as exc:  # A cache we cannot write is still not authoritative
        logger.warning("inventory.cache_write_failed", path=path, error=str(exc))
    return listing


def crawl(path: str, *, depth: int = 1, refresh: bool = False) -> Iterator[FtpEntry]:
    """Walk a remote subtree, yielding entries as they are found.

    Open-world: any path, no decoding, so it reaches families this package
    does not model (other SINAN agravos, CIHA, PCE). ``depth=1`` lists ``path`` only.
    Recursion is bounded by ``depth`` and the walk is sequential — no queue,
    no pool.

    A subdirectory that cannot be listed is logged and skipped; the entry for
    the directory itself is still yielded, so a denied subtree never silently
    truncates the walk.
    """
    if depth < 1:
        raise ValueError(f"depth must be >= 1; got {depth}")
    frontier: list[tuple[str, int]] = [(path, depth)]
    while frontier:
        current, remaining = frontier.pop(0)
        try:
            listing = list_dir_cached(current, refresh=refresh)
        except (FtpPathNotFound, FtpUnavailable) as exc:
            if current == path:
                raise
            logger.warning("inventory.crawl_skipped", path=current, error=str(exc))
            continue
        for entry in listing.entries:
            yield entry
            if entry.is_dir and remaining > 1:
                frontier.append((entry.path, remaining - 1))


@dataclass(frozen=True)
class ResolvedSource:
    """Where one scope's bytes are: its release and the listed file(s)."""

    release: Release
    files: tuple[FtpEntry, ...]
    """The parts in part order when the month is split, else the one whole file."""


def _part_order(part: str) -> tuple[int, int | str]:
    return (0, int(part)) if part.isdigit() else (1, part)


def sources_for(d: Dataset, listings: Mapping[Release, Listing]) -> dict[ScopeKey, ResolvedSource]:
    """Group the files of ``listings`` by scope for row ``d``.

    Pure. When a month has parts, the parts are its source and a whole file of
    the same month is superseded (DATASUS re-published split months later, with
    more records). A scope found in two release directories raises: it is a
    server inconsistency, never resolved by preference.
    """
    found: dict[ScopeKey, dict[Release, list[tuple[str | None, FtpEntry]]]] = {}
    for release, listing in listings.items():
        for entry in listing.files:
            parsed = parse_name(d, entry.name)
            if parsed is not None:
                found.setdefault(parsed.scope, {}).setdefault(release, []).append(
                    (parsed.part, entry)
                )
    resolved: dict[ScopeKey, ResolvedSource] = {}
    for scope, by_release in found.items():
        if len(by_release) > 1:
            raise ValueError(f"{d.name}: {scope} is published as both final and prelim")
        ((release, named),) = by_release.items()
        parts = sorted(
            ((part, entry) for part, entry in named if part is not None),
            key=lambda item: _part_order(item[0]),
        )
        wholes = [entry for part, entry in named if part is None]
        if parts:
            if wholes:
                logger.debug(
                    "inventory.superseded",
                    dataset=d.name,
                    scope=str(scope),
                    whole=[e.name for e in wholes],
                )
            files = tuple(entry for _, entry in parts)
        elif len(wholes) == 1:
            files = (wholes[0],)
        else:
            raise ValueError(f"{d.name}: {scope} is listed as {[e.name for e in wholes]}")
        resolved[scope] = ResolvedSource(release=release, files=files)
    return dict(sorted(resolved.items(), key=lambda item: _scope_order(item[0])))


def list_sources(d: Dataset, *, refresh: bool = False) -> dict[ScopeKey, ResolvedSource]:
    """:func:`sources_for` over one listing of each of ``d``'s directories."""
    listings = {
        release: list_dir_cached(path, refresh=refresh)
        for release, path in d.directories().items()
    }
    return sources_for(d, listings)


def _scope_order(scope: ScopeKey) -> tuple[int, str, int]:
    return (scope.ano, scope.uf or "", scope.mes or 0)


def available_releases(
    dataset: str | Dataset,
    *,
    years: Iterable[int] | None = None,
    ufs: Sequence[str] | None = None,
    months: Iterable[int] | None = None,
    refresh: bool = False,
) -> dict[ScopeKey, Release]:
    """The scopes DATASUS publishes now, and whether each is final or preliminary.

    One cached listing per directory. A scope found in two directories is a server
    inconsistency and raises; it is never resolved by preference.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a :class:`Dataset`.
        years: Keep these years, e.g. ``[2023, 2024]``; ``None`` (default) keeps all.
        ufs: Keep these UFs, e.g. ``["RR"]``; ``None`` keeps all. National datasets
            accept only ``None``.
        months: Keep these months 1-12; ``None`` keeps all. National datasets accept
            only ``None``.
        refresh: ``True`` ignores the local listing cache and asks the server again.

    Returns:
        ``{scope: "final" | "prelim"}``, ordered by year, UF and month.

    Raises:
        ValueError: ``dataset`` is unknown, a national dataset got ``ufs``/``months``,
            or a scope is listed in two directories.
        FtpUnavailable: the server did not answer after retries.

    Examples:
        >>> import omnisus as sus
        >>> sus.available_releases("sim_obitos", years=[2024], ufs=["RR"])  # doctest: +SKIP
        {ScopeKey(uf='RR', ano=2024, mes=None): 'prelim'}
    """
    d = resolve(dataset)
    if d.geography == "national" and (ufs is not None or months is not None):
        raise ValueError(f"{d.name} is national: it has no UF or month to filter by")
    wanted = set(years) if years is not None else None
    wanted_ufs = {u.upper() for u in ufs} if ufs is not None else None
    wanted_months = set(months) if months is not None else None
    found = {
        scope: source.release
        for scope, source in list_sources(d, refresh=refresh).items()
        if (wanted is None or scope.ano in wanted)
        and (wanted_ufs is None or scope.uf in wanted_ufs)
        and (wanted_months is None or scope.mes in wanted_months)
    }
    logger.info("inventory.available", dataset=d.name, scopes=len(found))
    return found


def available(
    dataset: str | Dataset,
    *,
    years: Iterable[int] | None = None,
    ufs: Sequence[str] | None = None,
    months: Iterable[int] | None = None,
    refresh: bool = False,
) -> list[ScopeKey]:
    """The scopes DATASUS publishes now: what an import can actually get.

    Pass the result to :func:`~omnisus.import_dataset`; unlike
    :func:`~omnisus.scopes_for`, it plans only files the server lists. Files of
    other datasets sharing a directory are skipped.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a :class:`Dataset`.
        years: Keep these years, e.g. ``[2023, 2024]``; ``None`` (default) keeps all.
        ufs: Keep these UFs, e.g. ``["RR"]``; ``None`` keeps all. National datasets
            accept only ``None``.
        months: Keep these months 1-12; ``None`` keeps all. National datasets accept
            only ``None``.
        refresh: ``True`` ignores the local listing cache and asks the server again.

    Returns:
        The scopes, ordered by year, UF and month.

    Raises:
        ValueError: as :func:`available_releases`.
        FtpUnavailable: the server did not answer after retries.

    Examples:
        >>> import omnisus as sus
        >>> sus.available("sim_obitos", years=[2023], ufs=["RR"])  # doctest: +SKIP
        [ScopeKey(uf='RR', ano=2023, mes=None)]
    """
    return list(available_releases(dataset, years=years, ufs=ufs, months=months, refresh=refresh))
