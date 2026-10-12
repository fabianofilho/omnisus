"""explorar.py imports a scope, explores it with widgets and cites it, on a real SIM file.

The fake server in `tests/support/fake_datasus.py` serves `sim_rr_2022_mini`, the whole
DORR2022.dbc (`tests/fixtures/FIXTURES.md`), for the scope the import widgets open on.
`app.run()` uses each widget's default, as `marimo export` does.
"""

from __future__ import annotations

import errno
import functools
import gzip
import hashlib
import importlib.util
import io
import os
import shutil
import sys
import zipfile
from pathlib import Path

import duckdb
import polars as pl
import pytest
from tests.support import fake_datasus
from tests.support.datasus_names import filename_for
from tests.unit.test_fixture_provenance import load_fixture_rows

import omnisus as sus
from omnisus.lake._transactions import CommitOutcomeUnknown
from omnisus.lake.catalog import data_dir
from omnisus.sources import sigtap
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp import _runner

ROOT = Path(__file__).resolve().parents[3]
EXPLORAR = ROOT / "notebooks" / "explorar.py"
ARQUIVO = ROOT / "tests" / "fixtures" / "dbc" / "sim_rr_2022_mini.dbc"
ESCOPO = ScopeKey(uf="RR", ano=2022)
ARQUIVO_2023 = ROOT / "tests" / "fixtures" / "dbc" / "sim_rr_2023_mini.dbc"
ESCOPO_2023 = ScopeKey(uf="RR", ano=2023)
TODAS_AS_UFS = ",".join(sus.ALL_UFS)  # `--ufs` with every UF


def _registros(arquivo: Path) -> int:
    nome = f"dbc/{arquivo.name}"
    return int(next(r for r in load_fixture_rows() if r["file"] == nome)["records"])


REGISTROS = _registros(ARQUIVO)
SHA256 = hashlib.sha256(ARQUIVO.read_bytes()).hexdigest()


