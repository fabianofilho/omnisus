"""omnisus — Brazilian public health database ingestion lib."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import polars as pl

from omnisus._loop import run_sync
from omnisus._version import __version__
from omnisus.lake import CatalogAttachError, Lake, LakeReader
from omnisus.lake.catalog import set_lake_dir
from omnisus.lake.publication import DeletionResult, ImportPolicy, scope_filter
from omnisus.lake.sql import qualified, quote_identifier
from omnisus.metadata import describe_dataset
from omnisus.products import Product, datasets, products
from omnisus.research import (
    Citation,
    citation_from_publications,
    cite,
    import_research,
    latest_snapshot_id,
    municipality_join_key,
    municipality_join_key_sql,
    reference_join_sql,
)
from omnisus.sources._base import (
    ALL_UFS,
    ImportAbortedError,
    ImportReport,
    ImportResult,
    ScopeKey,
    ScopeOutcome,
)
from omnisus.sources.datasus_ftp._runner import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
)
from omnisus.sources.datasus_ftp._runner import run_scopes as _run_scopes_ftp
from omnisus.sources.datasus_ftp.datasets import Dataset, resolve
from omnisus.sources.datasus_ftp.fetch import (
    DEFAULT_MAX_INFLIGHT_BYTES,
    DEFAULT_MAX_PAYLOAD_BYTES,
)
from omnisus.sources.datasus_ftp.inventory import (
    FtpEntry,
    FtpPathNotFound,
    FtpUnavailable,
    available,
    available_releases,
    list_sources,
)
from omnisus.sources.datasus_ftp.inventory import crawl as _crawl
from omnisus.transforms.analytics import (
    AnalyticalProjection,
    DerivedColumn,
    SourceContext,
    UnavailableField,
    analytical_projection,
)
from omnisus.transforms.columns import check_columns
from omnisus.transforms.dictionaries import display_row, label


def scopes_for(
    dataset: str | Dataset,
    *,
    years: Iterable[int],
    ufs: Sequence[str] | None = None,
    months: Iterable[int] | None = None,
) -> list[ScopeKey]:
    """Every scope (UF x year [x month]) of a dataset, without asking the server.

    Planning is composition: pass the result, or any other list of scopes, to
    :func:`import_dataset`. Scopes DATASUS does not publish are later reported as
    ``skipped``; :func:`available` plans only what the server lists.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a :class:`Dataset`; see
            :func:`datasets`.
        years: Years, e.g. ``[2022, 2023]`` or ``range(2020, 2024)``.
        ufs: UF abbreviations, e.g. ``["RR", "AC"]``. ``None`` (default) means all 27
            (:data:`ALL_UFS`). National datasets (SINAN, SIM subsets) accept only ``None``.
        months: Months 1-12 for monthly datasets (SIH, SIA, CNES); ``None`` (default)
            means all twelve. Ignored for yearly UF datasets; national datasets accept
            only ``None``.

    Returns:
        The scopes, ordered by year, then UF, then month.

    Raises:
        ValueError: ``dataset`` is unknown, or a national dataset got ``ufs`` or
            ``months``.

    Examples:
        >>> import omnisus as sus
        >>> sus.scopes_for("sih_aih_reduzida", years=[2024], ufs=["RR"], months=[1, 2])
        [ScopeKey(uf='RR', ano=2024, mes=1), ScopeKey(uf='RR', ano=2024, mes=2)]
        >>> sus.scopes_for("sinan_chagas", years=[2023])
        [ScopeKey(uf=None, ano=2023, mes=None)]
    """
    d = resolve(dataset)
    if d.geography == "national":
        if ufs is not None:
            raise ValueError(
                "national datasets do not accept UF filters; filter records after import"
            )
        if months is not None:
            raise ValueError("national yearly datasets do not accept month filters")
        return [ScopeKey(uf=None, ano=year) for year in years]
    uf_list = tuple(ufs) if ufs is not None else ALL_UFS
    month_list = tuple(months) if months is not None else tuple(range(1, 13))
    scopes: list[ScopeKey] = []
    for year in years:
        for uf in uf_list:
            if d.monthly:
                scopes.extend(ScopeKey(uf=uf, ano=year, mes=m) for m in month_list)
            else:
                scopes.append(ScopeKey(uf=uf, ano=year))
    return scopes


def browse(path: str, *, depth: int = 1, refresh: bool = False) -> list[FtpEntry]:
    """List any DATASUS FTP path, including datasets the package does not curate.

    The open-world counterpart to :func:`available`: it reaches other SINAN agravos,
    CIHA or PCE. Eager, so a huge tree is listed whole; call
    ``omnisus.sources.datasus_ftp.inventory.crawl`` for a lazy walk.

    Args:
        path: Absolute FTP path, e.g. ``"/dissemin/publicos/SINAN/DADOS/FINAIS"``.
        depth: How many directory levels to list; ``1`` (default) lists ``path`` only.
        refresh: ``True`` ignores the local listing cache and asks the server again.

    Returns:
        One :class:`FtpEntry` per file or directory, with size and server time.

    Raises:
        FtpPathNotFound: the server has no such path.
        FtpUnavailable: the server did not answer after retries.

    Examples:
        >>> import omnisus as sus
        >>> entries = sus.browse("/dissemin/publicos/SINAN/DADOS/FINAIS")  # doctest: +SKIP
        >>> entries[0].name  # doctest: +SKIP
        'ACBIBR06.dbc'
    """
    return list(_crawl(path, depth=depth, refresh=refresh))


_AFTER_IMPORT: dict[str, Callable[[Lake], object]] = {
    "cnes_estabelecimentos": Lake.ensure_aux_cnes_view,
}
"""Behaviour that follows an import, keyed by dataset. It lives here, not on the
registry row (ADR 0002), and runs whichever function started the import."""


def import_dataset(
    dataset: str | Dataset,
    *,
    scopes: Sequence[ScopeKey],
    target: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    batch_size: int = DEFAULT_BATCH_SIZE,
    policy: ImportPolicy = "append",
    run_id: str | None = None,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    max_inflight_bytes: int = DEFAULT_MAX_INFLIGHT_BYTES,
) -> ImportReport:
    """Import the given scopes of a DATASUS FTP dataset into the lake (operator door).

    The import iterates ``scopes`` and never asks where they came from:
    :func:`scopes_for` plans blindly and :func:`available` asks the server first.
    Every run lists the server once and imports what it lists; callers never choose
    a release or file name. Importing ``cnes_estabelecimentos`` also refreshes the
    ``aux_cnes`` view. Works inside a notebook's running event loop.

    Args:
        dataset: Dataset name, e.g. ``"sia_bpa_individualizado"``, or a
            :class:`Dataset`; see :func:`datasets`.
        scopes: The scopes to import, e.g. from :func:`scopes_for` or :func:`available`.
        target: DuckLake target such as ``"ducklake:/path/omnisus.ducklake"`` or
            ``"ducklake:postgresql://…?storage=s3://…"``. ``None`` (default) is
            ``data/raw/omnisus.ducklake`` under the working directory, or under
            ``$OMNISUS_DATA_DIR``.
        concurrency: Downloads in flight. DATASUS FTP is a shared public server; raise
            it only with reason.
        batch_size: Scopes committed in one DuckLake transaction, hence one snapshot.
        policy: What to do with a scope already in the lake: ``"append"`` (default)
            adds rows again; ``"skip_same"`` skips it when file and parser are
            unchanged, without downloading when the listing shows the same path,
            size and server time; ``"error_if_exists"`` fails that scope;
            ``"replace"`` rewrites it. :func:`load` and :func:`import_research` default to ``"skip_same"``.
        run_id: Your identifier for this run, chosen before it starts, to reconcile an
            interrupted commit through ``Lake.publications(run_id=...)``. ``None``
            generates one.
        max_payload_bytes: Largest compressed download accepted per file (512 MiB).
        max_inflight_bytes: Compressed bytes held at once before parsing (1 GiB).
            Neither bounds total memory: a decompressed DBF is held whole.

    Returns:
        One :class:`ScopeOutcome` per scope: ``ok``, ``skipped`` (e.g. the server
        does not list it) or ``failed``, with ``code`` and ``reason``. Inspect
        ``report.failed``; later batches continue after a failed scope.

    Raises:
        ImportAbortedError: the lake transaction failed mid-run; its ``report`` and
            ``unresolved`` say what was committed. Inspect before retrying.
        ValueError: ``dataset`` is unknown or ``policy`` is not one of the four values.

    Examples:
        >>> import omnisus as sus
        >>> scopes = sus.available("sim_obitos", years=[2023], ufs=["RR"])  # doctest: +SKIP
        >>> report = sus.import_dataset("sim_obitos", scopes=scopes)  # doctest: +SKIP
        >>> [(str(o.scope), o.status) for o in report.outcomes]  # doctest: +SKIP
        [('RR_2023', 'ok')]
    """
    d = resolve(dataset)

    async def run() -> ImportReport:
        with Lake.local(target) as lake:
            report = await _run_scopes_ftp(
                d,
                scopes=scopes,
                lake=lake,
                concurrency=concurrency,
                batch_size=batch_size,
                policy=policy,
                run_id=run_id,
                max_payload_bytes=max_payload_bytes,
                max_inflight_bytes=max_inflight_bytes,
            )
            if after_import := _AFTER_IMPORT.get(d.name):
                after_import(lake)
            return report

    return run_sync(run)


def _loadable(dataset: str | Dataset) -> Dataset:
    """The FTP dataset ``load`` imports; another product's name points to its function."""
    other = {p.name for p in products() if p.dataset is None}
    if dataset in other:
        raise ValueError(
            f"load reads DATASUS FTP datasets; use sus.import_{dataset} for {dataset}"
        )
    return resolve(dataset)


