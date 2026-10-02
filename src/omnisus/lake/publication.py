"""Transactional source publications; ordinary Lake.ingest remains append."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args
from uuid import uuid4

from omnisus.lake.sql import qualified, quote_identifier, quote_literal
from omnisus.sources._base import ScopeKey

if TYPE_CHECKING:
    from omnisus.lake import Lake
    from omnisus.lake.session import Session
    from omnisus.sources._base import ImportResult

ImportPolicy = Literal["append", "skip_same", "error_if_exists", "replace"]
POLICIES: tuple[str, ...] = get_args(ImportPolicy)
MANIFEST = "_omnisus_publications"
SOURCES = "_omnisus_sources"


@dataclass(frozen=True)
class SourceFile:
    """One downloaded file behind a publication, as the listing described it."""

    uri: str
    sha256: str
    size_bytes: int | None = None
    modified: str | None = None
    """Server mtime (``YYYY-MM-DDTHH:MM``, server clock), or ``None`` when unknown."""


def aggregate_sha256(files: Sequence[SourceFile]) -> str:
    """The publication digest: the file's own for one file, else over the ordered part digests."""
    if len(files) == 1:
        return files[0].sha256
    return hashlib.sha256(b"".join(bytes.fromhex(f.sha256) for f in files)).hexdigest()


def validate_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")


@dataclass(frozen=True)
class DeletionResult:
    """What :func:`delete_scope` removed: data rows, and the manifest rows retired with them."""

    rows_deleted: int
    publications_retired: int


def _validate_scope(scope: ScopeKey) -> None:
    if (
        (scope.uf is not None and not re.fullmatch("[A-Z]{2}", scope.uf))
        or not 1900 <= scope.ano <= 2200
        or (scope.mes is not None and not 1 <= scope.mes <= 12)
    ):
        raise ValueError("invalid source scope")


def _ensure_manifest(lake: "Lake") -> str:
    manifest = qualified(lake.alias, MANIFEST)
    lake.connect().execute(f"""CREATE TABLE IF NOT EXISTS {manifest} (
        publication_id VARCHAR, dataset VARCHAR, scope_json VARCHAR,
        source_sha256 VARCHAR, parser_version VARCHAR, run_id VARCHAR,
        batch_id VARCHAR, published_at VARCHAR, rows BIGINT,
        active BOOLEAN, managed BOOLEAN, source_uri VARCHAR
    )""")
    # Use live schema here: Lake's column cache is for data-table ingestion,
    # and an ALTER within a multi-scope transaction must be visible immediately.
    columns = {
        row[0] for row in lake.connect().execute(f"DESCRIBE SELECT * FROM {manifest}").fetchall()
    }
    if "source_uri" not in columns:
        lake.connect().execute(f"ALTER TABLE {manifest} ADD COLUMN source_uri VARCHAR")
    return manifest


def publications(session: "Session", *, run_id: str | None = None) -> list[dict]:
    if MANIFEST not in session.tables():
        return []
    sql = f"SELECT * FROM {qualified(session.alias, MANIFEST)}"
    args = []
    if run_id is not None:
        sql += " WHERE run_id = ?"
        args.append(run_id)
    rows = (
        session.connect()
        .execute(sql + " ORDER BY published_at, publication_id", args)
        .to_arrow_table()
        .to_pylist()
    )
    # Local import: the lake package stays registry-free at module import time.
    from omnisus.sources.datasus_ftp.datasets import release_from_uri

    for row in rows:
        dimensions = json.loads(row["scope_json"])
        row["scope"] = scope_from_fields(dimensions) if isinstance(dimensions, dict) else None
        row["release"] = release_from_uri(row["dataset"], row.get("source_uri"))
    by_publication: dict[str, list[dict]] = {}
    if SOURCES in session.tables():
        sources_sql = f"SELECT * FROM {qualified(session.alias, SOURCES)}"
        sources_args: list[object] = []
        if run_id is not None:
            sources_sql += (
                " WHERE publication_id IN "
                f"(SELECT publication_id FROM {qualified(session.alias, MANIFEST)} WHERE run_id = ?)"
            )
            sources_args.append(run_id)
        for source in (
            session.connect()
            .execute(sources_sql + " ORDER BY publication_id, ordinal", sources_args)
            .to_arrow_table()
            .to_pylist()
        ):
            by_publication.setdefault(source.pop("publication_id"), []).append(source)
    for row in rows:
        row["sources"] = by_publication.get(row["publication_id"]) or (
            [
                {
                    "ordinal": 0,
                    "source_uri": row["source_uri"],
                    "source_sha256": row["source_sha256"],
                    "source_bytes": None,
                    "source_modified": None,
                }
            ]
            if row.get("source_uri")
            else []
        )
    return rows