@functools.cache
def _app():
    """The notebook, loaded once: each load compiles its cells again."""
    spec = importlib.util.spec_from_file_location("notebook_explorar", EXPLORAR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def _executar(monkeypatch, *argumentos: str, defs: dict | None = None) -> tuple[str, dict]:
    """Run the notebook as `marimo export` would; return the text it shows and what its
    cells define."""
    monkeypatch.setattr(sys, "argv", ["explorar.py", *argumentos])
    saidas, definidos = _app().run(defs=defs)
    assert not [s for s in saidas if isinstance(s, duckdb.DuckDBPyConnection)]
    return " ".join(getattr(s, "text", "") for s in saidas if s is not None), definidos


def _rodar(monkeypatch, *argumentos: str) -> dict:
    """What the notebook's cells define."""
    return _executar(monkeypatch, *argumentos)[1]


def _importar(monkeypatch, pasta: Path, *argumentos: str) -> dict:
    """Click *Importar* on the lake in `pasta`, with the widgets that `argumentos` set."""
    return _rodar(monkeypatch, "--lake", str(pasta), "--executar", "true", *argumentos)


@pytest.fixture(scope="module")
def importado(tmp_path_factory) -> tuple[Path, dict, list[str]]:
    """The lake the notebook's import section fills, what its cells define then, and
    the server paths it downloaded."""
    pasta = tmp_path_factory.mktemp("explorar") / "lake"
    with pytest.MonkeyPatch.context() as monkeypatch:
        baixados = fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
        definidos = _importar(monkeypatch, pasta)
    return pasta, definidos, baixados


def test_imports_explores_and_cites_a_real_scope(importado):
    _, definidos, baixados = importado

    assert [p.rsplit("/", 1)[1] for p in baixados] == [
        filename_for(sus.resolve("sim_obitos"), ESCOPO)
    ]
    assert definidos["relatorio"].rows() == [("RR_2022", "importado", None)]
    assert definidos["importacao"] == "importado: 1"
    assert definidos["totais"] == {"sim_obitos": REGISTROS}
    amostra = definidos["amostras"]["sim_obitos"]
    assert amostra.height == REGISTROS
    # Labels from the dictionary, and the harmonised categories of a validated source.
    assert {"sexo", "sexo_rotulo", "idade_anos_completos"} <= set(amostra.columns)
    assert definidos["perfil"]["registros"].sum() == REGISTROS
    assert len(definidos["consulta"]) == 100  # the SQL cell's starting query
    citacao = definidos["citacoes"]["sim_obitos"]
    assert SHA256 in citacao
    assert filename_for(sus.resolve("sim_obitos"), ESCOPO) in citacao


def _planilha(conteudo: bytes, aba: str) -> pl.DataFrame:
    """One sheet of the dictionary workbook, every cell as text."""
    return pl.read_excel(conteudo, sheet_name=aba, infer_schema_length=0)


def test_each_tab_downloads_a_workbook_of_its_columns_and_of_the_codes_it_labels(importado):
    """Sheet `colunas`: one row per column of the lake table. Sheet `codigos`: one row
    per code, with the label the table shows."""
    _, definidos, _ = importado
    descricao = sus.describe_dataset("sim_obitos")
    esquema = definidos["esquemas"]["sim_obitos"]

    nome, conteudo = definidos["dicionarios"]["sim_obitos"]
    colunas = _planilha(conteudo, "colunas")
    codigos = _planilha(conteudo, "codigos")
    na_tabela = definidos["amostras"]["sim_obitos"].select("sexo", "sexo_rotulo").drop_nulls()

    assert nome == f"sim_obitos_dicionario_{descricao['dictionary_version']}.xlsx"
    assert colunas.select("coluna", "tipo_no_lake").rows() == list(esquema.items())
    # Every code of every column in the lake table; the blank code is an empty cell.
    assert set(codigos.iter_rows()) == {
        (f["field"]["name"], c["value"] or None, c["label"])
        for f in descricao["fields"]
        if f["field"]["name"] in esquema
        for c in f["field"]["codes"]
    }
    assert set(na_tabela.unique().iter_rows()) <= set(
        codigos.filter(coluna="sexo").select("codigo", "rotulo").iter_rows()
    )
    sexo = colunas.filter(coluna="sexo").row(0, named=True)
    fonte = next(d for d in descricao["sources"] if d["sha256"] == sexo["fonte_sha256"])
    assert (sexo["no_dicionario"], sexo["titulo"], sexo["fonte"], sexo["onde"]) == (
        "sim",
        "Sexo",
        fonte["url"],
        "Linha10 SEXO p. 2",
    )
    # The note says what a `conflicting` map conflicts with.
    tipobito = colunas.filter(coluna="tipobito").row(0, named=True)
    assert tipobito["conferencia"] == "conflicting"
    assert "cnv-difere-do-mapa-anterior" in tipobito["nota"]
    # A date the lake keeps as published text; with no codes, nothing was conferred.
    dtobito = colunas.filter(coluna="dtobito").row(0, named=True)
    assert (dtobito["tipo_no_lake"], dtobito["tipo_no_dicionario"], dtobito["conferencia"]) == (
        "VARCHAR",
        "date",
        None,
    )
    # Codes are text cells: `00` keeps its zero in a spreadsheet.
    assert "00" in codigos.filter(coluna="escfalagr1")["codigo"].to_list()
    # A source is plain text: several URLs in one cell would make one broken link.
    with zipfile.ZipFile(io.BytesIO(conteudo)) as planilha:
        folhas = [n for n in planilha.namelist() if n.startswith("xl/worksheets/sheet")]
        assert not [n for n in folhas if b"<hyperlink" in planilha.read(n)]


def test_the_workbook_lists_every_column_of_the_table_also_those_the_dictionary_lacks(
    monkeypatch, tmp_path
):
    """The CNES dictionary describes a few of the columns of the ST file."""
    arquivo = ROOT / "tests" / "fixtures" / "dbc" / "cnes_rr_2024_01_mini.dbc"
    escopo = ScopeKey(uf="RR", ano=2024, mes=1)
    fake_datasus.serve(monkeypatch, "cnes_estabelecimentos", {escopo: arquivo.read_bytes()})

    definidos = _importar(
        monkeypatch, tmp_path, "--base", "cnes_estabelecimentos", "--anos", "2024", "--meses", "1"
    )
    colunas = _planilha(definidos["dicionarios"]["cnes_estabelecimentos"][1], "colunas")
    descritas = {
        f["field"]["name"] for f in sus.describe_dataset("cnes_estabelecimentos")["fields"]
    }

    assert colunas["coluna"].to_list() == list(definidos["esquemas"]["cnes_estabelecimentos"])
    fora = set(colunas.filter(no_dicionario="não")["coluna"])
    assert fora == set(colunas["coluna"]) - descritas
    assert len(fora) > len(descritas)


def test_a_table_outside_the_dataset_registry_offers_its_packaged_dictionary(
    monkeypatch, tmp_path
):
    """`aux_sigtap_procedimentos`, which `sus.import_sigtap` publishes, is not a dataset of
    `sus.datasets()` but has a dictionary in the package."""
    nomes = ROOT / "tests" / "fixtures" / "listings" / "sigtap_tup_downloads_nlst.txt.gz"
    zip_200801 = ROOT / "tests" / "fixtures" / "sigtap" / "TabelaUnificada_200801.zip"
    monkeypatch.setattr(
        sigtap, "list_names", lambda: gzip.decompress(nomes.read_bytes()).decode().splitlines()
    )
    monkeypatch.setattr(
        sigtap, "download", lambda _: (zip_200801.read_bytes(), "2009-01-08T00:00")
    )
    sus.import_sigtap(years=[2008], months=[1], target=f"ducklake:{tmp_path / 'omnisus.ducklake'}")

    definidos = _rodar(monkeypatch, "--lake", str(tmp_path))

    assert definidos["dicionarios"]["aux_sigtap_procedimentos"][0] == (
        "aux_sigtap_procedimentos_dicionario_"
        f"{sus.describe_dataset('aux_sigtap_procedimentos')['dictionary_version']}.xlsx"
    )


def test_a_reimport_counts_as_already_in_the_lake_and_an_unlisted_scope_as_not_published(
    importado, monkeypatch
):
    pasta, _, _ = importado
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
    de_novo = _importar(monkeypatch, pasta)["relatorio"]
    fake_datasus.serve(monkeypatch, "sim_obitos", {})
    ausente = _importar(monkeypatch, pasta)["relatorio"]

    assert de_novo["situacao"].to_list() == ["já estava no lake"]
    assert ausente["situacao"].to_list() == ["o DATASUS não publica"]
    assert "not in the server listing" in ausente["motivo"].item()


def test_a_failed_download_is_reported_and_a_second_click_imports_only_what_is_missing(
    monkeypatch, tmp_path
):
    arquivos = {ESCOPO: ARQUIVO.read_bytes(), ESCOPO_2023: ARQUIVO_2023.read_bytes()}
    fake_datasus.serve(monkeypatch, "sim_obitos", arquivos)
    baixar = _runner.fetch_dbc_bytes

    async def falha_em_2023(entry, **kw):
        if entry.name.endswith("2023.dbc"):
            raise ConnectionResetError(f"{entry.path}: connection reset by peer")
        return await baixar(entry, **kw)

    monkeypatch.setattr(_runner, "fetch_dbc_bytes", falha_em_2023)
    antes = _importar(monkeypatch, tmp_path, "--anos", "2022,2023")
    baixados = fake_datasus.serve(monkeypatch, "sim_obitos", arquivos)
    # Repeated, as a shell user may also write it.
    depois = _importar(monkeypatch, tmp_path, "--anos", "2022", "--anos", "2023")

    assert antes["relatorio"]["situacao"].to_list() == ["importado", "falhou ao baixar"]
    assert "connection reset by peer" in antes["relatorio"]["motivo"][1]
    assert antes["totais"] == {"sim_obitos": REGISTROS}
    assert depois["relatorio"]["situacao"].to_list() == ["já estava no lake", "importado"]
    assert [p.rsplit("/", 1)[1] for p in baixados] == ["DORR2023.dbc"]
    assert depois["totais"] == {"sim_obitos": REGISTROS + _registros(ARQUIVO_2023)}


def test_imports_the_chosen_months_of_a_monthly_base_in_order(monkeypatch, tmp_path):
    arquivo = ROOT / "tests" / "fixtures" / "dbc" / "sih_er_rr_2024_01_mini.dbc"
    janeiro = ScopeKey(uf="RR", ano=2024, mes=1)
    fake_datasus.serve(monkeypatch, "sih_aih_rejeitada_erro", {janeiro: arquivo.read_bytes()})

    definidos = _importar(
        monkeypatch,
        tmp_path,
        "--base",
        "sih_aih_rejeitada_erro",
        "--anos",
        "2024",
        "--meses",
        "2,1",
    )

    assert definidos["relatorio"]["escopo", "situacao"].rows() == [
        ("RR_2024_01", "importado"),
        ("RR_2024_02", "o DATASUS não publica"),
    ]
    assert definidos["totais"] == {"sih_aih_rejeitada_erro": _registros(arquivo)}


def test_a_command_line_year_outside_the_base_coverage_is_left_out(monkeypatch, tmp_path):
    """The SIM in CID-9 ends in 1995; the widgets still open, with no year chosen."""
    definidos = _rodar(
        monkeypatch, "--lake", str(tmp_path), "--base", "sim_obitos_cid9", "--anos", "1995,2022"
    )

    assert definidos["anos_novos"].value == [1995]
    assert [str(e) for e in definidos["escopos_novos"]] == ["RR_1995"]


def test_only_true_turns_a_command_line_switch_on(monkeypatch, tmp_path):
    """marimo makes only true/false booleans; `--substituir no` must not re-download
    every scope, and `--executar no` must not import."""
    for valor in ("no", "nao", "off", "FALSE"):
        definidos = _rodar(
            monkeypatch, "--lake", str(tmp_path), "--substituir", valor, "--executar", valor
        )
        assert (definidos["substituir"].value, definidos["executar"]) == (False, False), valor
        assert "relatorio" not in definidos
    assert _rodar(monkeypatch, "--lake", str(tmp_path), "--substituir", "true")["substituir"].value


def test_command_line_ufs_take_lowercase(monkeypatch, tmp_path):
    definidos = _rodar(monkeypatch, "--lake", str(tmp_path), "--ufs", "rr,ap")

    assert [str(e) for e in definidos["escopos_novos"]] == ["AP_2022", "RR_2022"]


def test_a_scope_imported_by_another_omnisus_version_asks_for_and_takes_substituir(
    monkeypatch, tmp_path
):
    """A new parser version (another omnisus release or dictionary) on the same file."""
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
    sus.import_dataset(
        "sim_obitos", scopes=[ESCOPO], target=f"ducklake:{tmp_path / 'omnisus.ducklake'}"
    )
    versao = _runner.parser_version
    monkeypatch.setattr(_runner, "parser_version", lambda d: versao(d) + "-nova")

    texto, recusado = _executar(monkeypatch, "--lake", str(tmp_path), "--executar", "true")
    substituido = _importar(monkeypatch, tmp_path, "--substituir", "true")["relatorio"]

    assert recusado["relatorio"]["situacao"].to_list() == ["falhou ao gravar"]
    assert "request replace explicitly" in recusado["relatorio"]["motivo"].item()
    assert "os desfeitos da mesma parte entram no clique seguinte" in texto
    assert substituido["situacao"].to_list() == ["importado"]


def test_another_writer_on_the_lake_stops_the_import_with_a_message(monkeypatch, tmp_path):
    """As when the notebook is open in two tabs, or `sus.load` runs in a terminal."""
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})

    with sus.Lake.local(f"ducklake:{tmp_path / 'omnisus.ducklake'}"):
        definidos = _importar(monkeypatch, tmp_path)

    assert "Outro processo está gravando neste lake" in definidos["parada"]
    assert definidos["relatorio"]["situacao"].to_list() == ["não tentado"]


