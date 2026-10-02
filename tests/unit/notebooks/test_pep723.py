"""Notebooks carry PEP 723 metadata so sandbox/molab install this omnisus version from PyPI."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import omnisus as sus

NOTEBOOKS = Path(__file__).resolve().parents[3] / "notebooks"

# PEP 723: a comment block that starts with `# /// script` and ends with `# ///`.
_BLOCO = re.compile(r"(?m)^# /// script\n((?:#(?: |$).*\n)*)# ///")


def _notebooks() -> list[Path]:
    return sorted(
        p
        for p in NOTEBOOKS.rglob("*.py")
        if not any(part.startswith("_") for part in p.relative_to(NOTEBOOKS).parts)
    )


def _metadados(caminho: Path) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith("# /// script\n"), f"{caminho.name} must start with PEP 723 metadata"
    bloco = _BLOCO.match(texto)
    assert bloco, f"{caminho.name} has a broken PEP 723 comment block"
    linhas = []
    for linha in bloco.group(1).splitlines():
        if linha.startswith("# "):
            linhas.append(linha[2:])
        elif linha == "#":
            linhas.append("")
        else:
            raise AssertionError(f"{caminho.name}: unexpected metadata line {linha!r}")
    return tomllib.loads("\n".join(linhas) + "\n")


def test_every_notebook_pins_this_version_from_pypi():
    """A release bumps every notebook to the version it publishes."""
    caminhos = _notebooks()
    assert caminhos, "no notebooks found"
    for caminho in caminhos:
        meta = _metadados(caminho)
        assert meta["requires-python"] == ">=3.12"
        nomes = {re.split(r"[<>=!~;\[ ]", dep, maxsplit=1)[0] for dep in meta["dependencies"]}
        assert {"marimo", "omnisus", "polars"} <= nomes
        assert f"omnisus=={sus.__version__}" in meta["dependencies"], caminho.name
        assert "tool" not in meta, f"{caminho.name}: omnisus comes from PyPI, not a git source"


def test_every_notebook_pins_marimo_like_the_notebooks_extra():
    """A sandbox install must get the marimo that CI checks the notebooks with."""
    pyproject = tomllib.loads((NOTEBOOKS.parent / "pyproject.toml").read_text(encoding="utf-8"))
    extra = pyproject["project"]["optional-dependencies"]["notebooks"]
    esperado = next(dep for dep in extra if dep.startswith("marimo"))
    for caminho in _notebooks():
        deps = _metadados(caminho)["dependencies"]
        assert esperado in deps, f"{caminho.name}: {deps}"