def scope_fields(scope: ScopeKey) -> dict[str, object]:
    """The columns that identify ``scope``'s rows: the manifest's scope_json shape."""
    if scope.uf is None:
        national: dict[str, object] = {"_source_ano": scope.ano}
        if scope.mes is not None:
            national["_source_mes"] = scope.mes
        return national
    fields: dict[str, object] = {"ano": scope.ano, "uf": scope.uf}
    if scope.mes is not None:
        fields["mes"] = scope.mes
    return fields


def scope_from_fields(fields: Mapping[str, object]) -> ScopeKey | None:
    """Inverse of :func:`scope_fields`; ``None`` for a shape this version never writes."""
    uf, mes = fields.get("uf"), fields.get("mes")
    national, national_mes = fields.get("_source_ano"), fields.get("_source_mes")
    if (
        set(fields) - {"_source_mes"} == {"_source_ano"}
        and isinstance(national, int)
        and (national_mes is None or isinstance(national_mes, int))
    ):
        return ScopeKey(uf=None, ano=national, mes=national_mes)
    ano = fields.get("ano")
    if (
        set(fields) - {"mes"} == {"ano", "uf"}
        and isinstance(ano, int)
        and isinstance(uf, str)
        and (mes is None or isinstance(mes, int))
    ):
        return ScopeKey(uf=uf, ano=ano, mes=mes)
    return None


def _predicate(fields: Mapping[str, object]) -> tuple[str, list[object]]:
    sql = " AND ".join(f"{quote_identifier(k)} IS NOT DISTINCT FROM ?" for k in fields)
    return sql, list(fields.values())


def scope_filter(scope: ScopeKey) -> tuple[str, list[object]]:
    """``WHERE`` condition and parameters that select ``scope``'s rows in a dataset table."""
    return _predicate(scope_fields(scope))


def unchanged_since_listing(
    lake: "Lake",
    table: str,
    scope: ScopeKey,
    *,
    parser_version: str,
    listed: Sequence[tuple[str, int, str]],
) -> bool:
    """Whether ``skip_same`` may skip ``scope`` before downloading it.

    True when the scope has one active publication with this parser version,
    it recorded exactly ``listed`` (URI, bytes, server time, in part order),
    and the table holds no other rows in the scope (so none unmanaged). Anything else,
    including a publication that recorded no size or time, is ``False``: the
    caller downloads and :func:`publish_scope` compares SHA-256.
    """
    if not {MANIFEST, SOURCES, table} <= set(lake.tables()):
        return False
    con = lake.connect()
    fields = scope_fields(scope)
    previous = con.execute(
        f"SELECT publication_id, parser_version, rows FROM {qualified(lake.alias, MANIFEST)} "
        "WHERE dataset=? AND scope_json=? AND active",
        [table, json.dumps(fields, sort_keys=True, separators=(",", ":"))],
    ).fetchall()
    if len(previous) != 1:
        return False
    ((publication_id, recorded_parser, rows),) = previous
    if recorded_parser != parser_version:
        return False
    recorded = con.execute(
        f"SELECT source_uri, source_bytes, source_modified FROM {qualified(lake.alias, SOURCES)} "
        "WHERE publication_id=? ORDER BY ordinal",
        [publication_id],
    ).fetchall()
    if [tuple(row) for row in recorded] != [tuple(file) for file in listed]:
        return False
    predicate, args = _predicate(fields)
    existing = con.execute(
        f"SELECT count(*) FROM {qualified(lake.alias, table)} WHERE {predicate}", args
    ).fetchone()
    assert existing is not None
    return existing[0] == rows


