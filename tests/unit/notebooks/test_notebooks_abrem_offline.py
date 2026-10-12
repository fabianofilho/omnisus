"""Opening a notebook opens no network connection and writes nothing.

Every notebook runs in-process with `app.run()`, as `marimo export` would.
Cells gated by `EXECUTAR` (in explorar.py, the *Importar* button) stop at `mo.stop`,
so anything reaching the network or the research lake on open is a failure. The unit
conftest also refuses FTP listings.

The guard below patches `socket.socket.connect`, which is what both `ftplib` and
`httpx` use to open a connection. It does not intercept `connect_ex`, DuckDB's
native HTTP client, or Windows asyncio's `ConnectEx`; a notebook that reached the
network through one of those would not be caught here. Loopback addresses are
allowed through because asyncio's event loop builds a self-pipe with a loopback
connect on some platforms.
"""

import importlib.util
import socket
from pathlib import Path

import pytest

NOTEBOOKS = Path(__file__).resolve().parents[3] / "notebooks"

# A leading underscore marks a helper module, not a notebook.
TODOS = sorted(
    p
    for p in NOTEBOOKS.rglob("*.py")
    if not any(part.startswith("_") for part in p.relative_to(NOTEBOOKS).parts)
)

ESPERADOS = {
    "bases.py",
    "cnes_estabelecimentos.py",
    "explorar.py",
    "ibge_populacao.py",
    "linkage.py",
    "medicamentos.py",
    "sia.py",
    "sih_aih_reduzida.py",
    "sim_obitos.py",
    "sinan.py",
    "sinasc_nascidos_vivos.py",
}

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def test_every_notebook_is_checked():
    assert {p.relative_to(NOTEBOOKS).as_posix() for p in TODOS} == ESPERADOS


MOLAB = "https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/"
MOLAB_SHIELD = "[![Open in molab](https://molab.marimo.io/molab-shield.svg)]"


@pytest.mark.parametrize("caminho", TODOS, ids=lambda p: p.relative_to(NOTEBOOKS).as_posix())
def test_every_notebook_has_molab_badge(caminho):
    rel = caminho.relative_to(NOTEBOOKS).as_posix()
    texto = caminho.read_text(encoding="utf-8")
    esperado = f"{MOLAB_SHIELD}({MOLAB}{rel})"
    assert esperado in texto


def test_notebooks_index_links_every_notebook_in_molab():
    indice = (NOTEBOOKS / "README.md").read_text(encoding="utf-8")
    for rel in sorted(ESPERADOS):
        assert f"{MOLAB_SHIELD}({MOLAB}{rel})" in indice


# The notebooks are scripts a researcher edits and exports; explorar.py is the one app,
# for exploring a lake with widgets.
@pytest.mark.parametrize(
    "caminho",
    [p for p in TODOS if p.name != "explorar.py"],
    ids=lambda p: p.relative_to(NOTEBOOKS).as_posix(),
)
def test_notebooks_are_not_marimo_apps(caminho):
    texto = caminho.read_text(encoding="utf-8")
    assert "mo.ui." not in texto, f"{caminho.name} still uses marimo widgets"


@pytest.mark.parametrize("caminho", TODOS, ids=lambda p: p.relative_to(NOTEBOOKS).as_posix())
def test_opening_downloads_and_writes_nothing(caminho, monkeypatch, tmp_path):
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        # Windows asyncio builds its self-pipe with a loopback connect.
        if not isinstance(address, tuple) or address[0] in _LOOPBACK:
            return real_connect(self, address)
        raise AssertionError(f"{caminho.name} opened a connection to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    dados = tmp_path / "dados"
    monkeypatch.setenv("OMNISUS_DATA_DIR", str(dados))
    # `python notebook.py` and marimo put the notebook's folder on sys.path.
    monkeypatch.syspath_prepend(str(caminho.parent))
    spec = importlib.util.spec_from_file_location(f"notebook_{caminho.stem}", caminho)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.app.run()

    assert not dados.exists(), f"{caminho.name} wrote to the research lake on open"