def load(
    dataset: str | Dataset,
    *,
    years: Iterable[int],
    ufs: Sequence[str] | None = None,
    months: Iterable[int] | None = None,
    target: str | None = None,
    policy: ImportPolicy = "skip_same",
) -> pl.DataFrame:
    """Download what DATASUS publishes for these scopes and return the rows.

    The one-call path for a script or notebook cell. It imports into the lake (a
    second call downloads nothing new) and returns the requested scopes' rows with
    codes as DATASUS published them. When every file comes from a validated source
    (see ``describe_dataset(dataset)["analytics"]["validated_sources"]``) it also adds
    the harmonised categories: ``idade_anos_completos``, ``idade_status``,
    ``sexo_categoria``, ``sexo_status`` and ``<date>_data`` columns. Otherwise it
    leaves them out and warns once. Readable labels come from :func:`label`.

    Args:
        dataset: DATASUS FTP dataset name, e.g. ``"sim_obitos"``,
            ``"sih_aih_reduzida"``; see :func:`datasets`. IBGE population, SIGTAP and
            CNES names have their own functions (:func:`import_ibge_populacao`,
            :func:`import_sigtap`, :func:`import_cnes_master`).
        years: Years, e.g. ``[2023]`` or ``range(2020, 2024)``.
        ufs: UF abbreviations, e.g. ``["RR"]``. Required for datasets published per
            UF; pass :data:`ALL_UFS` for all of Brazil. National datasets (SINAN,
            SIM subsets) accept only ``None``.
        months: Months 1-12 of monthly datasets (SIH, SIA, CNES), e.g. ``[1, 2]``;
            ``None`` (default) means all twelve.
        target: DuckLake target; ``None`` (default) is ``data/raw/omnisus.ducklake``
            under the working directory, or under ``$OMNISUS_DATA_DIR``.
        policy: ``"skip_same"`` (default) reuses scopes already imported from the
            same file; ``"replace"`` rewrites scopes imported from another file or
            dictionary version; ``"append"`` and ``"error_if_exists"`` as in
            :func:`import_dataset`.

    Returns:
        A polars DataFrame with one row per record of the requested scopes.

    Raises:
        ValueError: ``dataset`` is unknown or not an FTP dataset, ``ufs`` is missing
            for a UF dataset, or given for a national one.
        RuntimeError: a scope failed to import; the message names each one.
        LookupError: DATASUS publishes none of the requested scopes.

    Warns:
        UserWarning: harmonised categories were left out, and why.

    Examples:
        >>> import omnisus as sus
        >>> dados = sus.load("sim_obitos", years=[2023], ufs=["RR"])  # doctest: +SKIP
        >>> dados.height  # doctest: +SKIP
        3311
        >>> dados = sus.label("sim_obitos", dados, columns=["sexo"])  # doctest: +SKIP
    """
    d = _loadable(dataset)
    if ufs is None and d.geography != "national":
        raise ValueError(
            f"{d.name} is published per UF: pass ufs=['RR', ...], or ufs=sus.ALL_UFS "
            "for all of Brazil"
        )
    scopes = scopes_for(d, years=years, ufs=ufs, months=months)
    report = import_dataset(d, scopes=scopes, target=target, policy=policy)
    if report.failed:
        reasons = "; ".join(f"{o.scope}: {o.reason}" for o in report.failed)
        raise RuntimeError(
            f"{d.name} import failed ({reasons}). A scope already imported from "
            "another file or parser version is rewritten with policy='replace'."
        )
    rows = _read_with_harmonised(d, scopes, target)
    if rows.is_empty():
        raise LookupError(f"{d.name}: DATASUS publishes none of these scopes: {scopes}")
    return rows


