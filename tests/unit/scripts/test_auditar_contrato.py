"""`auditar_contrato.py --decode-coverage` reads a pinned snapshot and writes JSON."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from omnisus.lake import Lake
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts" / "metadados" / "auditar_contrato.py"
    spec = importlib.util.spec_from_file_location("auditar_contrato", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "auditar_contrato", module)
    spec.loader.exec_module(module)
    return module


def test_decode_coverage_lists_uncovered_values_per_dataset(tmp_path, dbc_fixture, monkeypatch):
    frame = dbc_bytes_to_lazyframe(
        dbc_fixture("sih_rr_2024_01_mini").read_bytes(), dataset="sih_aih_reduzida"
    )
    target = f"ducklake:{tmp_path}/lake.ducklake"
    with Lake.local(target) as lake:
        lake.ingest("sih_aih_reduzida", frame)
        snapshot = lake.snapshots()[-1]["snapshot_id"]

    _load(monkeypatch).audit_decode_coverage(target, snapshot, tmp_path / "out")

    report = json.loads((tmp_path / "out" / "decode-coverage.json").read_text(encoding="utf-8"))
    assert report["snapshot_id"] == snapshot
    assert [(u["field"], u["value"]) for u in report["datasets"]["sih_aih_reduzida"]] == [
        ("homonimo", "2"),
        *[(f"tpdisec{n}", "0") for n in range(1, 10)],
    ]