def test_an_aborted_write_shows_its_innermost_cause_and_leaves_the_scope_unresolved(
    monkeypatch, tmp_path
):
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})

    def commit_incerto(*_a, **_kw):
        try:
            raise OSError("database is locked")
        except OSError as e:
            raise CommitOutcomeUnknown("commit outcome unknown; inspect before retry") from e

    monkeypatch.setattr(_runner, "publish_staged", commit_incerto)
    definidos = _importar(monkeypatch, tmp_path)

    assert "database is locked" in definidos["parada"]
    assert definidos["relatorio"]["situacao"].to_list() == ["sem resultado"]


def test_a_full_disk_stops_the_import_instead_of_downloading_the_rest(monkeypatch, tmp_path):
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})

    def disco_cheio(*_a, **_kw):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(_runner, "stage_raw", disco_cheio)
    definidos = _importar(monkeypatch, tmp_path, "--ufs", TODAS_AS_UFS)

    assert "Disco cheio" in definidos["parada"]
    assert definidos["relatorio"].filter(escopo="RR_2022")["situacao"].item() == "falhou ao gravar"
    assert definidos["relatorio"]["situacao"].to_list()[-3:] == ["não tentado"] * 3


def test_an_unexpected_error_becomes_a_message_and_keeps_the_report(monkeypatch, tmp_path):
    """Such as a listing that names one scope in two directories."""

    def listagem_incoerente(d, **_kw):
        raise ValueError("sim_obitos: RR_2022 is published as both final and prelim")

    monkeypatch.setattr(_runner, "list_sources", listagem_incoerente)
    definidos = _importar(monkeypatch, tmp_path)

    assert "ValueError: sim_obitos: RR_2022 is published as both" in definidos["parada"]
    assert definidos["relatorio"]["situacao"].to_list() == ["não tentado"]