def publish_scope(
    lake: "Lake",
    table: str,
    staging: Path,
    *,
    scope: ScopeKey,
    source_sha256: str,
    parser_version: str,
    policy: ImportPolicy = "append",
    run_id: str | None = None,
    batch_id: str | None = None,
    partition_by: tuple[str, ...] = (),
    source_uri: str | None = None,
    source_files: Sequence[SourceFile] = (),
) -> "ImportResult | None":
    validate_policy(policy)
    if not re.fullmatch("[0-9a-f]{64}", source_sha256) or not parser_version:
        raise ValueError("publication requires source SHA-256 and parser version")
    _validate_scope(scope)
    if table.startswith("_omnisus_"):
        raise ValueError("reserved publication table name")
    files = tuple(source_files) or ((SourceFile(source_uri, source_sha256),) if source_uri else ())
    if source_files and (aggregate_sha256(files) != source_sha256 or files[0].uri != source_uri):
        raise ValueError("source files do not match the publication's SHA-256 and URI")
    staging = Path(staging)
    run_id, batch_id = run_id or str(uuid4()), batch_id or str(uuid4())
    if not lake.in_transaction:
        with lake.transaction():
            return publish_scope(
                lake,
                table,
                staging,
                scope=scope,
                source_sha256=source_sha256,
                parser_version=parser_version,
                policy=policy,
                run_id=run_id,
                batch_id=batch_id,
                partition_by=partition_by,
                source_uri=source_uri,
                source_files=source_files,
            )
    con = lake.connect()
    fields = scope_fields(scope)
    columns = dict(lake._staging_columns(str(staging)))
    if not fields.keys() <= columns.keys():
        raise ValueError("staging is missing source scope columns")
    predicate, args = _predicate(fields)
    counts = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE {predicate}) FROM read_parquet({quote_literal(str(staging))})",
        args,
    ).fetchone()
    assert counts is not None
    total, matching = counts
    if total == 0 or matching != total:
        raise ValueError("empty or inconsistent source scope; previous data preserved")
    scope_json = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    existing = 0
    if table in lake.tables():
        # Never let a wider national scope replace state publications or vice versa.
        national_table = "_source_ano" in lake._table_columns(table)
        if national_table != (scope.uf is None):
            raise ValueError("incompatible national/state publication scope")
        existing_row = con.execute(
            f"SELECT count(*) FROM {qualified(lake.alias, table)} WHERE {predicate}", args
        ).fetchone()
        assert existing_row is not None
        existing = existing_row[0]
    manifest = _ensure_manifest(lake)
    previous = con.execute(
        f"SELECT source_sha256, parser_version, rows, managed FROM {manifest} WHERE dataset=? AND scope_json=? AND active",
        [table, scope_json],
    ).fetchall()
    managed = sum(r[2] for r in previous) == existing and all(r[3] for r in previous)
    if policy != "append" and not managed:
        raise ValueError("legacy or unmanaged rows in scope; inventory/rebuild required")
    if existing and policy == "error_if_exists":
        raise ValueError("source scope already exists")
    if previous and policy == "skip_same":
        if all(r[0] == source_sha256 and r[1] == parser_version for r in previous):
            return None
        if all(r[0] == source_sha256 for r in previous):
            raise ValueError(
                "same file, imported by another parser version (another omnisus release "
                "or dictionary); request replace explicitly"
            )
        raise ValueError(
            "the server file differs from the one imported (DATASUS republished it); "
            "request replace explicitly"
        )
    # Schema compatibility is checked before deleting. All mutations and the
    # durable publication ID then share the caller's managed transaction.
    lake._ensure_table(table, str(staging), partition_by)
    if policy == "replace":
        con.execute(f"DELETE FROM {qualified(lake.alias, table)} WHERE {predicate}", args)
        con.execute(
            f"UPDATE {manifest} SET active=false WHERE dataset=? AND scope_json=? AND active",
            [table, scope_json],
        )
    result = lake.ingest_parquet(table, staging, partition_by=partition_by)
    publication_id = str(uuid4())
    con.execute(
        f"INSERT INTO {manifest} (publication_id, dataset, scope_json, source_sha256, "
        "parser_version, run_id, batch_id, published_at, rows, active, managed, source_uri) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            publication_id,
            table,
            scope_json,
            source_sha256,
            parser_version,
            run_id,
            batch_id,
            datetime.now(UTC).isoformat(),
            result.rows,
            True,
            managed,
            source_uri,
        ],
    )
    if files:
        sources = qualified(lake.alias, SOURCES)
        con.execute(f"""CREATE TABLE IF NOT EXISTS {sources} (
            publication_id VARCHAR, ordinal BIGINT, source_uri VARCHAR,
            source_sha256 VARCHAR, source_bytes BIGINT, source_modified VARCHAR
        )""")
        con.executemany(
            f"INSERT INTO {sources} VALUES (?, ?, ?, ?, ?, ?)",
            [
                (publication_id, i, f.uri, f.sha256, f.size_bytes, f.modified)
                for i, f in enumerate(files)
            ],
        )
    result.run_id, result.batch_id, result.publication_id = run_id, batch_id, publication_id
    return result


