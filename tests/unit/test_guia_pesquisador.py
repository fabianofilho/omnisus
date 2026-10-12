"""The researcher guide keeps its shape: seven sections, notebook links, cited sources."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GITHUB = "https://github.com/raphaelfh/omnisus/blob/main/"
SECOES = [
    "Em uma frase",
    "O que um registro representa",
    "Datas e geografia",
    "Cobertura e modalidade",
    "Armadilhas",
    "Como usar",
    "Fontes",
]

# Profile page in docs/sources/ -> notebook in notebooks/.
PERFIS = {
    "sim_obitos": "sim_obitos",
    "sinasc_nascidos_vivos": "sinasc_nascidos_vivos",
    "sih_aih_reduzida": "sih_aih_reduzida",
    "sia": "sia",
    "cnes_estabelecimentos": "cnes_estabelecimentos",
    "ibge_populacao": "ibge_populacao",
    "sinan_chagas": "sinan",
    "sinan_hanseniase": "sinan",
    "sinan_tuberculose": "sinan",
    "medicamentos": "medicamentos",
}


def _texto(perfil: str) -> str:
    return (ROOT / "docs/sources" / f"{perfil}.md").read_text(encoding="utf-8")


def _secao(texto: str, titulo: str) -> str:
    return texto.split(f"\n## {titulo}\n", 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_profile_has_the_seven_sections_in_order(perfil):
    secoes = re.findall(r"^## (.+?)\s*$", _texto(perfil), flags=re.MULTILINE)
    assert secoes[:7] == SECOES
    assert secoes[7:] in ([], ["Detalhes técnicos"])


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_profile_links_its_notebook(perfil):
    caminho = f"notebooks/{PERFIS[perfil]}.py"
    assert (ROOT / caminho).is_file()
    secao = _secao(_texto(perfil), "Como usar")
    assert GITHUB + caminho in secao
    assert f"https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/{caminho}" in secao


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_sources_section_cites_a_document(perfil):
    assert re.search(r"(https?|ftp)://\S+", _secao(_texto(perfil), "Fontes"))


def _linhas_com(perfil: str, trecho: str) -> list[str]:
    return [linha for linha in _texto(perfil).splitlines() if trecho in linha]


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_profile_calls_datasets_page_bases_e_argumentos(perfil):
    # In CONTEXT.md the catalog is the lake's database, not docs/datasets.md (#64).
    linhas = _linhas_com(perfil, "datasets.md")
    assert [linha for linha in linhas if "catálogo" in linha.lower()] == []


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_profile_links_datasets_page_to_a_section(perfil):
    # mkdocs build --strict fails when the section does not exist (mkdocs.yml, validation).
    assert _linhas_com(perfil, "](../datasets.md)") == []


def test_every_bases_notebook_has_a_profile():
    notebooks = {
        p.stem for p in (ROOT / "notebooks").glob("*.py") if not p.name.startswith("_")
    } - {"linkage", "bases", "explorar"}
    assert set(PERFIS.values()) == notebooks


COMECE_AQUI = ROOT / "docs/pesquisa/index.md"


@pytest.mark.parametrize("notebook", sorted(set(PERFIS.values())))
def test_start_page_links_every_bases_notebook(notebook):
    assert f"{GITHUB}notebooks/{notebook}.py" in COMECE_AQUI.read_text(encoding="utf-8")


MOLAB = "https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/"


@pytest.mark.parametrize("notebook", sorted(set(PERFIS.values())))
def test_start_page_opens_every_bases_notebook_in_molab(notebook):
    caminho = f"notebooks/{notebook}.py"
    assert f"]({MOLAB}{caminho})" in COMECE_AQUI.read_text(encoding="utf-8")


@pytest.mark.parametrize("perfil", sorted(PERFIS))
def test_start_page_links_every_profile(perfil):
    assert f"../sources/{perfil}.md" in COMECE_AQUI.read_text(encoding="utf-8")