def _read_with_harmonised(
    d: Dataset, scopes: Sequence[ScopeKey], target: str | None
) -> pl.DataFrame:
    """The scopes' rows plus the harmonised categories their sources allow (ADR 0003).

    Rows, schema and source identities come from one pinned snapshot, as
    :func:`analytical_projection` requires. A category the rule leaves out is
    named in one warning; a dataset without rules warns nothing.
    """
    with LakeReader(target) as latest:
        if d.name not in latest.tables():
            return pl.DataFrame()
        snapshot = latest_snapshot_id(latest)
    predicates = [scope_filter(scope) for scope in scopes]
    where = " OR ".join(f"({sql})" for sql, _ in predicates)
    args = [value for _, values in predicates for value in values]
    with LakeReader(target, snapshot_id=snapshot) as reader:
        con = reader.connect()
        table = qualified(reader.alias, d.name)
        schema = {
            row[0]: row[1] for row in con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()
        }
        sources = [
            SourceContext.from_publication(row)
            for row in reader.publications()
            if row["dataset"] == d.name and row["active"] and row["scope"] in scopes
        ]
        projection = analytical_projection(d.name, observed_schema=schema, scopes=sources)
        derived = "".join(
            f", {column.expression} AS {quote_identifier(column.name)}"
            for column in projection.columns
        )
        rows = con.execute(f"SELECT *{derived} FROM {table} WHERE {where}", args).pl()
    left_out = [u for u in projection.unavailable if u.reason != "unsupported_dataset"]
    if left_out:
        warnings.warn(
            f"{d.name}: harmonised categories left out: "
            + ", ".join(f"{u.field} ({u.reason})" for u in left_out)
            + ". They exist only for validated sources (docs/decisions/0003); "
            "labels from sus.label work for any scope.",
            UserWarning,
            stacklevel=3,
        )
    return rows


