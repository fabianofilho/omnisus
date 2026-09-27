"""Generic DATASUS-FTP pipeline.

Every DATASUS FTP dataset imports through this runner.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import structlog

from omnisus.lake import Lake
from omnisus.lake._transactions import TransactionStateError
from omnisus.lake.publication import (
    ImportPolicy,
    SourceFile,
    aggregate_sha256,
    unchanged_since_listing,
    validate_policy,
)
from omnisus.sources._base import (
    ImportAbortedError,
    ImportReport,
    ImportResult,
    ScopeKey,
    ScopeOutcome,
)
from omnisus.sources.datasus_ftp._ftp import ftp_host
from omnisus.sources.datasus_ftp.datasets import Dataset, in_coverage, release_of, resolve
from omnisus.sources.datasus_ftp.fetch import (
    DEFAULT_MAX_INFLIGHT_BYTES,
    DEFAULT_MAX_PAYLOAD_BYTES,
    FtpFileNotFound,
    download_limit,
    fetch_dbc_bytes,
)
from omnisus.sources.datasus_ftp.identity import validate_identity
from omnisus.sources.datasus_ftp.inventory import FtpEntry, ResolvedSource, list_sources
from omnisus.transforms.dictionaries import load_dicionario

logger = structlog.get_logger(__name__)

_Fetched = tuple[int, ScopeKey, list[tuple[FtpEntry, bytes]] | None, BaseException | None]
"""One fetched scope on its way to the consumer: exactly one of the payloads
and the error is set."""

DEFAULT_CONCURRENCY = 6
"""Fetches in flight. DATASUS FTP is a shared public resource: this is
deliberately not "as fast as the network allows". Whether the server enforces
a per-IP connection limit is not known, so 6 stays below what comparable tools
run without reported trouble."""

DEFAULT_BATCH_SIZE = 24
"""Scopes per DuckLake transaction. One snapshot per scope meant 648 snapshots
and 648 small files for a wide SIH import. Batching trades atomicity
granularity for commit count: a write failure mid-batch loses that batch's
uncommitted scopes, never the run, and they are reported failed and safe to
retry. A scope rejected before it writes (decoding, integrity, identity) fails
alone. ``batch_size=1`` restores per-scope atomicity."""


class _ProducerStoppedError(RuntimeError):
    """The producer exited without completing the input stream."""


async def _next_fetched(
    queue: asyncio.Queue[_Fetched | None],
    producer: asyncio.Task[None],
) -> _Fetched | None:
    """Wait for either the next item or abnormal producer termination."""
    waiting = asyncio.create_task(queue.get())
    try:
        done, _ = await asyncio.wait({waiting, producer}, return_when=asyncio.FIRST_COMPLETED)
        if waiting in done:
            return waiting.result()
        if producer.cancelled():
            raise _ProducerStoppedError("producer cancelled")
        error = producer.exception()
        if error is not None:
            raise _ProducerStoppedError("producer failed") from error
        return await waiting
    finally:
        if not waiting.done():
            waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


async def import_scope(
    *,
    dataset: str | Dataset,
    scope: ScopeKey,
    lake: Lake,
) -> ImportResult:
    """Fetch + parse + sink one (dataset, scope) into the lake.

    ``dataset`` is a registry key or a ``Dataset`` value. The value form is
    the open door: an uncurated dataset with its own
    ``dictionary`` flows through exactly this path.
    """
    d = resolve(dataset)
    _require_well_formed(d, [scope])
    if d.monthly and scope.mes is None:
        raise ValueError(f"{d.name} is monthly; ScopeKey.mes is required")

    logger.info("import_scope.start", dataset=d.name, scope=str(scope))
    source = (await asyncio.to_thread(list_sources, d, refresh=True)).get(scope)
    if source is None:
        raise FtpFileNotFound(f"{d.name} {scope}: not in the server listing")
    raws = [await fetch_dbc_bytes(entry) for entry in source.files]
    result = ingest_raw(d, scope, list(zip(source.files, raws, strict=True)), lake)
    assert result is not None, "append always publishes"
    logger.info(
        "import_scope.done",
        dataset=d.name,
        scope=str(scope),
        rows=result.rows,
        snapshot_id=result.snapshot_id,
    )
    return result


@dataclass(frozen=True)
class StagedScope:
    """One scope validated to a local Parquet, not yet written to the lake."""

    path: Path
    sources: list[SourceFile]
    parser_version: str


def parser_version(d: Dataset) -> str:
    """The publication parser version for ``d``, known before any download.

    It hashes only what the import reads from the dictionary: the ``encoding`` that
    decodes text and the ``x-identity`` that accepts or rejects a file. Labels, code
    maps and claims are read when rows are queried, so editing them leaves published
    scopes unchanged.
    """
    from omnisus.sources.datasus_ftp.dbf_contract import publication_parser_version

    dic = load_dicionario(d.dictionary if d.dictionary is not None else d.name)
    read = {"encoding": dic.encoding, "x-identity": dic.raw.get("x-identity")}
    canonical = json.dumps(read, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return publication_parser_version(hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _listed(entry: FtpEntry) -> tuple[str, int, str]:
    """What a publication records of a listed file besides its digest: URI, bytes, server time."""
    return (
        f"ftp://{ftp_host()}{entry.path}",
        entry.size_bytes,
        entry.modified.strftime("%Y-%m-%dT%H:%M"),
    )


def stage_raw(
    d: Dataset, scope: ScopeKey, payloads: Sequence[tuple[FtpEntry, bytes]], directory: Path
) -> StagedScope:
    """Decode and validate one scope's file(s) into ``directory``, without touching the lake.

    ``payloads`` are the listed entries and their bytes, in part order. The
    release is read from the entries' directory, never passed in.
    """
    from omnisus.sources.datasus_ftp.staging import dbc_bytes_to_parquet

    _require_well_formed(d, [scope])
    releases = {release_of(d, entry.parent) for entry, _ in payloads}
    if not payloads or None in releases or len(releases) != 1:
        raise ValueError(f"{d.name} {scope}: files must come from one of the row's directories")
    (release,) = releases
    assert release is not None
    sources = []
    for entry, raw in payloads:
        uri, size_bytes, modified = _listed(entry)
        sources.append(SourceFile(uri, hashlib.sha256(raw).hexdigest(), size_bytes, modified))
    staging = directory / "scope.parquet"
    dbc_bytes_to_parquet(
        [raw for _, raw in payloads],
        staging,
        dataset=d.name,
        ano=scope.ano if d.geography == "state" else None,
        uf=scope.uf,
        dictionary=d.dictionary,
        mes=scope.mes if d.monthly else None,
        source_ano=scope.ano if d.geography == "national" else None,
        release=release,
    )
    validate_identity(
        staging, load_dicionario(d.dictionary if d.dictionary is not None else d.name), scope
    )
    return StagedScope(staging, sources, parser_version(d))


def publish_staged(
    d: Dataset,
    scope: ScopeKey,
    staged: StagedScope,
    lake: Lake,
    *,
    policy: ImportPolicy = "append",
    run_id: str | None = None,
    batch_id: str | None = None,
) -> ImportResult | None:
    """Publish one staged scope atomically as one version."""
    return lake.publish_scope(
        d.name,
        staged.path,
        scope=scope,
        source_sha256=aggregate_sha256(staged.sources),
        parser_version=staged.parser_version,
        policy=policy,
        run_id=run_id,
        batch_id=batch_id,
        partition_by=d.partition_by,
        source_uri=staged.sources[0].uri,
        source_files=staged.sources,
    )


def ingest_raw(
    d: Dataset,
    scope: ScopeKey,
    payloads: Sequence[tuple[FtpEntry, bytes]],
    lake: Lake,
    *,
    policy: ImportPolicy = "append",
    run_id: str | None = None,
    batch_id: str | None = None,
) -> ImportResult | None:
    """Validate one scope's file(s) to staging, then publish them atomically as one version."""
    with tempfile.TemporaryDirectory(prefix="omnisus-source-") as tmp:
        staged = stage_raw(d, scope, payloads, Path(tmp))
        return publish_staged(
            d, scope, staged, lake, policy=policy, run_id=run_id, batch_id=batch_id
        )


