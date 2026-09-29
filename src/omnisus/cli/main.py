"""omnisus CLI entry point (Typer + Rich)."""

from __future__ import annotations

from collections.abc import Callable

import typer
from rich.console import Console

from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, Dataset, resolve

app = typer.Typer(
    name="omnisus",
    help="Brazilian public health database ingestion lib.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_NON_FTP: dict[str, str] = {"ibge_populacao": "ibge_populacao"}
"""CLI names of datasets that are not DATASUS-FTP rows, mapped to
their dataset name. Dispatch (in ``import_cmd``) looks up the importer for
that dataset name in a second, importer-keyed mapping built inside the
command body — a mapping entry with no importer raises ``KeyError`` loudly
rather than silently importing the wrong dataset."""


_PLANNERS: frozenset[str] = frozenset({"product", "inventory"})
"""How ``import`` chooses scopes. ``product`` is every (uf, year[, month]) and
leans on tolerance to absorb the gaps; ``inventory`` asks the server what it
publishes and imports only that. The library has no such flag — planning there
is composition; this is CLI sugar over the same two functions."""


def dataset_choices() -> list[str]:
    """Every name ``omnisus import`` accepts — derived, never listed by hand."""
    return sorted({*REGISTRY, *_NON_FTP})


def ftp_dataset_choices() -> list[str]:
    """Every name ``omnisus inventory`` accepts.

    A subset of :func:`dataset_choices`: the inventory reads the DATASUS FTP
    server, so datasets that do not come from it (``_NON_FTP``) have nothing
    to list. Offering a name the command then rejects is a declaration that
    lies.
    """
    return sorted(REGISTRY)


@app.command()
def init(
    target: str | None = typer.Option(
        None,
        "--target",
        "-t",
        help="DuckLake target (default: data/raw/omnisus.ducklake, or $OMNISUS_DATA_DIR)",
    ),
) -> None:
    """Initialize a new lake and load auxiliary tables."""
    console.print("[bold]Initializing[/bold] lake")
    with Lake.local(target) as lake:
        lake.bootstrap_auxiliares()
        tables = lake.tables()
    console.print(f"[green]:heavy_check_mark:[/green] {len(tables)} table(s): {', '.join(tables)}")


@app.command(name="import")
def import_cmd(
    dataset: str = typer.Argument(..., help=f"One of: {', '.join(dataset_choices())}"),
    year: list[int] | None = typer.Option(
        None, "--year", "-y", help="Repeatable; e.g. -y 2023 -y 2024"
    ),
    years_range: str | None = typer.Option(None, "--years", help="e.g. 2020-2024"),
    ufs: str | None = typer.Option(None, "--ufs", help="Comma list: SP,RJ,MG"),
    months: str | None = typer.Option(None, "--months", help="Comma list, monthly only"),
    plan: str = typer.Option(
        "product",
        "--plan",
        help=(
            "How to choose scopes: 'product' (every uf x year, tolerating gaps) "
            "or 'inventory' (ask the server first, import only what exists)."
        ),
    ),
    census: bool | None = typer.Option(
        None,
        "--census/--estimate",
        help="IBGE only, required: the census edition or the year's latest estimate",
    ),
    policy: str = typer.Option(
        "append", "--policy", help="FTP: append, skip_same, error_if_exists, replace"
    ),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Durable FTP operation identity for reconciliation"
    ),
    max_payload_bytes: int = typer.Option(512 * 1024 * 1024, "--max-payload-bytes"),
    max_inflight_bytes: int = typer.Option(1024 * 1024 * 1024, "--max-inflight-bytes"),
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Import a dataset into the lake.

    For FTP imports, exits 1 when a completed report contains failed scopes
    or when ImportAbortedError interrupts the run. Skipped scopes alone do not
    fail the run. Invalid arguments and other exceptions can also exit non-zero.
    """
    from typing import cast

    import omnisus as sus
    from omnisus.lake.publication import ImportPolicy, validate_policy

    validate_policy(policy)
    import_policy = cast(ImportPolicy, policy)

    non_ftp_importers: dict[str, Callable[..., list[sus.ImportResult]]] = {
        "ibge_populacao": lambda **kw: sus.import_ibge_populacao(**kw),
    }

    # Resolve years
    if years_range:
        a, b = years_range.split("-")
        yrs: list[int] = list(range(int(a), int(b) + 1))
    elif year:
        yrs = list(year)
    else:
        raise typer.BadParameter("provide --year/-y or --years RANGE")

    if plan not in _PLANNERS:
        raise typer.BadParameter(f"--plan must be one of: {', '.join(sorted(_PLANNERS))}")

    uf_list = [u.strip().upper() for u in ufs.split(",")] if ufs else None
    month_list = [int(x) for x in months.split(",")] if months else None

    if dataset in _NON_FTP:
        name = _NON_FTP[dataset]
        importer = non_ftp_importers[name]
        if policy != "append" or run_id is not None:
            raise typer.BadParameter(
                "--policy and --run-id are FTP-only; IBGE publications retain their own provenance"
            )
        if census is None:
            raise typer.BadParameter("IBGE population needs --census or --estimate")
        results = importer(years=yrs, census=census, target=target)
        total_rows = sum(r.rows for r in results)
        console.print(
            f"[green]:heavy_check_mark:[/green] imported [bold]{total_rows:,}[/bold] rows "
            f"({len(results)} scope(s))"
        )
        return

    try:
        d = resolve(dataset)
    except ValueError as exc:
        raise typer.BadParameter(f"{exc}. Choose from: {', '.join(dataset_choices())}") from exc

    scopes = _plan_scopes(d, plan=plan, years=yrs, ufs=uf_list, months=month_list)

    try:
        report = sus.import_dataset(
            d,
            scopes=scopes,
            target=target,
            policy=import_policy,
            run_id=run_id,
            max_payload_bytes=max_payload_bytes,
            max_inflight_bytes=max_inflight_bytes,
        )
    except sus.ImportAbortedError as exc:
        console.print(
            "[red]import interrupted[/red]: "
            f"{exc.report.rows:,} confirmed rows, "
            f"{len(exc.report.failed)} failed, "
            f"{len(exc.unresolved)} unresolved; inspect before retry",
        )
        raise typer.Exit(1) from exc

    marker = "[red]failed[/red]" if report.failed else "[green]:heavy_check_mark:[/green]"
    console.print(
        f"{marker} imported [bold]{report.rows:,}[/bold] rows "
        f"({len(report.ok)} ok, {len(report.skipped)} skipped, {len(report.failed)} failed)"
    )
    by_code: dict[str, list[str]] = {}
    for outcome in report.skipped:
        by_code.setdefault(outcome.code or "skipped", []).append(str(outcome.scope))
    for code, names in by_code.items():
        shown = ", ".join(names[:10])
        more = f" … and {len(names) - 10} more" if len(names) > 10 else ""
        console.print(f"  skipped {len(names)} {code}: {shown}{more}")
    if report.failed:
        for outcome in report.failed[:10]:
            console.print(f"  [red]x[/red] {outcome.scope}: {outcome.reason}")
        if len(report.failed) > 10:
            console.print(f"  [dim]... and {len(report.failed) - 10} more[/dim]")
        raise typer.Exit(code=1)


def _plan_scopes(
    d: Dataset,
    *,
    plan: str,
    years: list[int],
    ufs: list[str] | None,
    months: list[int] | None,
) -> list[ScopeKey]:
    """Fill the scope list with the chosen planner, then apply the user's filters.

    ``--plan inventory`` forces ``refresh=True``: the 24h listing cache exists
    for interactive browsing, and a 23-hour-old listing would silently omit a
    month DATASUS published this morning. The run is about to use the network
    anyway, so the listing costs one extra LIST and removes that whole class of
    silent omission.
    """
    import omnisus as sus

    if d.geography == "national" and (ufs is not None or months is not None):
        raise ValueError("national yearly datasets do not accept UF/month filters")
    if plan == "product":
        return sus.scopes_for(d, years=years, ufs=ufs, months=months)

    return sus.available(d, years=years, ufs=ufs, months=months, refresh=True)


@app.command()
def inventory(
    dataset: str | None = typer.Argument(
        None, help=f"One of: {', '.join(ftp_dataset_choices())}. Omit when using --path."
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Browse any FTP path instead (e.g. /dissemin/publicos/SINAN)"
    ),
    depth: int = typer.Option(1, "--depth", "-d", help="Recursion depth for --path (1-4)"),
    refresh: bool = typer.Option(False, "--refresh", help="Bypass the 24h listing cache"),
) -> None:
    """Show what DATASUS actually publishes, from a cached FTP listing."""
    from rich.table import Table as RichTable

    import omnisus as sus
    from omnisus.sources.datasus_ftp.datasets import resolve
    from omnisus.sources.datasus_ftp.inventory import FtpPathNotFound, FtpUnavailable

    if (dataset is None) == (path is None):
        raise typer.BadParameter("provide exactly one of DATASET or --path")
    if path is not None and not 1 <= depth <= 4:
        raise typer.BadParameter("--depth must be between 1 and 4")

    try:
        if path is not None:
            entries = sus.browse(path, depth=depth, refresh=refresh)
            table = RichTable("Name", "Type", "Size", "Modified")
            for e in entries:
                table.add_row(
                    e.name,
                    "dir" if e.is_dir else "file",
                    "" if e.is_dir else f"{e.size_bytes:,}",
                    e.modified.strftime("%Y-%m-%d %H:%M"),
                )
            console.print(table)
            console.print(f"[dim]{len(entries)} entry(ies) under {path}[/dim]")
            return
        assert dataset is not None, "the XOR check above guarantees this"
        try:
            d = resolve(dataset)
        except ValueError as exc:
            raise typer.BadParameter(
                f"{exc}. Choose from: {', '.join(ftp_dataset_choices())}"
            ) from exc
        releases = sus.available_releases(d, refresh=refresh)
        table = RichTable("UF", "Ano", "Mês", "Release")
        for s, release in releases.items():
            table.add_row(
                s.uf or "Nacional", str(s.ano), "" if s.mes is None else f"{s.mes:02d}", release
            )
        console.print(table)
        console.print(f"[dim]{len(releases)} scope(s) available for {d.name}[/dim]")
    except FtpPathNotFound as exc:
        console.print(f"[red]x[/red] not found on the server: {exc}")
        raise typer.Exit(code=1) from exc
    except FtpUnavailable as exc:
        console.print(f"[red]x[/red] DATASUS FTP unreachable: {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def query(
    sql: str = typer.Argument(..., help="SQL to run against the lake"),
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Run an ad-hoc SQL query."""
    from rich.table import Table

    with Lake.local(target) as lake:
        rel = lake.connect().sql(sql)
        cols = list(rel.columns)
        rows = rel.fetchall()

    table = Table(*cols)
    for row in rows[:200]:
        table.add_row(*[str(v) for v in row])
    console.print(table)
    if len(rows) > 200:
        console.print(f"... ({len(rows)} rows total, showing first 200)")


lake_app = typer.Typer(name="lake", help="Lake operations.")
app.add_typer(lake_app)


@lake_app.command(name="tables")
def lake_tables_cmd(
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """List user tables in the lake."""
    with Lake.local(target) as lake:
        for t in lake.tables():
            console.print(f"  {t}")


@lake_app.command(name="describe")
def lake_describe_cmd(
    table: str,
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Describe a lake table (columns + types)."""
    from rich.table import Table as RichTable

    with Lake.local(target) as lake:
        cols = lake.connect().execute(f"DESCRIBE lake.{table}").fetchall()
    rt = RichTable("Column", "Type")
    for c in cols:
        rt.add_row(str(c[0]), str(c[1]))
    console.print(rt)


@lake_app.command(name="snapshots")
def lake_snapshots_cmd(
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """List the lake's snapshot history.

    Snapshots are catalog-wide in DuckLake, not per-table; the ``changes``
    column names the tables each one touched. This command previously took a
    table name and always failed, because ``ducklake_snapshots('lake.<table>')``
    does not bind.
    """
    from rich.table import Table as RichTable

    with Lake.local(target) as lake:
        snaps = lake.snapshots()
    rt = RichTable("Snapshot", "Time", "Changes")
    for snap in snaps:
        rt.add_row(str(snap["snapshot_id"]), str(snap["snapshot_time"]), str(snap["changes"]))
    console.print(rt)
    console.print(f"[dim]{len(snaps)} snapshot(s)[/dim]")


@lake_app.command(name="optimize")
def lake_optimize_cmd(
    table: str,
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Compact small Parquet files for a table."""
    with Lake.local(target) as lake:
        try:
            lake.optimize(table)
        except Exception as exc:
            console.print(f"[red]optimize failed:[/red] {exc}")
            raise typer.Exit(1) from exc
    console.print(f"[green]:heavy_check_mark:[/green] optimized {table}")


@lake_app.command(name="update-auxiliares")
def lake_update_aux_cmd(
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Refresh aux_* tables from the bundled auxiliares-bootstrap.zip."""
    with Lake.local(target) as lake:
        lake.bootstrap_auxiliares()
    console.print("[green]:heavy_check_mark:[/green] aux tables refreshed")


@app.command()
def doctor() -> None:
    """Print diagnostic info (versions, env)."""
    import duckdb
    import polars as pl
    import pyarrow as pa

    from omnisus._version import __version__ as v

    console.print(f"omnisus: {v}")
    console.print(f"DuckDB:     {duckdb.__version__}")
    console.print(f"Polars:     {pl.__version__}")
    console.print(f"PyArrow:    {pa.__version__}")

    try:
        con = duckdb.connect()
        con.execute("INSTALL ducklake; LOAD ducklake;")
        console.print("[green]:heavy_check_mark:[/green] ducklake extension OK")
    except Exception as exc:
        console.print(f"[red]x[/red] ducklake load failed: {exc}")


def _maintenance_command(operation: str, before: str, dry_run: bool, target: str | None) -> None:
    from datetime import datetime

    try:
        cutoff = datetime.fromisoformat(before)
        with Lake.local(target) as lake:
            method = lake.expire_snapshots if operation == "expire" else lake.cleanup_files
            results = method(older_than=cutoff, dry_run=dry_run)
    except Exception as exc:
        console.print(f"[red]Maintenance failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    label = "simulation" if dry_run else "executed"
    console.print(f"{operation}: {label}, {len(results)} result(s)")


@lake_app.command(name="expire-snapshots")
def lake_expire_snapshots_cmd(
    before: str = typer.Option(..., "--before", help="ISO datetime with timezone; history cutoff"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Expire historical snapshots. Simulates unless --execute is supplied."""
    _maintenance_command("expire", before, dry_run, target)


@lake_app.command(name="cleanup-files")
def lake_cleanup_files_cmd(
    before: str = typer.Option(
        ..., "--before", help="ISO datetime with timezone; obsolete-file cutoff"
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
    target: str | None = typer.Option(None, "--target", "-t"),
) -> None:
    """Remove obsolete files. Simulates unless --execute is supplied."""
    _maintenance_command("cleanup", before, dry_run, target)


if __name__ == "__main__":
    app()
