"""The runner resolves scopes from the listing and says why each one did not import."""

from __future__ import annotations

import asyncio
import ftplib
from datetime import datetime
from pathlib import Path

import pytest

import omnisus as odb
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.inventory import FtpPathNotFound
from tests.support import fake_datasus

DBC = Path(__file__).resolve().parents[3] / "fixtures" / "dbc"
SIM_RR = (DBC / "sim_rr_2023_mini.dbc").read_bytes()
BI_PARTS = [(DBC / f"sia_bi_mg_2024_12_part{n}_excerpt.dbc").read_bytes() for n in (1, 2)]


def _target(tmp_path: Path) -> str:
    return f"ducklake:{tmp_path}/x.ducklake"


def test_a_scope_the_listing_does_not_have_is_not_listed_without_a_download(
    monkeypatch, tmp_path
) -> None:
    fetched = fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey("RR", 2023): SIM_RR})
    report = odb.import_dataset(
        "sim_obitos",
        scopes=[ScopeKey("RR", 2023), ScopeKey("AC", 2023)],
        target=_target(tmp_path),
    )
    assert [o.status for o in report.outcomes] == ["ok", "skipped"]
    assert report.outcomes[1].code == "not_listed"
    assert len(fetched) == 1 and fetched[0].endswith("DORR2023.dbc")


def test_outside_coverage_has_its_own_code(monkeypatch, tmp_path) -> None:
    fake_datasus.serve(monkeypatch, "sim_obitos", {})
    report = odb.import_dataset(
        "sim_obitos", scopes=[ScopeKey("RR", 1990)], target=_target(tmp_path)
    )
    assert report.outcomes[0].code == "outside_coverage"


def test_a_550_on_a_listed_file_is_a_failure_not_a_skip(monkeypatch, tmp_path) -> None:
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey("RR", 2023): SIM_RR})

    async def gone(entry, **_kw):
        from omnisus.sources.datasus_ftp.fetch import FtpFileNotFound

        raise FtpFileNotFound(f"{entry.path}: 550")

    monkeypatch.setattr("omnisus.sources.datasus_ftp._runner.fetch_dbc_bytes", gone)
    report = odb.import_dataset(
        "sim_obitos", scopes=[ScopeKey("RR", 2023)], target=_target(tmp_path)
    )
    assert report.outcomes[0].status == "failed"
    assert report.outcomes[0].code == "fetch_failed"


def test_a_missing_registry_directory_aborts_before_any_scope(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))

    def denied(path, timeout):
        raise ftplib.error_perm(f"550 {path}")

    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory._blocking_list", denied)
    with pytest.raises(FtpPathNotFound):
        odb.import_dataset("sim_obitos", scopes=[ScopeKey("RR", 2023)], target=_target(tmp_path))


def test_the_same_file_again_is_unchanged(monkeypatch, tmp_path) -> None:
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey("RR", 2023): SIM_RR})
    scopes = [ScopeKey("RR", 2023)]
    odb.import_dataset("sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same")
    again = odb.import_dataset(
        "sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same"
    )
    assert again.outcomes[0].code == "unchanged"


def test_an_unchanged_listing_is_skipped_without_a_download(monkeypatch, tmp_path) -> None:
    """Same path, size and server time as the publication, same dictionary:
    nothing to download. Before, the 16 MB SIH SP file was fetched and decoded
    only to learn its SHA-256 matched."""
    scopes = [ScopeKey("RR", 2023)]
    fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    odb.import_dataset("sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same")
    fetched = fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    again = odb.import_dataset(
        "sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same"
    )
    assert (again.outcomes[0].status, again.outcomes[0].code) == ("skipped", "unchanged")
    assert fetched == []


