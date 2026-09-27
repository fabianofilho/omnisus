"""Tests for the omnisus CLI entry point."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import respx
from typer.testing import CliRunner

from omnisus.cli.main import app
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

runner = CliRunner()


def test_app_help_lists_top_level_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for verb in ("init", "import", "query", "lake", "doctor"):
        assert verb in result.stdout


def test_init_does_not_echo_connection_credentials(monkeypatch) -> None:
    class UnavailableLake:
        @staticmethod
        def local(target):
            raise ValueError("controlled connection failure")

    monkeypatch.setattr("omnisus.cli.main.Lake", UnavailableLake)
    result = runner.invoke(
        app,
        ["init", "--target", "ducklake:postgresql://user:secret@host/db?storage=s3://bucket"],
    )
    assert result.exit_code != 0
    assert "secret" not in result.output


def test_init_creates_lake_and_loads_auxiliares(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/omnisus.ducklake"
    result = runner.invoke(app, ["init", "--target", target])

    assert result.exit_code == 0, result.stdout

    from omnisus.lake import Lake

    lake = Lake.local(target)
    tables = set(lake.tables())
    assert {"aux_uf", "aux_municipios", "aux_cid10"} <= tables
    lake.close()


def test_init_default_target_is_data_raw_under_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMNISUS_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "data/raw/omnisus.ducklake").exists()


def test_import_sim_via_cli(monkeypatch, tmp_path, dbc_fixture) -> None:
    fixture_bytes = dbc_fixture("sim_rr_2023_mini").read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): fixture_bytes})

    target = f"ducklake:{tmp_path}/cli.ducklake"
    result = runner.invoke(
        app,
        ["import", "sim_obitos", "--year", "2023", "--ufs", "RR", "--target", target],
    )
    assert result.exit_code == 0, result.stdout

    from omnisus.lake import Lake

    lake = Lake.local(target)
    n = lake.connect().execute("SELECT count(*) FROM lake.sim_obitos").fetchone()[0]
    assert n > 0
    lake.close()


def test_import_requires_year_or_years() -> None:
    """Missing --year/--years should fail with a clear error."""
    result = runner.invoke(app, ["import", "sim_obitos"])
    assert result.exit_code != 0
    assert "year" in result.output.lower()


def test_query_runs_sql(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/q.ducklake"
    runner.invoke(app, ["init", "--target", target])
    result = runner.invoke(
        app,
        ["query", "SELECT count(*) FROM lake.aux_uf", "--target", target],
    )
    assert result.exit_code == 0, result.stdout
    assert "27" in result.stdout


def test_lake_tables_lists_aux(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/t.ducklake"
    runner.invoke(app, ["init", "--target", target])
    result = runner.invoke(app, ["lake", "tables", "--target", target])
    assert result.exit_code == 0
    assert "aux_uf" in result.stdout


def test_doctor_reports_environment() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "DuckDB" in result.stdout
    assert "Polars" in result.stdout


def test_lake_describe_shows_columns(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/d.ducklake"
    runner.invoke(app, ["init", "--target", target])
    result = runner.invoke(
        app,
        ["lake", "describe", "aux_uf", "--target", target],
    )
    assert result.exit_code == 0
    assert "codigo_ibge" in result.stdout


def test_lake_optimize_runs(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/o.ducklake"
    runner.invoke(app, ["init", "--target", target])
    result = runner.invoke(
        app,
        ["lake", "optimize", "aux_uf", "--target", target],
    )
    # Optimize may print output; just confirm no crash
    assert result.exit_code == 0


def test_lake_update_auxiliares(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/u.ducklake"
    runner.invoke(app, ["init", "--target", target])
    result = runner.invoke(
        app,
        ["lake", "update-auxiliares", "--target", target],
    )
    assert result.exit_code == 0


def test_import_sia_bpa_individualizado_via_cli(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    """The CLI must reach every registry row, not a hand-maintained subset."""
    fixture_bytes = dbc_fixture("sia_bi_rr_2024_01_mini").read_bytes()
    fake_datasus.serve(
        monkeypatch, "sia_bpa_individualizado", {ScopeKey(uf="RR", ano=2024, mes=1): fixture_bytes}
    )

    target = f"ducklake:{tmp_path}/sia.ducklake"
    result = runner.invoke(
        app,
        [
            "import",
            "sia_bpa_individualizado",
            "--year",
            "2024",
            "--months",
            "1",
            "--ufs",
            "RR",
            "--target",
            target,
        ],
    )
    assert result.exit_code == 0, result.output

    from omnisus.lake import Lake

    with Lake.local(target) as lake:
        assert "sia_bpa_individualizado" in lake.tables()


def test_import_unknown_dataset_lists_the_choices() -> None:
    result = runner.invoke(app, ["import", "bogus", "--year", "2024"])
    assert result.exit_code != 0
    assert "unknown dataset" in result.output
    assert "sia_bpa_individualizado" in result.output


def test_import_help_lists_registry_names() -> None:
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    for name in (
        "sim_obitos",
        "sia_apac_tratamento_dialitico",
        "cnes_estabelecimentos",
        "ibge_populacao",
    ):
        assert name in result.output


def test_dataset_choices_cover_registry_and_non_ftp() -> None:
    import omnisus.cli.main as cli_main
    from omnisus.cli.main import dataset_choices
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    choices = set(dataset_choices())
    assert choices == set(REGISTRY) | set(cli_main._NON_FTP)
    assert "ibge_populacao" in choices


def test_import_dispatch_fails_loudly_on_non_ftp_entry_without_importer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``_NON_FTP`` entry with no matching importer must raise, never
    silently mis-route to another dataset's importer."""
    import omnisus.cli.main as cli_main

    monkeypatch.setitem(cli_main._NON_FTP, "bogus-nonftp", "bogus")

    result = runner.invoke(app, ["import", "bogus-nonftp", "--year", "2024"])
    assert result.exit_code != 0
    assert "imported" not in result.output


