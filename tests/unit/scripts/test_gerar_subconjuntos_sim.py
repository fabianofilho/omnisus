"""DOINF, DOMAT and DOEXT records are DO records, so they read with sim_obitos' fields."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from omnisus.sources.datasus_ftp.library_columns import is_library_field
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.dictionaries import load_dicionario

ROOT = Path(__file__).resolve().parents[3]
SUBSETS = [
    ("sim_obitos_infantis", "sim_doinf_br_2023_excerpt"),
    ("sim_obitos_maternos", "sim_domat_br_2023_mini"),
    ("sim_obitos_externos", "sim_doext_br_2023_excerpt"),
]


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = ROOT / "scripts" / "metadados" / "gerar_subconjuntos_sim.py"
    spec = importlib.util.spec_from_file_location("gerar_subconjuntos_sim", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "gerar_subconjuntos_sim", module)
    spec.loader.exec_module(module)
    return module


def _physical(fields):
    """The fields the DBF publishes, without the columns the import adds."""
    return [f for f in fields if not is_library_field(f)]


def test_generator_output_is_committed(monkeypatch):
    for path, text in _load(monkeypatch).generate().items():
        assert path.read_text(encoding="utf-8") == text, path.name


@pytest.mark.parametrize(("dataset", "fixture"), SUBSETS)
def test_every_shared_field_is_sim_obitos_field(dataset, fixture):
    do = {f["name"]: f for f in _physical(load_dicionario("sim_obitos").fields)}
    fields = _physical(load_dicionario(dataset).fields)
    assert [f["name"] for f in fields if f["name"] not in do] == []
    assert [f["name"] for f in fields if f != do[f["name"]]] == []


@pytest.mark.parametrize(("dataset", "fixture"), SUBSETS)
def test_a_subset_record_takes_the_label_of_its_do_record(dbc_fixture, dataset, fixture):
    """The 2023 fixtures hold sexo 1/2 and racacor 1-5, which only sim_obitos decodes."""
    frame = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
    subset, do = load_dicionario(dataset), load_dicionario("sim_obitos")
    for field in ("sexo", "racacor", "estciv", "esc2010"):
        for value in set(frame[field].drop_nulls()):
            assert subset.decode(field, value) == do.decode(field, value), (field, value)
    assert {subset.decode("sexo", v) for v in set(frame["sexo"])} <= {
        "Masculino",
        "Feminino",
        "Ignorado",
    }