def test_a_new_server_time_downloads_and_compares_the_bytes(monkeypatch, tmp_path) -> None:
    """A republished file (new server time) is downloaded; identical bytes are
    still ``unchanged``, now proven by SHA-256."""
    scopes = [ScopeKey("RR", 2023)]
    fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    odb.import_dataset("sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same")
    fetched = fake_datasus.serve(
        monkeypatch, "sim_obitos", {scopes[0]: SIM_RR}, modified=datetime(2025, 1, 2, 3, 4)
    )
    again = odb.import_dataset(
        "sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same"
    )
    assert again.outcomes[0].code == "unchanged"
    assert len(fetched) == 1


def test_a_new_dictionary_downloads_even_when_the_listing_is_unchanged(
    monkeypatch, tmp_path
) -> None:
    """The parser version is part of "same": a changed dictionary is not skipped
    early, so ``skip_same`` reaches the publication check and asks for replace."""
    from omnisus.sources.datasus_ftp import _runner

    scopes = [ScopeKey("RR", 2023)]
    fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    odb.import_dataset("sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same")
    fetched = fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    monkeypatch.setattr(_runner, "parser_version", lambda d: "dbc-staging-v1:" + "0" * 64)
    again = odb.import_dataset(
        "sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same"
    )
    assert again.outcomes[0].status == "failed"
    assert "replace" in (again.outcomes[0].reason or "")
    assert len(fetched) == 1


def _edited_dictionary(tmp_path: Path, dataset: str, edit) -> Path:
    """``dataset``'s packaged YAML, parsed, changed by ``edit`` and written to ``tmp_path``."""
    from importlib.resources import files

    import yaml

    raw = yaml.safe_load(
        (files("omnisus.data.dicionarios") / f"{dataset}.yaml").read_text("utf-8")
    )
    edit(raw)
    path = tmp_path / f"{dataset}.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _relabel(raw: dict) -> None:
    """An editorial change: a label, a code map and a claim note, none read by the import."""
    field = raw["schema"]["fields"][0]
    field["label"] = field.get("label", "") + " (revisto)"
    field["x-decode"] = {"1": "Um"}
    field["x-metadata"] = {"claims": [{"target": "/field/codes", "note": "Conferido de novo."}]}


def test_an_editorial_dictionary_change_keeps_the_scope_unchanged(monkeypatch, tmp_path) -> None:
    """Labels, code maps and claims are read when rows are queried, never when they are
    imported, so a lake imported under the old dictionary needs no replace (issue #13)."""
    from dataclasses import replace

    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    scopes = [ScopeKey("RR", 2023)]
    fake_datasus.serve(monkeypatch, "sim_obitos", {scopes[0]: SIM_RR})
    odb.import_dataset("sim_obitos", scopes=scopes, target=_target(tmp_path), policy="skip_same")
    edited = replace(
        REGISTRY["sim_obitos"], dictionary=_edited_dictionary(tmp_path, "sim_obitos", _relabel)
    )
    fetched = fake_datasus.serve(monkeypatch, edited, {scopes[0]: SIM_RR})
    again = odb.import_dataset(edited, scopes=scopes, target=_target(tmp_path), policy="skip_same")
    assert (again.outcomes[0].status, again.outcomes[0].code) == ("skipped", "unchanged")
    assert fetched == []


@pytest.mark.parametrize(
    ("dataset", "edit", "same"),
    [
        ("sinan_hanseniase", _relabel, True),
        ("sinan_hanseniase", lambda raw: raw.update(encoding="cp1252"), False),
        ("sinan_hanseniase", lambda raw: raw["x-identity"].update(code="A30"), False),
    ],
    ids=["editorial", "encoding", "x-identity"],
)
def test_the_parser_version_follows_only_what_the_import_reads(
    tmp_path, dataset, edit, same
) -> None:
    """The import reads the dictionary's ``encoding`` (to decode text) and ``x-identity``
    (to accept or reject the file); nothing else in the YAML changes the stored rows."""
    from dataclasses import replace

    from omnisus.sources.datasus_ftp._runner import parser_version
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    packaged = REGISTRY[dataset]
    edited = replace(packaged, dictionary=_edited_dictionary(tmp_path, dataset, edit))
    assert (parser_version(edited) == parser_version(packaged)) is same