def test_when_the_server_stops_answering_what_was_imported_stays_and_the_rest_is_not_tried(
    monkeypatch, tmp_path
):
    """The import runs in parts; a part that fails stops the rest, not the parts before it."""
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
    listar = _runner.list_sources
    listagens = []

    def responde_uma_vez(d, **kw):
        listagens.append(d.name)
        if len(listagens) > 1:
            # ftplib raises a bare EOFError when the server drops the connection.
            erro = sus.FtpUnavailable("/dissemin/publicos/SIM/CID10/DORES: 3 attempts failed")
            raise erro from EOFError()
        return listar(d, **kw)

    monkeypatch.setattr(_runner, "list_sources", responde_uma_vez)
    definidos = _importar(monkeypatch, tmp_path, "--ufs", TODAS_AS_UFS)
    relatorio = definidos["relatorio"]

    assert relatorio.height == len(sus.ALL_UFS)
    assert relatorio.filter(escopo="RR_2022")["situacao"].item() == "importado"
    assert relatorio["situacao"].value_counts(sort=True).rows() == [
        ("o DATASUS não publica", len(sus.ALL_UFS) - 4),
        ("não tentado", 3),
        ("importado", 1),
    ]
    assert (
        "não respondeu (/dissemin/publicos/SIM/CID10/DORES: 3 attempts failed)"
        in definidos["parada"]
    )
    assert definidos["totais"] == {"sim_obitos": REGISTROS}


