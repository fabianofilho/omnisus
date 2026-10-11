"""Packaging contract: a base install does not pull the notebook runtime."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _names(requirements: list[str]) -> set[str]:
    return {re.split(r"[<>=!~;\[ ]", r, maxsplit=1)[0].strip().lower() for r in requirements}


def test_marimo_is_only_an_optional_extra():
    project = PYPROJECT["project"]
    assert "marimo" not in _names(project["dependencies"])
    assert "marimo" in _names(project["optional-dependencies"]["notebooks"])


def test_ipykernel_is_only_the_colab_extra():
    # A library-only install (a server reading the lake) must not pull the Jupyter
    # kernel and its ~25 dependencies (#100).
    project = PYPROJECT["project"]
    assert "ipykernel" not in _names(project["dependencies"])
    assert "ipykernel" in _names(project["optional-dependencies"]["colab"])


def test_dev_installs_the_notebooks_extra():
    # CI syncs only --extra dev, and tests/unit/notebooks imports marimo.
    assert "omnisus[notebooks]" in PYPROJECT["project"]["optional-dependencies"]["dev"]


def test_no_packaged_data_file_is_gitignored():
    """Hatch leaves gitignored files out of the wheel: an unanchored `data/` in
    .gitignore once dropped every dictionary from it while tests on src/ passed."""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("needs the git checkout")
    packaged = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "src/omnisus/data").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", *packaged], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    assert packaged and ignored == []