def test_a_split_month_imports_through_the_runner(monkeypatch, tmp_path) -> None:
    scope = ScopeKey("MG", 2024, 12)
    fetched = fake_datasus.serve(monkeypatch, "sia_bpa_individualizado", {scope: BI_PARTS})
    report = odb.import_dataset(
        "sia_bpa_individualizado", scopes=[scope], target=_target(tmp_path)
    )
    assert report.outcomes[0].status == "ok" and report.rows == 400
    assert [p.rsplit("/", 1)[1] for p in fetched] == ["BIMG2412_1.dbc", "BIMG2412_2.dbc"]


def test_a_scope_over_the_inflight_budget_fails_and_the_run_continues(
    monkeypatch, tmp_path
) -> None:
    """A split month larger than the in-flight budget is that scope's failure,
    never a run-wide error: the other scope still imports."""
    big, small = ScopeKey("MG", 2024, 12), ScopeKey("MG", 2024, 11)
    fake_datasus.serve(monkeypatch, "sia_bpa_individualizado", {big: BI_PARTS, small: BI_PARTS[0]})
    # MG 2024-12 bytes stand in for 2024-11; the identity check would refuse them.
    monkeypatch.setattr(
        "omnisus.sources.datasus_ftp._runner.validate_identity", lambda *_a, **_k: None
    )
    budget = len(BI_PARTS[0]) + len(BI_PARTS[1]) - 1
    report = odb.import_dataset(
        "sia_bpa_individualizado",
        scopes=[big, small],
        target=_target(tmp_path),
        max_payload_bytes=max(map(len, BI_PARTS)),
        max_inflight_bytes=budget,
    )
    failed, ok = report.outcomes
    assert (failed.status, failed.code) == ("failed", "fetch_failed")
    assert str(budget + 1) in (failed.reason or "") and "max_inflight_bytes" in (
        failed.reason or ""
    )
    assert ok.status == "ok" and report.rows == 200


def test_a_file_over_the_payload_cap_fails_before_it_is_downloaded(monkeypatch, tmp_path) -> None:
    scope = ScopeKey("MG", 2024, 12)
    fetched = fake_datasus.serve(monkeypatch, "sia_bpa_individualizado", {scope: BI_PARTS})
    cap = len(BI_PARTS[0]) - 1
    report = odb.import_dataset(
        "sia_bpa_individualizado",
        scopes=[scope],
        target=_target(tmp_path),
        max_payload_bytes=cap,
        max_inflight_bytes=10 * cap,
    )
    (outcome,) = report.outcomes
    assert (outcome.status, outcome.code) == ("failed", "fetch_failed")
    assert "max_payload_bytes" in (outcome.reason or "")
    assert fetched == []


def _serve_real_sia_listing(monkeypatch, tmp_path) -> list[str]:
    """The real SIASUS/200801_/Dados listing, parsed by ``list_sources``
    (``inventory.sources_for``). The names and sizes are the server's; the bytes
    behind them are the committed BI excerpts, because the real parts are too
    large to commit. Returns the fetched names in order."""
    from omnisus.sources.datasus_ftp import _runner
    from omnisus.sources.datasus_ftp.datasets import REGISTRY
    from tests.support.listings import serve_listings

    monkeypatch.setenv("OMNISUS_CACHE_DIR", str(tmp_path / "cache"))
    serve_listings(
        monkeypatch, {REGISTRY["sia_bpa_individualizado"].ftp_dir: "siasus_200801_dados"}
    )
    fetched: list[str] = []

    async def fetch(entry, **_kw):
        fetched.append(entry.name)
        await asyncio.sleep(0)  # a real download suspends; let other scopes run
        return BI_PARTS[len(fetched) % 2]

    monkeypatch.setattr(_runner, "fetch_dbc_bytes", fetch)
    # The stand-in bytes are MG 2024-12, so the file-identity check (test_identity.py)
    # would rightly refuse them as SP 2025-10; these tests are about fetching.
    monkeypatch.setattr(_runner, "validate_identity", lambda *_a, **_k: None)
    return fetched