def test_an_interrupt_leaves_the_running_part_without_result_and_the_rest_not_tried(
    monkeypatch, tmp_path
):
    """In marimo the running part ends before the interrupt reaches the cell; its report
    is lost, so its scopes have no result."""
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
    listar = _runner.list_sources
    listagens = []

    def interrompe_na_segunda(d, **kw):
        listagens.append(d.name)
        if len(listagens) == 2:
            raise KeyboardInterrupt
        return listar(d, **kw)

    monkeypatch.setattr(_runner, "list_sources", interrompe_na_segunda)
    definidos = _importar(monkeypatch, tmp_path, "--anos", "2021,2022", "--ufs", TODAS_AS_UFS)

    assert definidos["parada"].startswith("Interrompido.")
    assert definidos["relatorio"]["situacao"].value_counts(sort=True).rows() == [
        ("o DATASUS não publica", 24),
        ("sem resultado", 24),
        ("não tentado", 2 * len(sus.ALL_UFS) - 48),
    ]


def test_a_report_of_many_scopes_keeps_a_reason_that_comes_after_the_first_hundred(
    monkeypatch, tmp_path
):
    """The newest year comes last and is often not published yet."""

    def importa_ate_2022(dataset, *, scopes, **_kw):
        return sus.ImportReport(
            tuple(
                sus.ScopeOutcome(s, "ok")
                if s.ano < 2023
                else sus.ScopeOutcome(s, "skipped", reason="not in the listing", code="not_listed")
                for s in scopes
            )
        )

    monkeypatch.setattr(sus, "import_dataset", importa_ate_2022)
    relatorio = _importar(
        monkeypatch, tmp_path, "--anos", "2019,2020,2021,2022,2023", "--ufs", TODAS_AS_UFS
    )["relatorio"]

    assert relatorio.height == 5 * len(sus.ALL_UFS)
    assert relatorio.row(-1) == ("TO_2023", "o DATASUS não publica", "not in the listing")