# --- import: planning and exit status -------------------------------------


def test_a_skipped_scope_exits_zero(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    """Asking for a range DATASUS only partly published is normal, not an error.
    An orchestrator must be able to tell 'nothing to do' from 'something broke'.
    The server lists 2023 only."""
    fake_datasus.serve(
        monkeypatch,
        "sim_obitos",
        {ScopeKey(uf="RR", ano=2023): dbc_fixture("sim_rr_2023_mini").read_bytes()},
    )
    result = runner.invoke(
        app,
        [
            "import",
            "sim_obitos",
            "--years",
            "2022-2023",
            "--ufs",
            "RR",
            "--target",
            f"ducklake:{tmp_path}/s.ducklake",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "1 skipped" in result.output


def test_a_failed_scope_exits_one(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    """A 530 exhausting its retries is a real failure and must be visible to
    the caller's exit status, not buried in a summary line. The file is
    listed; the real fetcher runs over the patched synchronous seam."""
    import ftplib

    from omnisus.sources.datasus_ftp import fetch

    def _throttled(*_a: object) -> bytes:
        raise ftplib.error_perm("530 maximum number of allowed clients")

    fake_datasus.serve(
        monkeypatch,
        "sim_obitos",
        {ScopeKey(uf="RR", ano=2023): dbc_fixture("sim_rr_2023_mini").read_bytes()},
    )
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", fetch.fetch_dbc_bytes
    )
    monkeypatch.setattr("omnisus.sources.datasus_ftp.fetch._blocking_fetch", _throttled)
    result = runner.invoke(
        app,
        [
            "import",
            "sim_obitos",
            "--year",
            "2023",
            "--ufs",
            "RR",
            "--target",
            f"ducklake:{tmp_path}/f.ducklake",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "1 failed" in result.output


def test_import_invalid_dbc_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): b"invalid dbc"})
    result = runner.invoke(
        app,
        [
            "import",
            "sim_obitos",
            "--year",
            "2023",
            "--ufs",
            "RR",
            "--target",
            f"ducklake:{tmp_path}/bad.ducklake",
        ],
    )
    assert result.exit_code == 1
    assert "1 failed" in result.stdout
    assert "0 rows" in result.stdout


@pytest.mark.parametrize("width", [None, 40, 80])
def test_import_abort_prints_partial_progress(monkeypatch, tmp_path: Path, width) -> None:
    from rich.console import Console

    if width is not None:
        monkeypatch.setattr("omnisus.cli.main.console", Console(width=width))
    import omnisus as sus

    def abort(*args: object, **kwargs: object) -> None:
        report = sus.ImportReport(outcomes=())
        unresolved = ((0, sus.ScopeKey(uf="RR", ano=2023)),)
        raise sus.ImportAbortedError(report, unresolved)

    monkeypatch.setattr(sus, "import_dataset", abort)
    result = runner.invoke(
        app,
        [
            "import",
            "sim_obitos",
            "--year",
            "2023",
            "--ufs",
            "RR",
            "--target",
            f"ducklake:{tmp_path}/partial.ducklake",
        ],
    )
    assert result.exit_code == 1
    output = " ".join(result.stdout.split())
    assert "import interrupted" in output
    assert "0 confirmed rows" in output
    assert "0 failed" in output
    assert "1 unresolved" in output
    assert "inspect before retry" in output
    assert "imported" not in result.stdout


def test_plan_inventory_imports_only_what_the_server_lists(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """The goal: build the lake from what is actually published. The server
    lists 2023 only, so 2022 is never even attempted."""
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))
    sim_prelim_dir = REGISTRY["sim_obitos"].prelim_dir
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()

    def _list(path: str, _t: float) -> list[str]:
        if path == sim_prelim_dir:
            return []
        return [f"12-19-24  11:56AM {len(raw):>20} DORR2023.dbc"]

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", _list)
    fetched: list[str] = []

    def _blocking(_remote_dir: str, filename: str, _timeout: float) -> bytes:
        fetched.append(filename)
        return raw

    monkeypatch.setattr("omnisus.sources.datasus_ftp.fetch._blocking_fetch", _blocking)

    result = runner.invoke(
        app,
        [
            "import",
            "sim_obitos",
            "--years",
            "2022-2023",
            "--ufs",
            "RR",
            "--plan",
            "inventory",
            "--target",
            f"ducklake:{tmp_path}/p.ducklake",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fetched == ["DORR2023.dbc"], "2022 was not listed, so it must not be fetched"


def test_plan_inventory_bypasses_a_stale_listing_cache(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    """--plan implies refresh=True. A 23-hour-old cache would silently omit a
    month published this morning, and the run is about to use the network anyway."""
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))
    sim_prelim_dir = REGISTRY["sim_obitos"].prelim_dir
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    listings = 0

    def _list(path: str, _t: float) -> list[str]:
        nonlocal listings
        if path == sim_prelim_dir:
            return []
        listings += 1
        return [f"12-19-24  11:56AM {len(raw):>20} DORR2023.dbc"]

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", _list)
    monkeypatch.setattr("omnisus.sources.datasus_ftp.fetch._blocking_fetch", lambda *_a: raw)
    argv = [
        "import",
        "sim_obitos",
        "--year",
        "2023",
        "--ufs",
        "RR",
        "--plan",
        "inventory",
        "--target",
        f"ducklake:{tmp_path}/r.ducklake",
    ]

    assert runner.invoke(app, argv).exit_code == 0
    assert listings == 2, "the plan and the import each list afresh"
    assert runner.invoke(app, argv).exit_code == 0
    assert listings == 4, "the second run must re-list, not trust the 24h cache"


def test_an_unknown_plan_is_rejected() -> None:
    result = runner.invoke(app, ["import", "sim_obitos", "--year", "2023", "--plan", "bogus"])
    assert result.exit_code != 0
    assert "inventory" in result.output and "product" in result.output


def test_explicit_maintenance_dry_run_and_cli_failures(tmp_path):
    target = f"ducklake:{tmp_path}/maintenance.ducklake"
    runner.invoke(app, ["init", "--target", target])
    for operation in ("expire-snapshots", "cleanup-files"):
        result = runner.invoke(
            app, ["lake", operation, "--before", "2000-01-01T00:00:00+00:00", "--target", target]
        )
        assert result.exit_code == 0, result.output
        assert "simulation" in result.output.lower()
        invalid = runner.invoke(
            app, ["lake", operation, "--before", "2000-01-01", "--target", target]
        )
        assert invalid.exit_code != 0


def test_module_entrypoint_registers_maintenance_commands():
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONPATH="src")
    result = subprocess.run(
        [sys.executable, "-m", "omnisus.cli.main", "lake", "expire-snapshots", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_import_prints_skipped_scopes_grouped_by_code(monkeypatch, tmp_path) -> None:
    raw = (
        Path(__file__).resolve().parents[2] / "fixtures" / "dbc" / "sim_rr_2023_mini.dbc"
    ).read_bytes()
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): raw})
    target = f"ducklake:{tmp_path}/grouped.ducklake"
    result = runner.invoke(
        app,
        ["import", "sim_obitos", "--year", "2023", "--ufs", "RR,AC", "--target", target],
    )
    assert result.exit_code == 0, result.stdout
    assert "skipped 1 not_listed: AC_2023" in result.output


@respx.mock
def test_import_ibge_census_via_cli(tmp_path: Path) -> None:
    """Real IBGE 4714 responses; the CLI names the edition like the Python API."""
    from tests.integration.test_ibge_pop_e2e import mock_source

    mock_source()
    target = f"ducklake:{tmp_path}/x.ducklake"

    result = runner.invoke(
        app, ["import", "ibge_populacao", "--year", "2022", "--census", "--target", target]
    )

    assert result.exit_code == 0, result.output
    assert "imported 2 rows" in result.output


def test_import_ibge_requires_census_or_estimate(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["import", "ibge_populacao", "--year", "2022", "--target", f"ducklake:{tmp_path}/x"]
    )

    assert result.exit_code != 0
    # On GitHub Actions typer forces colour; the codes split "--census" apart.
    assert "--census" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