def import_ibge_populacao(
    *,
    years: Iterable[int],
    census: bool,
    target: str | None = None,
) -> list[ImportResult]:
    """Import IBGE population by municipality: a census or the year's latest estimate.

    Each population edition is its own publication, identified by the returned
    ``publication_id`` in ``ibge_population_manifest``; it never appears in
    ``Lake.publications()``. Reconcile an interrupted run through that manifest.

    Args:
        years: Years, e.g. ``[2022]``. Censuses exist for 2010 and 2022; an estimate
            is importable only as the aggregate's latest edition, and years without a
            verified territorial universe are refused.
        census: Required, with no default, so nobody gets an estimate thinking it is
            the census. ``True`` imports the census; ``False`` the latest estimate.
        target: DuckLake target; ``None`` (default) is ``data/raw/omnisus.ducklake``
            under the working directory, or under ``$OMNISUS_DATA_DIR``.

    Returns:
        One :class:`ImportResult` per year, with ``rows`` and ``publication_id``.

    Raises:
        ValueError: the year has no such edition.
        TypeError: ``census`` was not given.

    Examples:
        >>> import omnisus as sus
        >>> (censo,) = sus.import_ibge_populacao(years=[2022], census=True)  # doctest: +SKIP
        >>> censo.rows  # doctest: +SKIP
        5570
    """
    from omnisus.sources.ibge.importers.pop import import_pop_year

    edition = "census" if census else "estimate"

    async def run() -> list[ImportResult]:
        results: list[ImportResult] = []
        with Lake.local(target) as lake:
            for y in years:
                results.append(await import_pop_year(year=y, lake=lake, product=edition))
        return results

    return run_sync(run)


