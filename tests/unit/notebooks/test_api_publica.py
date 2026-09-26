"""The notebooks teach the public API: `import omnisus as odb` and `odb.<name>` only.

A notebook is what a researcher copies. Private helpers (`omnisus._notebooks`,
`load_dicionario`, `resolve_target`) would teach code that is not documented and
may change without notice, so no notebook imports them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import omnisus as odb

NOTEBOOKS = Path(__file__).resolve().parents[3] / "notebooks"
TODOS = sorted(p for p in NOTEBOOKS.glob("*.py") if not p.name.startswith("_"))

# Modules a notebook may import besides omnisus.
BIBLIOTECAS = {"json", "marimo", "polars", "pathlib"}

# A name with no public door yet, by notebook. Each one says why.
EXCECOES = {
    # The BNAFAR/Hórus stock API is inspected, never published in the lake.
    "medicamentos.py": {"omnisus.sources.medicamentos": {"fetch_stock_page"}},
    # IBGE has no server listing; the accepted years are package constants.
    "ibge_populacao.py": {
        "omnisus.sources.ibge.products": {"CENSUS_YEARS", "ESTIMATE_UNAVAILABLE_YEARS"}
    },
}


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


@pytest.mark.parametrize("caminho", TODOS, ids=lambda p: p.name)
def test_imports_only_omnisus_as_odb_and_plain_libraries(caminho):
    permitidos = EXCECOES.get(caminho.name, {})
    for node in ast.walk(_arvore(caminho)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "omnisus":
                    assert alias.asname == "odb", caminho.name
                else:
                    assert alias.name in BIBLIOTECAS, (caminho.name, alias.name)
        elif isinstance(node, ast.ImportFrom):
            nomes = {alias.name for alias in node.names}
            if node.module in permitidos:
                assert nomes <= permitidos[node.module], (caminho.name, node.module, nomes)
            else:
                assert node.module in BIBLIOTECAS, (caminho.name, node.module, nomes)


@pytest.mark.parametrize("caminho", TODOS, ids=lambda p: p.name)
def test_every_odb_name_is_public(caminho):
    for node in ast.walk(_arvore(caminho)):
        if isinstance(node, ast.Attribute) and getattr(node.value, "id", None) == "odb":
            assert node.attr in odb.__all__, (caminho.name, node.attr)


@pytest.mark.parametrize("caminho", TODOS, ids=lambda p: p.name)
def test_rows_come_from_load_and_the_citation_from_cite(caminho):
    """One mechanism per step: `odb.load` reads, `odb.cite` cites."""
    texto = caminho.read_text(encoding="utf-8")
    if caminho.stem != "ibge_populacao":  # IBGE is not an FTP dataset; see its notebook
        assert "odb.load(" in texto, caminho.name
    if caminho.stem != "linkage":  # linkage cites nothing: it measures, it does not publish
        assert "odb.cite(" in texto, caminho.name