def delete_scope(lake: "Lake", table: str, scope: ScopeKey) -> DeletionResult:
    """Delete one source scope and retire every publication within it, atomically.

    Rows are matched by the predicate :func:`publish_scope` uses, so a yearly
    scope on a monthly table removes all its months, and each month's manifest
    row is retired (``active = false``). Rows that never had a manifest are
    deleted as well; ``rows_deleted`` above the retired publications' row sum
    is the caller's signal that unmanaged rows were present. Runs inside the
    caller's managed transaction when one is active, else opens one.
    """
    _validate_scope(scope)
    if table.startswith("_omnisus_"):
        raise ValueError("reserved publication table name")
    if not lake.in_transaction:
        with lake.transaction():
            return delete_scope(lake, table, scope)
    if table not in lake.tables():
        raise ValueError(f"unknown table: {table!r}")
    national_table = "_source_ano" in lake._table_columns(table)
    if national_table != (scope.uf is None):
        raise ValueError("incompatible national/state publication scope")
    con = lake.connect()
    fields = scope_fields(scope)
    predicate, args = _predicate(fields)
    data = qualified(lake.alias, table)
    counted = con.execute(f"SELECT count(*) FROM {data} WHERE {predicate}", args).fetchone()
    assert counted is not None
    con.execute(f"DELETE FROM {data} WHERE {predicate}", args)
    retired = 0
    if MANIFEST in lake.tables():
        manifest = qualified(lake.alias, MANIFEST)
        active = con.execute(
            f"SELECT publication_id, scope_json FROM {manifest} WHERE dataset = ? AND active",
            [table],
        ).fetchall()
        within = [
            publication_id
            for publication_id, scope_json in active
            if _contains(json.loads(scope_json), fields)
        ]
        for publication_id in within:
            con.execute(
                f"UPDATE {manifest} SET active = false WHERE publication_id = ?", [publication_id]
            )
        retired = len(within)
    return DeletionResult(rows_deleted=int(counted[0]), publications_retired=retired)


def _contains(dimensions: object, fields: Mapping[str, object]) -> bool:
    """Whether a manifest row's scope lies within the requested fields."""
    return isinstance(dimensions, dict) and all(dimensions.get(k) == v for k, v in fields.items())


def record_failed_attempts(lake: "Lake", report) -> None:
    """Persist determined failures after data batches have rolled back."""
    if not report.failed:
        return
    table = qualified(lake.alias, "_omnisus_attempts")
    with lake.transaction():
        lake.connect().execute(f"""CREATE TABLE IF NOT EXISTS {table} (
            run_id VARCHAR, input_index BIGINT, scope VARCHAR, status VARCHAR,
            reason VARCHAR, recorded_at VARCHAR
        )""")
        rows = [
            (
                report.run_id,
                index,
                str(outcome.scope),
                outcome.status,
                outcome.reason,
                datetime.now(UTC).isoformat(),
            )
            for index, outcome in enumerate(report.outcomes)
            if outcome.status == "failed"
        ]
        lake.connect().executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)", rows)


def attempts(session: "Session", *, run_id: str | None = None) -> list[dict]:
    if "_omnisus_attempts" not in session.tables():
        return []
    sql = f"SELECT * FROM {qualified(session.alias, '_omnisus_attempts')}"
    params = []
    if run_id is not None:
        sql += " WHERE run_id=?"
        params.append(run_id)
    return (
        session.connect()
        .execute(sql + " ORDER BY recorded_at, input_index", params)
        .to_arrow_table()
        .to_pylist()
    )