def import_sigtap(
    *,
    years: Iterable[int],
    months: Iterable[int] | None = None,
    target: str | None = None,
    policy: ImportPolicy = "skip_same",
) -> ImportReport:
    """Import SIGTAP procedures, one competência per year x month.

    Each competência is one national monthly publication from
    ``ftp2.datasus.gov.br/public/sistemas/tup/downloads`` into
    ``aux_sigtap_procedimentos``. Nothing joins at import: join on
    ``co_procedimento`` and the record's competência yourself.

    Args:
        years: Years, e.g. ``[2024]``.
        months: Months 1-12, e.g. ``[1, 2]``; ``None`` (default) means all twelve.
        target: DuckLake target; ``None`` (default) is ``data/raw/omnisus.ducklake``
            under the working directory, or under ``$OMNISUS_DATA_DIR``.
        policy: ``"skip_same"`` (default) reports an unchanged zip as
            ``skipped``/``unchanged``; ``"append"``, ``"error_if_exists"`` and
            ``"replace"`` as in :func:`import_dataset`.

    Returns:
        One :class:`ScopeOutcome` per competência; one the server does not list is
        ``skipped``/``not_listed``. :func:`cite` names each zip.

    Examples:
        >>> import omnisus as sus
        >>> report = sus.import_sigtap(years=[2024], months=[1])  # doctest: +SKIP
        >>> [(str(o.scope), o.status) for o in report.outcomes]  # doctest: +SKIP
        [('national_2024_01', 'ok')]
    """
    from omnisus.sources.sigtap import import_sigtap as _impl

    month_list = tuple(months) if months is not None else tuple(range(1, 13))
    wanted = [(year, month) for year in years for month in month_list]
    with Lake.local(target) as lake:
        return _impl(wanted, lake=lake, policy=policy)


def available_sigtap() -> list[tuple[int, int]]:
    """Every SIGTAP competência the server lists now, oldest first.

    Returns:
        ``(year, month)`` pairs, e.g. ``[(2008, 1), (2008, 2), ...]``.

    Raises:
        FtpUnavailable: the server did not answer after retries.

    Examples:
        >>> import omnisus as sus
        >>> sus.available_sigtap()[:2]  # doctest: +SKIP
        [(2008, 1), (2008, 2)]
    """
    from omnisus.sources.sigtap import available_sigtap as _impl

    return _impl()


