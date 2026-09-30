"""A Dictionary's x-version names one content: the lock records its digest (issue #25)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"
LOCK = DICIONARIOS / "versoes.json"


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = ROOT / "scripts" / "metadados" / "travar_versoes.py"
    spec = importlib.util.spec_from_file_location("travar_versoes", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "travar_versoes", module)
    spec.loader.exec_module(module)
    return module


def _copy(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of the packaged dictionaries and of the committed lock."""
    dicionarios = tmp_path / "dicionarios"
    dicionarios.mkdir()
    for path in DICIONARIOS.glob("*.yaml"):
        shutil.copy(path, dicionarios / path.name)
    lock = tmp_path / "versoes.json"
    shutil.copy(LOCK, lock)
    return dicionarios, lock


def test_committed_lock_is_current(monkeypatch):
    assert _load(monkeypatch).generate() == LOCK.read_text(encoding="utf-8")


def test_changed_content_without_a_new_version_is_refused(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    path = dicionarios / "sih_aih_reduzida.yaml"
    text = path.read_text(encoding="utf-8")
    assert "label: Número da AIH\n" in text
    path.write_text(text.replace("label: Número da AIH\n", "label: Nº da AIH\n"), "utf-8")
    with pytest.raises(ValueError, match=r"sih_aih_reduzida.*bump x-version"):
        module.generate(dicionarios, lock)


def test_a_new_version_is_added_and_the_old_one_kept(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    path = dicionarios / "sih_aih_reduzida.yaml"
    text = path.read_text(encoding="utf-8")
    old = module.load_lock(lock.read_text(encoding="utf-8"))["sih_aih_reduzida"]
    [(version, _)] = old.items()
    text = text.replace("label: Número da AIH\n", "label: Nº da AIH\n")
    path.write_text(text.replace(f'x-version: "{version}"', 'x-version: "99.0.0"'), "utf-8")
    new = module.load_lock(module.generate(dicionarios, lock))["sih_aih_reduzida"]
    assert new[version] == old[version]
    assert list(new) == [version, "99.0.0"]
    assert new["99.0.0"] != old[version]


def test_lock_with_a_duplicate_version_is_refused(monkeypatch):
    """Synthetic lock: what a hand-resolved merge of two bumps to 2.9.0 would leave."""
    text = '{"sih_aih_reduzida": {"2.9.0": "aa", "2.9.0": "bb"}}'
    with pytest.raises(ValueError, match=r"2\.9\.0"):
        _load(monkeypatch).load_lock(text)


def test_lock_entry_for_an_unknown_dictionary_is_refused(monkeypatch, tmp_path):
    """Synthetic lock entry: a dictionary name that has no YAML."""
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    entries = json.loads(lock.read_text(encoding="utf-8"))
    entries["nao_existe"] = {"1.0.0": "00"}
    lock.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="nao_existe"):
        module.generate(dicionarios, lock)
