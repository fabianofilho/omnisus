"""The Colab notebook installs this version from PyPI and calls only the public API."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import omnisus as sus

NOTEBOOK = Path(__file__).resolve().parents[3] / "notebooks" / "colab.ipynb"


def _code() -> list[str]:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def test_installs_this_version_from_pypi_with_uv():
    """Colab ships uv and sets UV_SYSTEM_PYTHON, so `uv pip install` reaches the kernel."""
    install = _code()[0]
    assert f"!uv pip install -q omnisus=={sus.__version__}" in install.splitlines()


def test_cells_are_python_that_uses_only_public_names():
    for cell in _code():
        python = "\n".join(line for line in cell.splitlines() if not line.startswith(("%", "!")))
        tree = ast.parse(python)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and getattr(node.value, "id", None) == "sus":
                assert node.attr in sus.__all__, node.attr


def test_every_link_points_to_the_published_docs_or_repository():
    text = NOTEBOOK.read_text(encoding="utf-8")
    for url in re.findall(r"\]\((https?://[^)]+)\)", text):
        assert url.startswith(
            ("https://raphaelfh.github.io/omnisus/", "https://github.com/raphaelfh/omnisus/")
        ), url