def import_cnes_master(
    *,
    codes: Sequence[str] | None = None,
    target: str | None = None,
    concurrency: int = 5,
    only_missing: bool = True,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Fetch CNES establishment names from the public API into ``cnes_master``.

    The CNES-ST DBF has no establishment names; this pulls them from
    ``apidadosabertos.saude.gov.br`` and joins them into the ``aux_cnes`` view. It
    is an idempotent upsert, not a publication: no ``run_id``, no ``policy``, no
    manifest row. To finish an interrupted run, run it again.

    Args:
        codes: 7-digit CNES codes, e.g. ``["2789590"]``. ``None`` (default) takes
            every code in ``cnes_estabelecimentos``.
        target: DuckLake target; ``None`` (default) is ``data/raw/omnisus.ducklake``
            under the working directory, or under ``$OMNISUS_DATA_DIR``.
        concurrency: API requests in flight (default 5).
        only_missing: ``True`` (default) skips codes already in ``cnes_master``, so
            reruns are incremental; ``False`` fetches every code again.
        progress: Optional ``progress(done, total)`` callback after each fetch.

    Returns:
        The number of records written in this run.

    Raises:
        ValueError: a code is not seven ASCII digits, or the API returned conflicting
            records for one code.

    Examples:
        >>> import omnisus as sus
        >>> sus.import_cnes_master(codes=["2789590"])  # doctest: +SKIP
        1
    """
    from omnisus.sources.cnes.importers.master import (
        import_cnes_master as _impl,
    )

    return _impl(
        codes=codes,
        target=target,
        concurrency=concurrency,
        only_missing=only_missing,
        progress=progress,
    )


def outdated(
    dataset: str | Dataset,
    *,
    lake: Lake | LakeReader,
    refresh: bool = False,
) -> list[ScopeKey]:
    """Scopes whose imported files differ from what the server lists now.

    Different means another path (a preliminary year that became final, or a moved
    directory), or the same path with another size or server time (DATASUS
    republished it). Publications without a recorded source are always reported.
    Scopes the server no longer lists are a withdrawal, not returned here.
    Read-only.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a :class:`Dataset`.
        lake: An open :class:`Lake` or :class:`LakeReader`.
        refresh: ``True`` ignores the local listing cache and asks the server again.

    Returns:
        The scopes to re-import with :func:`import_dataset` and
        ``policy="replace"``, ordered by year, UF and month.

    Raises:
        ValueError: ``dataset`` is unknown.
        FtpUnavailable: the server did not answer after retries.

    Examples:
        >>> import omnisus as sus
        >>> with sus.LakeReader() as lake:  # doctest: +SKIP
        ...     stale = sus.outdated("sim_obitos", lake=lake)
        >>> sus.import_dataset(  # doctest: +SKIP
        ...     "sim_obitos", scopes=stale, policy="replace", run_id="refresh-2026-09"
        ... )
    """
    d = resolve(dataset)
    current = list_sources(d, refresh=refresh)
    changed = {
        row["scope"]
        for row in lake.publications()
        if row["dataset"] == d.name
        and row["active"]
        and row["scope"] in current
        and _files_differ(row["sources"], current[row["scope"]].files)
    }
    return sorted(changed, key=lambda s: (s.ano, s.uf or "", s.mes or 0))


def _files_differ(recorded: Sequence[Mapping[str, object]], listed: Sequence[FtpEntry]) -> bool:
    if [urlparse(str(r["source_uri"])).path for r in recorded] != [e.path for e in listed]:
        return True
    return any(
        (r["source_bytes"] is not None and r["source_bytes"] != e.size_bytes)
        or (
            r["source_modified"] is not None
            and r["source_modified"] != e.modified.strftime("%Y-%m-%dT%H:%M")
        )
        for r, e in zip(recorded, listed, strict=True)
    )


__all__ = [
    "ALL_UFS",
    "AnalyticalProjection",
    "CatalogAttachError",
    "Citation",
    "Dataset",
    "DeletionResult",
    "DerivedColumn",
    "FtpEntry",
    "FtpPathNotFound",
    "FtpUnavailable",
    "ImportAbortedError",
    "ImportPolicy",
    "ImportReport",
    "ImportResult",
    "Lake",
    "LakeReader",
    "Product",
    "ScopeKey",
    "ScopeOutcome",
    "SourceContext",
    "UnavailableField",
    "__version__",
    "analytical_projection",
    "available",
    "available_releases",
    "available_sigtap",
    "browse",
    "check_columns",
    "citation_from_publications",
    "cite",
    "datasets",
    "describe_dataset",
    "display_row",
    "import_cnes_master",
    "import_dataset",
    "import_ibge_populacao",
    "import_research",
    "import_sigtap",
    "label",
    "latest_snapshot_id",
    "load",
    "municipality_join_key",
    "municipality_join_key_sql",
    "outdated",
    "products",
    "reference_join_sql",
    "resolve",
    "scopes_for",
    "set_lake_dir",
]
