"""A Dictionary's x-version names one content: the lock records its digest (issue #25)."""

from __future__ import annotations

import importlib.util
import json
import re
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


def _edit(path: Path, version: str | None = None, changed: bool = True) -> None:
    """Rewrite a real dictionary: a new top-level key and/or another x-version line."""
    text = path.read_text(encoding="utf-8")
    if changed:
        text += "x-teste: 1\n"
    if version is not None:
        text, n = re.subn(r"(?m)^x-version:.*$", f'x-version: "{version}"', text)
        assert n == 1
    path.write_text(text, encoding="utf-8")


def _locked(module: ModuleType, text: str) -> dict[str, str]:
    return module.load_lock(text)["sih_aih_reduzida"]


def test_changed_content_without_a_new_version_is_refused(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    _edit(dicionarios / "sih_aih_reduzida.yaml")
    with pytest.raises(ValueError, match=r"sih_aih_reduzida.*bump x-version"):
        module.generate(dicionarios, lock)


def test_a_new_version_is_added_last_and_old_ones_kept(monkeypatch, tmp_path):
    """10.0.0 sorts before 2.x as text: the lock orders versions as numbers."""
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    old = _locked(module, lock.read_text(encoding="utf-8"))
    _edit(dicionarios / "sih_aih_reduzida.yaml", "10.0.0")
    new = _locked(module, module.generate(dicionarios, lock))
    assert {v: new[v] for v in old} == old
    assert list(new) == [*old, "10.0.0"]
    assert new["10.0.0"] not in old.values()


def test_a_new_version_lower_than_a_locked_one_is_refused(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    _edit(dicionarios / "sih_aih_reduzida.yaml", "1.0.0")
    with pytest.raises(ValueError, match="sih_aih_reduzida"):
        module.generate(dicionarios, lock)


def test_returning_to_an_earlier_locked_version_is_refused(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    path = dicionarios / "sih_aih_reduzida.yaml"
    original = path.read_text(encoding="utf-8")
    _edit(path, "10.0.0")
    lock.write_text(module.generate(dicionarios, lock), encoding="utf-8")
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="sih_aih_reduzida"):
        module.generate(dicionarios, lock)


def test_a_dictionary_without_x_version_is_refused(monkeypatch, tmp_path):
    """Synthetic removal of the x-version line from a copy of a real dictionary."""
    module = _load(monkeypatch)
    dicionarios, lock = _copy(tmp_path)
    path = dicionarios / "sih_aih_reduzida.yaml"
    text, n = re.subn(r"(?m)^x-version:.*\n", "", path.read_text(encoding="utf-8"))
    assert n == 1
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=r"sih_aih_reduzida\.yaml.*x-version"):
        module.generate(dicionarios, lock)


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