def test_the_free_disk_line_survives_a_folder_it_cannot_read(monkeypatch, tmp_path):
    """As a Google Drive or network folder that is not mounted, or one macOS protects."""

    def sem_permissao(_pasta):
        raise PermissionError(13, "Operation not permitted")

    monkeypatch.setattr(shutil, "disk_usage", sem_permissao)
    texto, definidos = _executar(monkeypatch, "--lake", str(tmp_path / "nao" / "existe"))

    assert "Disco livre: ? GiB na pasta do lake" in texto
    assert [str(e) for e in definidos["escopos_novos"]] == ["RR_2022"]
    assert not (tmp_path / "nao").exists()


def test_a_base_without_chosen_scopes_has_no_rows_and_no_citation(importado, monkeypatch):
    pasta, _, _ = importado

    texto, definidos = _executar(
        monkeypatch, "--lake", str(pasta), defs={"escolhidas": {"sim_obitos": []}}
    )

    assert definidos["totais"] == {"sim_obitos": 0}
    assert definidos["amostras"]["sim_obitos"].height == 0
    assert definidos["perfil"]["registros"].sum() == 0
    assert definidos["citacoes"] == {}
    assert "Nenhum escopo escolhido para citar." in texto
    assert "Baixar citação" not in texto
    assert "Baixar o dicionário (XLSX)" in texto  # the tab still offers its dictionary
    # With no scope there is no source to validate, so no category is "left out".
    assert "Categorias harmonizadas fora" not in texto
    # The harmonised columns come last; the tab's table shows every column, not the first 50.
    assert "data-max-columns='&quot;all&quot;'" in texto


def test_the_row_limit_caps_the_table_but_not_the_counts(importado, monkeypatch):
    pasta, _, _ = importado

    texto, definidos = _executar(monkeypatch, "--lake", str(pasta), "--linhas", "100")

    assert definidos["amostras"]["sim_obitos"].height == 100
    assert definidos["totais"] == {"sim_obitos": REGISTROS}
    assert definidos["perfil"]["registros"].sum() == REGISTROS
    # Numbers as written in Portuguese: 3.246, not 3,246 (which reads as about 3).
    assert f"{REGISTROS:,}".replace(",", ".") in texto
    assert f"{REGISTROS:,}" not in texto
    # The lake has only an annual base, so Escolher shows no Meses filter.
    assert "Meses" not in texto


def test_without_lake_it_opens_the_folder_sus_load_writes_to(importado, monkeypatch, tmp_path):
    """$OMNISUS_DATA_DIR, else data/raw under the working directory, as `data_dir()` says."""
    pasta, _, _ = importado
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMNISUS_DATA_DIR", str(pasta))

    definidos = _rodar(monkeypatch)

    assert definidos["diretorio"] == data_dir().resolve()
    assert definidos["totais"] == {"sim_obitos": REGISTROS}
    monkeypatch.delenv("OMNISUS_DATA_DIR")
    assert _rodar(monkeypatch)["diretorio"] == data_dir().resolve()
    # A literal `~` (as from a .env file) is not the home folder for `sus.load` either.
    monkeypatch.setenv("OMNISUS_DATA_DIR", "~/omnisus")
    assert _rodar(monkeypatch)["diretorio"] == data_dir().resolve()