def test_a_real_three_part_month_imports_under_default_limits(monkeypatch, tmp_path) -> None:
    """SIA BPA-I SP 2025-10 is listed as three parts totalling 534,393,112
    bytes: more than two 512 MiB payload caps, well inside the 1 GiB budget."""
    fetched = _serve_real_sia_listing(monkeypatch, tmp_path)
    report = odb.import_dataset(
        "sia_bpa_individualizado", scopes=[ScopeKey("SP", 2025, 10)], target=_target(tmp_path)
    )
    assert report.outcomes[0].status == "ok", report.outcomes[0].reason
    assert fetched == ["BISP2510_1.dbc", "BISP2510_2.dbc", "BISP2510_3.dbc"]


def test_a_real_split_month_reserves_the_sum_of_its_listed_sizes(monkeypatch, tmp_path) -> None:
    """SP 2025-10 (534,393,112 bytes listed) and SP 2025-11 (478,365,189) each
    fit a budget one byte short of both, so the second month's download waits
    until the first is ingested, then runs. A budget one byte short of a month's
    sum fails that month, naming the sum."""
    fetched = _serve_real_sia_listing(monkeypatch, tmp_path)
    october, november = ScopeKey("SP", 2025, 10), ScopeKey("SP", 2025, 11)
    report = odb.import_dataset(
        "sia_bpa_individualizado",
        scopes=[october, november],
        target=_target(tmp_path),
        concurrency=2,
        max_inflight_bytes=534_393_112 + 478_365_189 - 1,
    )
    assert [o.status for o in report.outcomes] == ["ok", "ok"]
    assert fetched == [f"BISP25{m}_{n}.dbc" for m in (10, 11) for n in (1, 2, 3)]

    short = odb.import_dataset(
        "sia_bpa_individualizado",
        scopes=[october],
        target=f"ducklake:{tmp_path}/short.ducklake",
        max_payload_bytes=202_352_447,
        max_inflight_bytes=534_393_112 - 1,
    )
    assert (short.outcomes[0].status, short.outcomes[0].code) == ("failed", "fetch_failed")
    assert "534393112" in (short.outcomes[0].reason or "")


@pytest.mark.asyncio
async def test_split_months_sharing_a_small_budget_do_not_deadlock(monkeypatch, tmp_path) -> None:
    """Each scope reserves the sum of its listed sizes in one step. Reserved
    file by file, three split months could each hold one part's bytes and wait
    for the others forever. The two-byte parts are synthetic: only their sizes
    matter here, and ingest rejects them (``ingest_failed``) by design."""
    from omnisus.lake import Lake
    from omnisus.sources.datasus_ftp import _runner

    scopes = [ScopeKey("MG", 2024, m) for m in (10, 11, 12)]
    fake_datasus.serve(monkeypatch, "sia_bpa_individualizado", {s: [b"ab", b"cd"] for s in scopes})
    served = _runner.fetch_dbc_bytes

    async def yielding(entry, **kw):
        await asyncio.sleep(0)  # a real download suspends; let the others run
        return await served(entry, **kw)

    monkeypatch.setattr(_runner, "fetch_dbc_bytes", yielding)
    with Lake.local(_target(tmp_path)) as lake:
        report = await asyncio.wait_for(
            _runner.run_scopes(
                "sia_bpa_individualizado",
                scopes=scopes,
                lake=lake,
                concurrency=3,
                max_payload_bytes=2,
                max_inflight_bytes=5,
            ),
            timeout=5,
        )
    assert [o.code for o in report.outcomes] == ["ingest_failed"] * 3