def _require_well_formed(d: Dataset, scopes: Sequence[ScopeKey]) -> None:
    """Reject malformed scopes before the run starts, not during it.

    A monthly dataset asked for without a month is a caller bug, not an
    upstream condition, and it affects every scope equally — so it fails fast
    and loudly rather than becoming 700 identical ``failed`` outcomes that
    look like a server problem.
    """
    for scope in scopes:
        if d.geography == "national" and (scope.uf is not None or scope.mes is not None):
            raise ValueError("national yearly dataset requires uf=None and mes=None")
        if d.geography == "state" and scope.uf is None:
            raise ValueError("state dataset requires UF")
    if not d.monthly:
        return
    bad = [s for s in scopes if s.mes is None]
    if bad:
        raise ValueError(
            f"{d.name} is monthly; ScopeKey.mes is required "
            f"({len(bad)} scope(s) without one, e.g. {bad[0]})"
        )


async def run_scopes(
    dataset: str | Dataset,
    *,
    scopes: Sequence[ScopeKey],
    lake: Lake,
    concurrency: int = DEFAULT_CONCURRENCY,
    batch_size: int = DEFAULT_BATCH_SIZE,
    policy: ImportPolicy = "append",
    run_id: str | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    max_inflight_bytes: int = DEFAULT_MAX_INFLIGHT_BYTES,
) -> ImportReport:
    """Import many scopes, reporting per-scope outcomes instead of aborting.

    A wide import spans years DATASUS never published for a given UF. Before
    tolerance, the first such gap raised and discarded every result already
    collected — including scopes whose rows were already committed — so a
    702-scope run died on scope 3 with no partial results and no resume.

    Three filters keep work off the wire, cheapest first:

    1. ``coverage`` rejects scopes outside the dataset's declared window
       (``outside_coverage``) without asking the server for them.
    2. The listing: one fresh LIST per directory of the row per run. A scope
       the listing lacks is ``skipped`` (``not_listed``) without a download; a
       550 on a listed file, like any fetch error that exhausts its retry
       budget, is ``failed`` (``fetch_failed``) and worth retrying.
    3. With ``policy="skip_same"``, a scope whose publication recorded the same
       files (path, size, server time) under the same parser version is
       ``skipped`` (``unchanged``) without a download. Any difference downloads,
       and the publication then compares SHA-256 as before.

    Shape: ``concurrency`` fetches in flight, **one** consumer parsing and
    sinking, with commits every ``batch_size`` scopes. Fetch and parse used to
    be fully serialized — connect, RETR, parse, insert, one at a time — so
    wall clock was ``sum(fetch) + sum(parse+sink)``.

    ``max_inflight_bytes`` is a budget over the *listed* sizes: before
    fetching, each producer reserves the sum of its scope's file sizes (all of
    a split month's parts in one step, so no scope ever waits holding part of
    the budget) and holds it until the consumer releases the compressed
    payloads. A scope whose file is listed larger than ``max_payload_bytes``,
    or whose total exceeds ``max_inflight_bytes``, is ``failed``
    (``fetch_failed``) without a download, and the reason names the limit to
    raise. The fetcher also enforces ``max_payload_bytes`` during receipt.
    This is not a total RSS limit: decompressed DBF and parsing memory are
    additional.
    """
    if lake.in_transaction:
        raise RuntimeError("run_scopes cannot run inside an existing Lake.transaction")
    d = resolve(dataset)
    _require_well_formed(d, scopes)
    validate_policy(policy)
    run_id = run_id or str(uuid4())
    if type(max_payload_bytes) is not int or max_payload_bytes < 1:
        raise ValueError("max_payload_bytes must be a positive integer")
    if type(max_inflight_bytes) is not int or max_inflight_bytes < max_payload_bytes:
        raise ValueError("max_inflight_bytes must be at least max_payload_bytes")
    if concurrency < 1:
        raise ValueError(f"concurrency must be >= 1; got {concurrency}")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1; got {batch_size}")

    sources = await asyncio.to_thread(list_sources, d, refresh=True)
    version = parser_version(d)
    outcomes: dict[int, ScopeOutcome] = {}
    queued: list[tuple[int, ScopeKey, ResolvedSource]] = []
    for index, scope in enumerate(scopes):
        if not in_coverage(d, scope):
            first, last = d.coverage
            outcomes[index] = ScopeOutcome(
                scope=scope,
                status="skipped",
                reason=f"outside declared coverage {first}..{last or 'ongoing'}",
                code="outside_coverage",
            )
        elif scope not in sources:
            outcomes[index] = ScopeOutcome(
                scope=scope,
                status="skipped",
                reason=f"not in the server listing of {', '.join(d.directories().values())}",
                code="not_listed",
            )
        elif policy == "skip_same" and unchanged_since_listing(
            lake,
            d.name,
            scope,
            parser_version=version,
            listed=[_listed(entry) for entry in sources[scope].files],
        ):
            outcomes[index] = ScopeOutcome(
                scope=scope,
                status="skipped",
                reason="same listed files and parser version already published",
                code="unchanged",
            )
        else:
            source = sources[scope]
            too_big = _over_budget(source, max_payload_bytes, max_inflight_bytes)
            if too_big is None:
                queued.append((index, scope, source))
            else:
                outcomes[index] = _outcome_for_error(d, scope, ValueError(too_big))

    queue: asyncio.Queue[_Fetched | None] = asyncio.Queue(maxsize=concurrency)
    sem = asyncio.Semaphore(concurrency)

    # A scope reserves its listed bytes in one step BEFORE downloading, so no
    # scope waits while holding part of the budget, and queued payloads stay
    # covered until the consumer is done with them.
    budget = asyncio.Condition()
    available = max_inflight_bytes
    held: dict[int, int] = {}
    """Scope index -> bytes it has reserved."""

    async def reserve(index: int, need: int) -> None:
        nonlocal available
        async with budget:
            await budget.wait_for(lambda: available >= need)
            available -= need
            held[index] = need

    async def release(index: int) -> None:
        nonlocal available
        if index in held:
            async with budget:
                available += held.pop(index)
                budget.notify_all()

    async def produce(index: int, scope: ScopeKey, source: ResolvedSource) -> None:
        async with sem:
            enqueued = False
            try:
                await reserve(index, sum(entry.size_bytes for entry in source.files))
                raws: list[bytes] = []
                try:
                    for entry in source.files:
                        with download_limit(max_payload_bytes):
                            raw = await fetch_dbc_bytes(entry)
                        if len(raw) > max_payload_bytes:
                            del raw
                            raise ValueError("download exceeds payload bytes limit")
                        raws.append(raw)
                except Exception as exc:
                    # The traceback keeps this frame alive after the budget is
                    # released; do not let it keep the parts already downloaded.
                    raws.clear()
                    raw = None
                    await release(index)
                    await queue.put((index, scope, None, exc))
                else:
                    await queue.put(
                        (index, scope, list(zip(source.files, raws, strict=True)), None)
                    )
                    enqueued = True
            finally:
                if not enqueued:
                    await release(index)

    async def produce_all() -> None:
        tasks = [asyncio.create_task(produce(i, s, source)) for i, s, source in queued]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        await queue.put(None)

    producer = asyncio.create_task(produce_all())
    try:
        exhausted = False
        while not exhausted:
            batch: dict[int, ScopeOutcome] = {}
            batch_id = str(uuid4())
            writing: set[int] = set()
            pending_skips: set[int] = set()
            try:
                with lake.transaction():
                    while len(batch) < batch_size:
                        item = await _next_fetched(queue, producer)
                        if item is None:
                            exhausted = True
                            break
                        index, scope, payloads, exc = item
                        if exc is not None:
                            batch[index] = _outcome_for_error(d, scope, exc)
                            continue
                        assert payloads is not None, "payloads are set whenever exc is None"
                        writing.add(index)
                        batch[index] = ScopeOutcome(
                            scope=scope,
                            status="failed",
                            reason="ingestion did not complete",
                            code="ingest_failed",
                        )
                        try:
                            with tempfile.TemporaryDirectory(prefix="omnisus-source-") as tmp:
                                try:
                                    staged = stage_raw(d, scope, payloads, Path(tmp))
                                except Exception as exc:
                                    # Rejected before writing: the batch holds nothing of
                                    # this scope, so the others need not roll back.
                                    writing.discard(index)
                                    batch[index] = ScopeOutcome(
                                        scope=scope,
                                        status="failed",
                                        reason=str(exc),
                                        code="ingest_failed",
                                    )
                                    continue
                                result = publish_staged(
                                    d,
                                    scope,
                                    staged,
                                    lake,
                                    policy=policy,
                                    run_id=run_id,
                                    batch_id=batch_id,
                                )
                        except TransactionStateError:
                            batch.pop(index, None)
                            raise
                        except Exception as exc:
                            batch[index] = ScopeOutcome(
                                scope=scope, status="failed", reason=str(exc), code="ingest_failed"
                            )
                            raise
                        finally:
                            payloads = None
                            item = None
                            await release(index)
                        if result is None:
                            if any(o.scope == scope and o.status == "ok" for o in batch.values()):
                                pending_skips.add(index)
                            else:
                                writing.discard(index)
                            batch[index] = ScopeOutcome(
                                scope=scope,
                                status="skipped",
                                reason="same source and parser version already published",
                                code="unchanged",
                            )
                        else:
                            batch[index] = ScopeOutcome(scope=scope, status="ok", result=result)
            except Exception as exc:
                if (
                    isinstance(exc, (TransactionStateError, _ProducerStoppedError))
                    or not lake.is_usable
                ):
                    rollback_known = not isinstance(exc, TransactionStateError) and lake.is_usable
                    determined = dict(outcomes)
                    for i, outcome in batch.items():
                        if i in writing and not rollback_known:
                            continue
                        determined[i] = (
                            outcome
                            if outcome.status != "ok" and i not in pending_skips
                            else ScopeOutcome(
                                scope=outcome.scope,
                                status="failed",
                                reason=f"batch rolled back: {exc}",
                                code="rolled_back",
                            )
                        )
                    partial = ImportReport(
                        tuple(determined[i] for i in sorted(determined)), run_id=run_id
                    )
                    unresolved = tuple(
                        (i, scope) for i, scope in enumerate(scopes) if i not in determined
                    )
                    raise ImportAbortedError(partial, unresolved) from exc

                logger.warning("run_scopes.batch_failed", dataset=d.name, error=str(exc))
                for index, outcome in batch.items():
                    outcomes[index] = (
                        outcome
                        if outcome.status != "ok" and index not in pending_skips
                        else ScopeOutcome(
                            scope=outcome.scope,
                            status="failed",
                            reason=f"batch rolled back: {exc}",
                            code="rolled_back",
                        )
                    )
            else:
                outcomes.update(batch)
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        while not queue.empty():
            queue.get_nowait()
        for index in tuple(held):
            await release(index)

    report = ImportReport(outcomes=tuple(outcomes[i] for i in sorted(outcomes)), run_id=run_id)
    from omnisus.lake.publication import record_failed_attempts

    try:
        record_failed_attempts(lake, report)
    except Exception as exc:
        # Scope outcomes are still determined; only the durable audit write
        # requires inspection. Never turn already committed data into failure.
        raise ImportAbortedError(report, ()) from exc
    logger.info(
        "run_scopes.done",
        dataset=d.name,
        ok=len(report.ok),
        skipped=len(report.skipped),
        failed=len(report.failed),
        rows=report.rows,
    )
    return report


def _over_budget(source: ResolvedSource, max_payload: int, max_inflight: int) -> str | None:
    """Why ``source`` cannot be fetched under these limits, from its listed sizes."""
    for entry in source.files:
        if entry.size_bytes > max_payload:
            return (
                f"{entry.name} is listed at {entry.size_bytes} bytes; "
                f"raise max_payload_bytes to at least {entry.size_bytes}"
            )
    total = sum(entry.size_bytes for entry in source.files)
    if total > max_inflight:
        return (
            f"{len(source.files)} file(s) listed at {total} bytes in total; "
            f"raise max_inflight_bytes to at least {total}"
        )
    return None


def _outcome_for_error(d: Dataset, scope: ScopeKey, exc: BaseException) -> ScopeOutcome:
    """A listed scope whose download failed is worth retrying."""
    logger.warning("run_scopes.failed", dataset=d.name, scope=str(scope), error=str(exc))
    return ScopeOutcome(scope=scope, status="failed", reason=str(exc), code="fetch_failed")
