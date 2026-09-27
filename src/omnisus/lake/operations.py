"""High-level Lake API."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Self

import structlog

from omnisus.lake._transactions import (
    CommitOutcomeUnknown,
    TransactionReceipt,
    TransactionStateError,
)
from omnisus.lake.catalog import CatalogURI, parse_target, resolve_target
from omnisus.lake.connection import make_connection
from omnisus.lake.session import Session
from omnisus.lake.sql import qualified, quote_identifier, quote_literal

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime
    from pathlib import Path

    import polars as pl

    from omnisus.lake.publication import DeletionResult
    from omnisus.sources._base import ImportResult, ScopeKey

logger = structlog.get_logger(__name__)


class Lake(Session):
    """Writer handle on a DuckLake.

    Use :meth:`local` with a ``ducklake:`` target or :meth:`cloud` for a
    Postgres-backed catalog. Managed ingestion requires one writer per lake,
    including when the catalog is hosted in Postgres. To only read, open a
    :class:`~omnisus.lake.session.LakeReader` instead: it takes no lock.
    """

    def __init__(self, *, target: CatalogURI, alias: str = "lake") -> None:
        self._target = target
        self._in_transaction = False
        self._pending_results: list[ImportResult] = []
        self._ensured: set[str] = set()
        """Tables this handle has already created and partitioned. Ensuring a
        table costs a schema read of the staging file; once per run is enough."""
        self._columns: dict[str, set[str]] = {}
        """Known column names per table, so schema reconciliation does not
        re-query the catalog for every scope."""
        from omnisus.lake.locking import WriterLock

        self._writer_lock = WriterLock(target.catalog_uri)
        try:
            con = make_connection(
                catalog_uri=target.catalog_uri,
                storage_root=target.storage_root,
                alias=alias,
            )
        except BaseException:
            self._writer_lock.close()
            raise
        super().__init__(con, alias)

    @classmethod
    def local(cls, target: str | None = None) -> Self:
        """Open, or create, a lake on local disk for writing.

        One writer per lake: a second handle opening it for writing, in this process
        or another, fails at once with ``WriterBusyError``. Use
        :class:`~omnisus.LakeReader` to read while another process writes.

        Args:
            target: ``"ducklake:<dir>/omnisus.ducklake"``: data files go in that
                directory and the SQLite catalog next to it. ``None`` (default) is
                ``data/raw/omnisus.ducklake`` under the working directory, or under
                ``$OMNISUS_DATA_DIR``.

        Returns:
            An open :class:`Lake`; use it as a context manager so it closes.

        Raises:
            ValueError: ``target`` does not start with ``ducklake:``.
            WriterBusyError: another handle already has this lake open for writing
                (``omnisus.lake.locking.WriterBusyError``).
            CatalogAttachError: DuckDB could not attach the catalog.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.bootstrap_auxiliares()
        """
        return cls(target=parse_target(resolve_target(target)))

    @classmethod
    def cloud(cls, *, catalog: str, storage: str) -> Self:
        """Open a lake whose catalog is in PostgreSQL and data in object storage.

        Args:
            catalog: ``"postgresql://user:password@host/db"``.
            storage: Data path, e.g. ``"s3://bucket/lake"``.

        Returns:
            An open :class:`Lake`.

        Raises:
            ValueError: ``catalog`` is not a ``postgresql://`` URI.
            CatalogAttachError: DuckDB could not attach the catalog.

        Examples:
            >>> import omnisus as sus
            >>> lake = sus.Lake.cloud(  # doctest: +SKIP
            ...     catalog="postgresql://u:p@db/lake", storage="s3://bucket/lake"
            ... )
        """
        if not catalog.startswith(("postgresql://", "postgres://")):
            raise ValueError("cloud catalog must be postgresql://")
        return cls(target=CatalogURI(catalog_uri=catalog, storage_root=storage))

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def _read_snapshot(self) -> int | None:
        row = self._con.execute(
            "SELECT id FROM ducklake_last_committed_snapshot(?)", [self._alias]
        ).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    @contextlib.contextmanager
    def transaction(self) -> Iterator[TransactionReceipt]:
        """Group writes into one DuckLake transaction, hence one snapshot.

        Yields:
            A receipt whose ``snapshot_id`` is set once the context commits.

        Raises:
            RuntimeError: already inside a transaction on this handle.
            TransactionStateError: the transaction could not begin or end cleanly;
                the handle becomes unusable, so close it and inspect the catalog.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake, lake.transaction() as receipt:  # doctest: +SKIP
            ...     lake.ensure_aux_cnes_view()
        """
        self.connect()  # Reject closed or invalidated handles.
        if self._in_transaction:
            raise RuntimeError("nested Lake.transaction is not supported")
        self._columns.clear()
        self._ensured.clear()
        try:
            before = self._read_snapshot()
            self._con.execute("BEGIN TRANSACTION")
        except BaseException as exc:
            self._unusable = True
            if not isinstance(exc, Exception):
                raise
            raise TransactionStateError("could not begin managed transaction") from exc

        receipt = TransactionReceipt()
        self._in_transaction = True
        self._pending_results = []
        try:
            try:
                yield receipt
            except BaseException as original:
                try:
                    self._con.execute("ROLLBACK")
                except BaseException as rollback_error:
                    self._unusable = True
                    original.add_note(f"rollback also failed: {rollback_error}")
                    if isinstance(original, Exception):
                        if not isinstance(rollback_error, Exception):
                            raise rollback_error from original
                        raise TransactionStateError(
                            "rollback failed; handle unusable"
                        ) from original
                raise
            else:
                try:
                    self._con.execute("COMMIT")
                except BaseException as original:
                    self._unusable = True
                    try:
                        self._con.execute("ROLLBACK")
                    except BaseException as rollback_error:
                        original.add_note(f"rollback cleanup also failed: {rollback_error}")
                        if isinstance(original, Exception) and not isinstance(
                            rollback_error, Exception
                        ):
                            raise rollback_error from original
                    if not isinstance(original, Exception):
                        raise
                    raise CommitOutcomeUnknown(
                        "commit outcome unknown; inspect before retry"
                    ) from original

                receipt.committed = True
                try:
                    after = self._read_snapshot()
                except Exception:
                    logger.warning("lake.snapshot_unavailable_after_commit")
                else:
                    receipt.snapshot_id = after if after != before else None
                for result in self._pending_results:
                    result.snapshot_id = receipt.snapshot_id
        finally:
            self._in_transaction = False
            self._pending_results = []
            self._columns.clear()
            self._ensured.clear()

    def optimize(self, table: str) -> list[dict]:
        """Merge a table's small data files, keeping every historical snapshot.

        Args:
            table: Table name, e.g. ``"sim_obitos"``.

        Returns:
            One dict per maintenance step DuckLake reports.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.optimize("sim_obitos")
        """
        from omnisus.lake.maintenance import run_maintenance

        return run_maintenance(self.connect(), alias=self._alias, operation="compact", table=table)

    def expire_snapshots(self, *, older_than: datetime, dry_run: bool = True) -> list[dict]:
        """Forget snapshots older than a cutoff; only simulates unless told otherwise.

        Expired snapshots can no longer be read or cited.

        Args:
            older_than: Timezone-aware ``datetime`` cutoff.
            dry_run: ``True`` (default) lists what would expire; ``False`` expires it.

        Returns:
            The snapshots expired, or that would be.

        Raises:
            ValueError: ``older_than`` has no timezone.

        Examples:
            >>> from datetime import UTC, datetime
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.expire_snapshots(older_than=datetime(2026, 1, 1, tzinfo=UTC))
        """
        from omnisus.lake.maintenance import run_maintenance

        return run_maintenance(
            self.connect(),
            alias=self._alias,
            operation="expire",
            older_than=older_than,
            dry_run=dry_run,
        )

    def cleanup_files(self, *, older_than: datetime, dry_run: bool = True) -> list[dict]:
        """Delete data files no snapshot needs, older than a cutoff; simulates by default.

        Args:
            older_than: Timezone-aware ``datetime`` cutoff.
            dry_run: ``True`` (default) lists the files; ``False`` deletes them.

        Returns:
            The files deleted, or that would be.

        Raises:
            ValueError: ``older_than`` has no timezone.

        Examples:
            >>> from datetime import UTC, datetime
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.cleanup_files(older_than=datetime(2026, 1, 1, tzinfo=UTC))
        """
        from omnisus.lake.maintenance import run_maintenance

        return run_maintenance(
            self.connect(),
            alias=self._alias,
            operation="cleanup",
            older_than=older_than,
            dry_run=dry_run,
        )

    def bootstrap_auxiliares(self) -> None:
        """Load the ``aux_*`` vocabularies (UF, municipalities, CID-10, CBO, countries).

        They come from the package's bootstrap zip, each file hashed in the source
        registry. Re-running replaces the tables' contents.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.bootstrap_auxiliares()
        """
        self.connect()

        import io
        import os
        import tempfile
        import zipfile
        from importlib.resources import files

        zip_bytes = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if not name.endswith(".parquet"):
                    continue
                table = name.removesuffix(".parquet")
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    tmp.write(zf.read(name))
                    tmp_path = tmp.name
                try:
                    self._con.execute(
                        f"CREATE OR REPLACE TABLE {qualified(self._alias, table)} AS "
                        f"SELECT * FROM read_parquet({quote_literal(tmp_path)})"
                    )
                finally:
                    os.unlink(tmp_path)

    def ensure_aux_cnes_view(self) -> bool:
        """Create or refresh ``aux_cnes``: one row per CNES establishment.

        Every import of ``cnes_estabelecimentos`` already calls this. The view joins
        the latest competência of ``cnes_estabelecimentos`` with ``cnes_master``
        names: ``cnes`` (7 digits), ``nome`` (NULL until
        :func:`~omnisus.import_cnes_master` runs), ``tp_unid``, ``codufmun`` and
        ``yyyymm_max``.

        Returns:
            ``False`` when ``cnes_estabelecimentos`` does not exist yet, else ``True``.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.ensure_aux_cnes_view()
            True
        """
        self.connect()
        tables = set(self.tables())
        if "cnes_estabelecimentos" not in tables:
            return False

        operational = qualified(self._alias, "cnes_estabelecimentos")
        view = qualified(self._alias, "aux_cnes")
        if "cnes_master" in tables:
            nome_select = "m.nome"
            join_clause = f"LEFT JOIN {qualified(self._alias, 'cnes_master')} m USING (cnes)"
        else:
            nome_select = "CAST(NULL AS VARCHAR) AS nome"
            join_clause = ""

        # Select all rows at the latest competence. Identical repeated imports
        # can collapse in this view; conflicting rows must never be picked by
        # incidental load order. The guard remains in the view for later inserts.
        latest_cte = f"""
            WITH ranked AS (
                SELECT cnes, tp_unid, codufmun, CAST(ano AS INTEGER) * 100 + CAST(mes AS INTEGER) AS yyyymm_max,
                       DENSE_RANK() OVER (PARTITION BY cnes ORDER BY ano DESC NULLS LAST, mes DESC NULLS LAST) AS rank
                FROM {operational} WHERE cnes IS NOT NULL
            ), latest AS (
                SELECT DISTINCT cnes, tp_unid, codufmun, yyyymm_max FROM ranked WHERE rank=1
            ), checked AS (
                SELECT *, COUNT(*) OVER (PARTITION BY cnes) AS variants FROM latest
            )
        """
        conflict = self._con.execute(
            latest_cte
            + "SELECT cnes FROM checked WHERE variants > 1 OR yyyymm_max IS NULL LIMIT 1"
        ).fetchone()
        if conflict:
            raise ValueError(
                "ambiguous or conflicting latest CNES rows; reconcile source versions before refreshing"
            )
        self._con.execute(f"""
            CREATE OR REPLACE VIEW {view} AS
            {latest_cte}
            SELECT CASE WHEN variants != 1 OR yyyymm_max IS NULL
                        THEN error('conflicting latest CNES rows') ELSE checked.cnes END AS cnes,
                   {nome_select}, checked.tp_unid, checked.codufmun, checked.yyyymm_max
            FROM checked {join_clause}
            WHERE CASE WHEN variants != 1 OR yyyymm_max IS NULL THEN error('conflicting latest CNES rows') ELSE true END
        """)
        return True

    def _staging_columns(self, staging: str) -> list[tuple[str, str]]:
        """(name, type) of the staging file, read from the Parquet footer."""
        return [
            (str(name), str(dtype))
            for name, dtype, *_ in self._con.execute(
                f"DESCRIBE SELECT * FROM read_parquet({quote_literal(str(staging))})"
            ).fetchall()
        ]

    def _table_columns(self, table: str) -> set[str]:
        if table not in self._columns:
            rows = self._con.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ?
                """,
                [self._alias, table],
            ).fetchall()
            self._columns[table] = {str(name) for (name,) in rows}
        return self._columns[table]

    def _ensure_table(self, table: str, staging: str, partition_by: tuple[str, ...]) -> None:
        """Create the table and set its partitioning, then keep its schema wide
        enough for what is being inserted.

        DATASUS changes its layouts between eras: SIM-DO goes 42 columns in
        1996, 45 in 2005, 61 in 2010, 90 in 2015 and 89 in 2020, adding *and*
        removing columns. A table created from whichever scope landed first
        therefore rejects most of the others, which is why a multi-year import
        could not build a lake at all. New columns are added as they appear;
        columns a given era lacks are left NULL by ``INSERT ... BY NAME``.
        """
        if table not in set(self.tables()):
            self._con.execute(
                f"CREATE TABLE {qualified(self._alias, table)} AS "
                f"SELECT * FROM read_parquet({quote_literal(str(staging))}) WHERE 1=0"
            )
            if partition_by:
                cols = ", ".join(quote_identifier(c) for c in partition_by)
                self._con.execute(
                    f"ALTER TABLE {qualified(self._alias, table)} SET PARTITIONED BY ({cols})"
                )
            self._columns.pop(table, None)
            self._ensured.add(table)
            return

        import pyarrow as pa
        import pyarrow.parquet as pq

        from omnisus.lake.schema import compatible_type

        known = self._table_columns(table)
        existing_types = dict(
            self._con.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ?",
                [self._alias, table],
            ).fetchall()
        )
        incoming = self._staging_columns(staging)
        null_fields = {f.name for f in pq.read_schema(staging) if pa.types.is_null(f.type)}
        promotions = []
        # Validate ALL shared columns before altering any of them.
        for name, dtype in incoming:
            if name in existing_types and name not in null_fields:
                target_type = compatible_type(existing_types[name], dtype)
                if target_type != existing_types[name]:
                    promotions.append((name, target_type))
        for name, dtype in promotions:
            self._con.execute(
                f"ALTER TABLE {qualified(self._alias, table)} ALTER COLUMN {quote_identifier(name)} SET TYPE {dtype}"
            )
        missing = [(n, t) for n, t in incoming if n not in known]
        for name, dtype in missing:
            self._con.execute(
                f"ALTER TABLE {qualified(self._alias, table)} ADD COLUMN {quote_identifier(name)} {dtype}"
            )
            known.add(name)
        if missing:
            logger.info(
                "lake.schema_widened",
                table=table,
                added=[n for n, _ in missing],
            )
        self._ensured.add(table)

    def ingest(
        self,
        table: str,
        lazyframe: pl.LazyFrame,
        *,
        partition_by: tuple[str, ...] = (),
    ) -> ImportResult:
        """Append a polars LazyFrame to a table, without a publication record.

        Outside :meth:`transaction` it commits before returning; inside, the result's
        ``snapshot_id`` stays ``None`` until the context commits.

        Args:
            table: Destination table, e.g. ``"minha_tabela"``.
            lazyframe: The rows to materialize and insert.
            partition_by: Partition columns, applied once when the table is created.

        Returns:
            Rows inserted, staging bytes and duration.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import polars as pl
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.ingest("minha_tabela", pl.LazyFrame({"x": [1, 2]}))
        """
        import tempfile
        import time
        from pathlib import Path

        self.connect()
        if not self.in_transaction:
            with self.transaction():
                return self.ingest(table, lazyframe, partition_by=partition_by)
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="omnisus-staging-") as tmp:
            staging = Path(tmp) / "data.parquet"
            lazyframe.sink_parquet(staging, row_group_size=1_000_000, compression="zstd")
            result = self.ingest_parquet(table, staging, partition_by=partition_by)
        result.duration_seconds = time.monotonic() - start
        return result

    def ingest_parquet(
        self, table: str, staging: str | Path, *, partition_by: tuple[str, ...] = ()
    ) -> ImportResult:
        """Append a validated Parquet staging file to a table, without rewriting it.

        Args:
            table: Destination table, e.g. ``"minha_tabela"``.
            staging: Path of the Parquet file.
            partition_by: Partition columns, applied once when the table is created.

        Returns:
            Rows inserted, the staging file's size and duration.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.ingest_parquet("minha_tabela", "staging.parquet")
        """
        import time
        from pathlib import Path

        from omnisus.sources._base import ImportResult

        self.connect()
        staging = Path(staging)
        if not self.in_transaction:
            with self.transaction():
                return self.ingest_parquet(table, staging, partition_by=partition_by)
        start = time.monotonic()
        self._ensure_table(table, str(staging), partition_by)
        inserted = self._con.execute(
            f"INSERT INTO {qualified(self._alias, table)} BY NAME SELECT * FROM read_parquet({quote_literal(str(staging))})"
        ).fetchone()
        result = ImportResult(
            rows=0 if inserted is None else int(inserted[0]),
            bytes_written=staging.stat().st_size,
            duration_seconds=time.monotonic() - start,
        )
        self._pending_results.append(result)
        return result

    def publish_scope(self, table: str, staging: Path, **kwargs: Any) -> ImportResult | None:
        """Publish one scope from a staging file, recording its source and policy.

        The low-level step :func:`~omnisus.import_dataset` runs per scope.

        Args:
            table: Dataset table, e.g. ``"sim_obitos"``.
            staging: Path of the validated Parquet staging file.
            **kwargs: ``scope``, ``source_sha256``, ``parser_version``, ``policy``,
                ``run_id``, ``source_uri`` and ``source_files``, as recorded in the
                publication.

        Returns:
            The result, or ``None`` when ``policy="skip_same"`` found the same source.

        Raises:
            ValueError: the staging file does not match the scope or the table.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.publish_scope("sim_obitos", "staging.parquet", scope=scope, ...)
        """
        from omnisus.lake.publication import publish_scope

        return publish_scope(self, table, staging, **kwargs)

    def delete_scope(self, table: str, scope: ScopeKey) -> DeletionResult:
        """Delete one scope's rows and retire its publications, in one transaction.

        Args:
            table: Dataset table, e.g. ``"sim_obitos"``.
            scope: The scope to delete, e.g. ``sus.ScopeKey("RR", 2023)``.

        Returns:
            Rows deleted and publications retired.

        Raises:
            ValueError: the table's national/state shape does not match ``scope``.

        Examples:
            >>> import omnisus as sus
            >>> with sus.Lake.local() as lake:  # doctest: +SKIP
            ...     lake.delete_scope("sim_obitos", sus.ScopeKey("RR", 2023))
        """
        from omnisus.lake.publication import delete_scope

        return delete_scope(self, table, scope)

    def close(self) -> None:
        """Close the connection and release the writer lock.

        Examples:
            >>> import omnisus as sus
            >>> lake = sus.Lake.local()  # doctest: +SKIP
            >>> lake.close()  # doctest: +SKIP
        """
        try:
            super().close()
        finally:
            self._writer_lock.close()
            self._columns.clear()
            self._ensured.clear()
