"""Each base notebook runs every step, with `EXECUTAR` on, over a real DATASUS file.

The fake server in `tests/support/fake_datasus.py` lists and serves one committed
file (`tests/fixtures/FIXTURES.md`) for the notebook's own cut, so discovery,
`odb.load`, `odb.check_columns`, the analysis and `odb.cite` all see real rows.

Left out: `ibge_populacao.py` reads the IBGE API and `medicamentos.py` the Hórus
stock API, which have no committed response; `linkage.py` needs about thirty
tables. `test_notebooks_abrem_offline.py` still opens all of them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from tests.support import fake_datasus

from omnisus.sources._base import ScopeKey

NOTEBOOKS = Path(__file__).resolve().parents[3] / "notebooks"

# notebook -> (dataset, the notebook's cut, fixture of that exact server file)
CASOS = {
    "sim_obitos.py": ("sim_obitos", ScopeKey(uf="RR", ano=2022), "sim_rr_2022_mini", "final"),
    "sinasc_nascidos_vivos.py": (
        "sinasc_nascidos_vivos",
        ScopeKey(uf="RR", ano=2022),
        "sinasc_rr_2022_mini",
        "final",
    ),
    "sih_aih_reduzida.py": (
        "sih_aih_reduzida",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sih_rr_2024_01_mini",
        "final",
    ),
    "sia.py": (
        "sia_bpa_individualizado",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sia_bi_rr_2024_01_mini",
        "final",
    ),
    "cnes_estabelecimentos.py": (
        "cnes_estabelecimentos",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "cnes_rr_2024_01_mini",
        "final",
    ),
    "sinan.py": ("sinan_chagas", ScopeKey(uf=None, ano=2023), "sinan_chagas_br_2023", "prelim"),
}


@pytest.mark.parametrize("nome", sorted(CASOS))
def test_notebook_runs_every_step_on_real_rows(nome, monkeypatch, tmp_path, dbc_fixture):
    dataset, recorte, fixture, release = CASOS[nome]
    servido = dbc_fixture(fixture).read_bytes()
    fake_datasus.serve(monkeypatch, dataset, {recorte: servido}, release=release)
    listagem = sys.modules["omnisus.sources.datasus_ftp._runner"].list_sources
    monkeypatch.setattr("omnisus.sources.datasus_ftp.inventory.list_sources", listagem)
    monkeypatch.setattr("omnisus.list_sources", listagem)
    monkeypatch.setenv("OMNISUS_DATA_DIR", str(tmp_path / "lake"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [nome, "--executar", "true"])
    caminho = NOTEBOOKS / nome
    spec = importlib.util.spec_from_file_location(f"notebook_{caminho.stem}", caminho)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.app.run()

    pasta = tmp_path / "resultados" / dataset
    citacao = (pasta / "citacao.txt").read_text(encoding="utf-8")
    assert hashlib.sha256(servido).hexdigest() in citacao
    assert list(pasta.glob("*.csv")), "the analysis wrote no table"
