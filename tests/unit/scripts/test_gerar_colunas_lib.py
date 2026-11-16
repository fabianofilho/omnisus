"""The columns the import adds are generated into every DATASUS dictionary (issue #11)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from omnisus.sources.datasus_ftp.datasets import REGISTRY
from omnisus.sources.datasus_ftp.library_columns import is_library_field, library_columns
from omnisus.transforms.dictionaries import load_dicionario

ROOT = Path(__file__).resolve().parents[3]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = ROOT / "scripts" / "metadados" / "gerar_colunas_lib.py"
    spec = importlib.util.spec_from_file_location("gerar_colunas_lib", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "gerar_colunas_lib", module)
    spec.loader.exec_module(module)
    return module


def test_generator_output_is_committed(monkeypatch):
    """Idempotent: generating again changes no byte of any dictionary."""
    generated = _load(monkeypatch).generate()
    assert len(generated) == len(REGISTRY)
    for path, text in generated.items():
        assert path.read_text(encoding="utf-8") == text, path.name


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_a_dictionary_declares_exactly_the_columns_the_import_adds(name):
    declared = [f["name"] for f in load_dicionario(name).fields if is_library_field(f)]
    assert sorted(declared) == sorted(c.name for c in library_columns(REGISTRY[name]))


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_the_import_columns_follow_the_registry_row(name):
    d = REGISTRY[name]
    names = {c.name for c in library_columns(d)}
    assert ("ano" in names) is (d.geography == "state")
    assert ("uf" in names) is (d.geography == "state")
    assert ("mes" in names) is d.monthly
    assert ("_source_ano" in names) is (d.geography == "national")
    assert "_source_release" in names


def test_the_release_is_not_a_code_of_the_datasus():
    """`final` and `prelim` name a directory of ours, so no dictionary maps them (issue #11).
    The duplicate `derivation:` key, which no reader used, is gone too."""
    for path in sorted(DICIONARIOS.glob("*.yaml")):
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
        for field in raw["schema"]["fields"]:
            if field["name"] == "_source_release":
                assert "x-decode" not in field, path.name
            assert "derivation" not in field, f"{path.name}.{field['name']}"


def test_er_declares_the_type_the_lake_stores_and_the_one_the_file_publishes():
    """ANO C(4) and MES C(2) are replaced by integers when staged (evidence/2026-09-23-er-ano-mes)."""
    fields = {f["name"]: f for f in load_dicionario("sih_aih_rejeitada_erro").fields}
    for name, width in (("ano", 4), ("mes", 2)):
        field = fields[name]
        assert field["type"] == "integer"
        assert is_library_field(field)
        meta = field["x-metadata"]
        assert meta["physical_name"] == name.upper()
        assert meta["physical_type"] == {"type": "string", "length": width}