def test_reads_the_lake_after_its_folder_moved(monkeypatch, tmp_path):
    """As when the folder is copied from Google Drive to another computer or to molab:
    the catalog records the absolute path where the lake was created."""
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})
    sus.import_dataset(
        "sim_obitos",
        scopes=[ESCOPO],
        target=f"ducklake:{tmp_path / 'criado' / 'omnisus.ducklake'}",
    )
    shutil.move(tmp_path / "criado", tmp_path / "copiado")

    depois = _importar(monkeypatch, tmp_path / "copiado")

    assert depois["totais"] == {"sim_obitos": REGISTROS}
    assert depois["amostras"]["sim_obitos"].height == REGISTROS
    assert SHA256 in depois["citacoes"]["sim_obitos"]
    # It only reads there: an import goes to the folder where the lake was created.
    assert "pasta onde foi criado" in depois["parada"]
    assert depois["relatorio"]["situacao"].to_list() == ["não tentado"]


def test_a_reader_holding_the_catalog_stops_the_import_with_a_message(monkeypatch, tmp_path):
    """Another notebook or DuckDB session with a read transaction open on the lake makes
    the writer fail while setting its options, after SQLite's 5 s busy timeout; this
    raises at once what `Lake.local` raises then."""

    def catalogo_ocupado(*_a, **_kw):
        raise sus.CatalogAttachError("set_option", "TransactionException")

    monkeypatch.setattr(sus, "import_dataset", catalogo_ocupado)
    definidos = _importar(monkeypatch, tmp_path)

    assert "outro programa está lendo este lake" in definidos["parada"]
    assert definidos["relatorio"]["situacao"].to_list() == ["não tentado"]


def test_the_last_report_stays_while_the_widgets_change(importado, monkeypatch):
    """The warning asks to import some scopes again with *Substituir* on: changing the
    widgets reruns the import cell without a click, and the report that names those
    scopes stays until the next click."""
    pasta, _, _ = importado
    relatorio = pl.DataFrame(
        {"escopo": ["RR_2022"], "situacao": ["falhou ao gravar"], "motivo": ["replace"]}
    )
    ultima = ("Veja o motivo de cada escopo.", "warn", "falhou ao gravar: 1", relatorio)
    estado = {
        "versao": lambda: 0,
        "mudar_versao": lambda _v: None,
        "ultima": lambda: ultima,
        "guardar_ultima": lambda _v: None,
    }

    texto, definidos = _executar(monkeypatch, "--lake", str(pasta), defs=estado)

    assert "relatorio" not in definidos  # no click, no import
    assert "falhou ao gravar: 1" in texto
    assert "Veja o motivo de cada escopo." in texto


def test_the_rows_open_on_the_base_the_command_line_names(monkeypatch, tmp_path):
    """On a lake with other bases, `--base` is the one Escolher starts on, so an export
    shows and cites what it imported. An unvalidated source says why its categories
    are out, in Portuguese."""
    sih = ROOT / "tests" / "fixtures" / "dbc" / "sih_rr_2024_01_mini.dbc"
    janeiro = ScopeKey(uf="RR", ano=2024, mes=1)
    fake_datasus.serve(monkeypatch, "sih_aih_reduzida", {janeiro: sih.read_bytes()})
    sus.import_dataset(
        "sih_aih_reduzida", scopes=[janeiro], target=f"ducklake:{tmp_path / 'omnisus.ducklake'}"
    )
    fake_datasus.serve(monkeypatch, "sim_obitos", {ESCOPO: ARQUIVO.read_bytes()})

    sim = _importar(monkeypatch, tmp_path, "--base", "sim_obitos")
    texto, rd = _executar(monkeypatch, "--lake", str(tmp_path), "--base", "sih_aih_reduzida")

    assert sim["bases"].value == ["sim_obitos"]
    assert list(sim["citacoes"]) == ["sim_obitos"]
    assert rd["bases"].value == ["sih_aih_reduzida"]
    assert "porque nem todos os escopos vêm de fontes validadas" in texto
    assert "unconfirmed_source_scope" not in texto
