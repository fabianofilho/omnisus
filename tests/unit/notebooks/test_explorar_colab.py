"""explorar_colab.ipynb imports scopes, explores them and cites them, on real SIM files.

The fake server in `tests/support/fake_datasus.py` serves `sim_rr_2022_mini` and
`sim_rr_2023_mini` (`tests/fixtures/FIXTURES.md`). The code cells run in order in one
namespace, without the `!` install line, as `test_colab_e2e.py` runs `colab.ipynb`; a
Colab form field (`NAME = value  # @param`) takes the value a test gives it, and
`USAR_DRIVE` is off, so the lake is `$OMNISUS_DATA_DIR`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest
from tests.support import fake_datasus
from tests.unit.test_fixture_provenance import load_fixture_rows

import omnisus as sus
from omnisus.sources._base import ScopeKey

ROOT = Path(__file__).resolve().parents[3]
NOTEBOOK = ROOT / "notebooks" / "explorar_colab.ipynb"
ARQUIVOS = {
    ScopeKey(uf="RR", ano=ano): ROOT / "tests" / "fixtures" / "dbc" / f"sim_rr_{ano}_mini.dbc"
    for ano in (2022, 2023)
}


def _registros(arquivo: Path) -> int:
    nome = f"dbc/{arquivo.name}"
    return int(next(r for r in load_fixture_rows() if r["file"] == nome)["records"])


def _code() -> list[str]:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    return ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]


def _executar(monkeypatch, lake: Path, **campos: object) -> dict:
    """Run the code cells with the form fields in `campos`; return what they define."""
    monkeypatch.setenv("OMNISUS_DATA_DIR", str(lake))
    campos = {"USAR_DRIVE": False, **campos}
    namespace: dict = {"display": lambda *args, **kwargs: None}
    for i, cell in enumerate(_code()):
        linhas = []
        for linha in cell.splitlines():
            if linha.startswith("!"):
                continue
            campo = re.match(r"(\w+) = .+?(  # @param.*)$", linha)
            if campo and campo[1] in campos:
                linha = f"{campo[1]} = {campos.pop(campo[1])!r}{campo[2]}"
            linhas.append(linha)
        exec(compile("\n".join(linhas), f"explorar_colab.ipynb, cell {i + 1}", "exec"), namespace)
    assert not campos, f"not form fields of the notebook: {campos}"
    return namespace


@pytest.fixture(scope="module")
def importado(tmp_path_factory) -> tuple[Path, dict]:
    """The lake the notebook fills with RR 2022 and 2023, and what its cells define."""
    lake = tmp_path_factory.mktemp("explorar_colab")
    with pytest.MonkeyPatch.context() as monkeypatch:
        fake_datasus.serve(
            monkeypatch, "sim_obitos", {e: a.read_bytes() for e, a in ARQUIVOS.items()}
        )
        definidos = _executar(monkeypatch, lake, ANOS="2022, 2023")
    return lake, definidos


def test_installs_this_version_from_pypi_with_uv():
    """Colab ships uv and sets UV_SYSTEM_PYTHON, so `uv pip install` reaches the kernel."""
    install = _code()[0]
    assert f'!uv pip install -q "omnisus[colab]=={sus.__version__}"' in install.splitlines()


def test_cells_are_python_that_uses_only_public_names():
    for cell in _code():
        python = "\n".join(line for line in cell.splitlines() if not line.startswith("!"))
        for node in ast.walk(ast.parse(python)):
            if isinstance(node, ast.Attribute) and getattr(node.value, "id", None) == "sus":
                assert node.attr in sus.__all__, node.attr


def test_every_link_points_to_the_published_docs_or_repository():
    text = NOTEBOOK.read_text(encoding="utf-8")
    for url in re.findall(r"\]\((https?://[^)]+)\)", text):
        assert url.startswith(
            ("https://raphaelfh.github.io/omnisus/", "https://github.com/raphaelfh/omnisus/")
        ), url


def test_imports_explores_and_cites_real_scopes(importado):
    _, definidos = importado
    registros = sum(_registros(a) for a in ARQUIVOS.values())

    assert definidos["relatorio"].rows() == [
        ("RR_2022", "importado", None),
        ("RR_2023", "importado", None),
    ]
    assert definidos["no_lake"]["ano"].to_list() == [2022, 2023]
    assert definidos["total"] == registros
    linhas = definidos["linhas"]
    assert linhas.height == registros
    # Labels from the dictionary, and the harmonised categories of a validated source.
    assert {"sexo", "sexo_rotulo", "idade_anos_completos"} <= set(linhas.columns)
    assert definidos["perfil"]["registros"].sum() == registros
    assert "sexo_rotulo" in definidos["perfil"].columns
    for arquivo in ARQUIVOS.values():
        assert hashlib.sha256(arquivo.read_bytes()).hexdigest() in definidos["citacao"]


def test_a_second_run_downloads_nothing_already_in_the_lake(importado, monkeypatch):
    lake, _ = importado
    baixados = fake_datasus.serve(
        monkeypatch, "sim_obitos", {e: a.read_bytes() for e, a in ARQUIVOS.items()}
    )

    definidos = _executar(monkeypatch, lake, ANOS="2022 2023")

    assert definidos["relatorio"]["situacao"].to_list() == ["já estava no lake"] * 2
    assert baixados == []


def test_without_importar_it_explores_the_lake_without_the_server(importado, monkeypatch):
    lake, _ = importado
    fake_datasus.block_ftp_listing(monkeypatch)

    definidos = _executar(monkeypatch, lake, IMPORTAR=False)

    assert "relatorio" not in definidos
    assert definidos["total"] == sum(_registros(a) for a in ARQUIVOS.values())


def test_the_chosen_year_limits_rows_profile_and_citation(importado, monkeypatch):
    lake, _ = importado
    fake_datasus.block_ftp_listing(monkeypatch)
    ano_2023 = ARQUIVOS[ScopeKey(uf="RR", ano=2023)]

    definidos = _executar(monkeypatch, lake, IMPORTAR=False, ANOS_EXPLORAR="2023")

    assert definidos["total"] == definidos["linhas"].height == _registros(ano_2023)
    assert definidos["perfil"]["registros"].sum() == _registros(ano_2023)
    assert "DORR2023.dbc" in definidos["citacao"]
    assert "DORR2022.dbc" not in definidos["citacao"]


def test_the_row_limit_caps_the_table_but_not_the_count(importado, monkeypatch):
    lake, _ = importado
    fake_datasus.block_ftp_listing(monkeypatch)

    definidos = _executar(monkeypatch, lake, IMPORTAR=False, LINHAS=100)

    assert definidos["linhas"].height == 100
    assert definidos["total"] == sum(_registros(a) for a in ARQUIVOS.values())


def test_a_cut_the_lake_does_not_have_says_so(importado, monkeypatch):
    lake, _ = importado
    fake_datasus.block_ftp_listing(monkeypatch)

    with pytest.raises(ValueError, match="O lake não tem escopos de sim_obitos"):
        _executar(monkeypatch, lake, IMPORTAR=False, UFS_EXPLORAR="SP")
