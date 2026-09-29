"""Sessions on a DuckLake catalog: the shared read surface and the read-only reader."""

from __future__ import annotations

from typing import Self

import duckdb

from omnisus.lake.catalog import parse_target, resolve_target
from omnisus.lake.connection import close_connection, make_reader_connection
from omnisus.lake.sql import quote_literal


class Session:
    """What every handle on a catalog can do: query, list, and close.

    Subclasses own how the connection is opened — :class:`Lake` for writing,
    under the writer lock; :class:`LakeReader` read-only — and hand it here.
    Raw SQL transaction control is outside this contract on either.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection, alias: str) -> None:
        self._con = con
        self._alias = alias
        self._closed = False
        self._unusable = False

    @property
    def alias(self) -> str:
        return self._alias

    @property
    def is_usable(self) -> bool:
        return not self._closed and not self._unusable

    def connect(self) -> duckdb.DuckDBPyConnection:
        """The DuckDB connection with the lake attached as :attr:`alias` (``"lake"``).

        Returns:
            A connection to run SQL on, e.g. ``SELECT * FROM lake.sim_obitos``.

        Raises:
            RuntimeError: the handle is closed, or unusable after a failed transaction.

        Examples:
            >>> import omnisus as sus
            >>> with sus.LakeReader() as lake:  # doctest: +SKIP
            ...     df = lake.connect().sql("SELECT count(*) FROM lake.sim_obitos").pl()
        """
        if self._closed:
            raise RuntimeError("handle is closed")
        if self._unusable:
            raise RuntimeError("Lake handle is unusable; close it and inspect the catalog")
        return self._con

    def tables(self) -> list[str]:
        """The lake's tables, without DuckLake's internal ones.

        Returns:
            Table names in alphabetical order, e.g. ``["aux_uf", "sim_obitos"]``.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.LakeReader() as lake:  # doctest: +SKIP
            ...     "sim_obitos" in lake.tables()
            True
        """
        self.connect()
        rows = self._con.execute(
            f"""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_catalog = {quote_literal(self._alias)}
            ORDER BY table_name
            """
        ).fetchall()
        return [name for (name,) in rows]

    def snapshots(self) -> list[dict[str, object]]:
        """The lake's snapshot history, oldest first.

        Snapshots are catalog-wide: ``changes`` names the tables each one touched.
        Pin a reader to one with ``LakeReader(snapshot_id=...)`` to reproduce a
        query.

        Returns:
            ``{"snapshot_id", "snapshot_time", "changes"}`` per snapshot; the time is
            text, since rendering DuckDB's TIMESTAMPTZ would need ``pytz``.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.LakeReader() as lake:  # doctest: +SKIP
            ...     latest = lake.snapshots()[-1]["snapshot_id"]
        """
        self.connect()
        rows = self._con.execute(
            f"""
            SELECT snapshot_id, snapshot_time::VARCHAR, changes::VARCHAR
            FROM ducklake_snapshots({quote_literal(self._alias)})
            ORDER BY snapshot_id
            """
        ).fetchall()
        return [
            {"snapshot_id": int(sid), "snapshot_time": when, "changes": changes}
            for sid, when, changes in rows
        ]

    def publications(self, *, run_id: str | None = None) -> list[dict]:
        """What was imported: one row per published scope, with its source files.

        Readable even after an import whose commit outcome was unknown, which is
        how such a run is reconciled.

        Args:
            run_id: Only this run's publications; ``None`` (default) returns all.

        Returns:
            Dicts with ``dataset``, ``scope`` (a :class:`~omnisus.ScopeKey`),
            ``active``, ``rows``, ``run_id``, ``release``, ``source_uri``,
            ``source_sha256`` and ``sources`` (every file with size and server time).

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.LakeReader() as lake:  # doctest: +SKIP
            ...     [p["scope"] for p in lake.publications() if p["dataset"] == "sim_obitos"]
            [ScopeKey(uf='RR', ano=2023, mes=None)]
        """
        from omnisus.lake.publication import publications

        return publications(self, run_id=run_id)

    def attempts(self, *, run_id: str | None = None) -> list[dict]:
        """Failed import attempts whose data was rolled back.

        Args:
            run_id: Only this run's attempts; ``None`` (default) returns all.

        Returns:
            One dict per recorded attempt.

        Raises:
            RuntimeError: the handle is closed or unusable.

        Examples:
            >>> import omnisus as sus
            >>> with sus.LakeReader() as lake:  # doctest: +SKIP
            ...     failed = lake.attempts(run_id="cap2")
        """
        from omnisus.lake.publication import attempts

        return attempts(self, run_id=run_id)

    def close(self) -> None:
        """Detach the lake and close the connection; closing twice is harmless.

        Examples:
            >>> import omnisus as sus
            >>> reader = sus.LakeReader()  # doctest: +SKIP
            >>> reader.close()  # doctest: +SKIP
        """
        if self._closed:
            return
        try:
            close_connection(self._con, self._alias)
        finally:
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class LakeReader(Session):
    """Read-only session on an existing lake.

    ``target`` uses the same grammar as :meth:`Lake.local` —
    ``ducklake:./omnisus.ducklake`` or ``ducklake:postgresql://…?storage=…`` —
    and the storage part is ignored: the catalog records its own data path.
    Nothing is created and no option is set, so a reader never takes the
    writer lock and never blocks a writer; DuckLake refuses writes on the
    connection itself. ``snapshot_id`` pins the session to one snapshot
    (``snapshots()[-1]["snapshot_id"]`` is the latest); without it every
    statement reads the latest committed snapshot.

    Raises :class:`~omnisus.lake.CatalogAttachError` when the catalog does
    not exist or the pinned snapshot is unknown.
    """

    snapshot_id: int | None
    """The pinned snapshot, or ``None`` for a session that reads the latest one."""

    def __init__(
        self, target: str | None = None, *, snapshot_id: int | None = None, alias: str = "lake"
    ) -> None:
        if snapshot_id is not None and (type(snapshot_id) is not int or snapshot_id < 0):
            raise ValueError("snapshot_id must be a non-negative integer")
        self.snapshot_id = snapshot_id
        catalog = parse_target(resolve_target(target))
        con = make_reader_connection(
            catalog_uri=catalog.catalog_uri, alias=alias, snapshot_id=snapshot_id
        )
        super().__init__(con, alias)
