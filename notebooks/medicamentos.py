# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.0,<0.26",
#     "omnisus==0.2.0",
#     "polars>=1.44.2,<2.0",
# ]
# ///

"""Medicamentos: APAC de medicamentos (SIA-AM), estoque Hórus e o que não é público."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="Medicamentos")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import polars as pl

    import omnisus as sus
    from omnisus.sources.medicamentos import fetch_stock_page

    return Path, fetch_stock_page, json, mo, sus, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Medicamentos: o que dá para estudar com dados abertos

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py)

    Três partes:

    - **A · APAC de medicamentos (SIA-AM)** — as seis etapas do
      [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com
      **Roraima, janeiro de 2024**.
    - **B · Estoque BNAFAR/Hórus** — uma página da API pública de posição de estoque,
      guardada com procedência, sem publicar no lake.
    - **C · O que não existe publicamente** — eventos de dispensação.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`). Leia o
    [perfil de medicamentos](https://raphaelfh.github.io/omnisus/sources/medicamentos/)
    antes de interpretar números: um registro de APAC não é uma dose nem uma dispensação.
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute.
    BASE = "sia_apac_medicamentos"
    UF = "RR"
    ANO = 2024
    MES = 1
    CODIGO_UF = "14"  # parte B: código IBGE da UF
    DATA_ESTOQUE = ""  # parte B: AAAA-MM-DD, opcional
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, CODIGO_UF, DATA_ESTOQUE, MES, UF, executar


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A1 · O que a APAC de medicamentos registra

    Campos do dicionário da biblioteca (`sus.describe_dataset`), sem rede.
    """)
    return


@app.cell
def _(BASE, sus, pl):
    pl.DataFrame(
        [
            {"campo": f["name"], "tipo": f["type"], "rótulo": f.get("label", "")}
            for f in sus.describe_dataset(BASE)["schema"]["fields"]
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A2 · Descobrir

    `sus.available` lista agora o FTP do DATASUS: um arquivo por UF e mês.
    """)
    return


@app.cell
def _(BASE, UF, executar, mo, sus, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = sus.available(BASE, ufs=[UF], refresh=True)
    pl.DataFrame(publicados).sort("ano", "mes", descending=True)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A3 · Baixar e ler

    `sus.load` importa o recorte para o lake e devolve as linhas, com os códigos como
    o DATASUS publicou. Rodar de novo não baixa nem duplica nada.
    """)
    return


@app.cell
def _(ANO, BASE, MES, UF, executar, mo, sus):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    dados = sus.load(BASE, years=[ANO], ufs=[UF], months=[MES])
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A4 · Conferir

    `sus.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. O SIA é publicado num único diretório, então `sus.outdated` não se
    aplica.
    """)
    return


@app.cell
def _(BASE, dados, sus):
    sus.check_columns(BASE, dados)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A5 · Analisar

    Registros de APAC por procedimento principal e valor aprovado. Não são doses nem
    pacientes únicos.
    """)
    return


@app.cell
def _(dados, pl):
    tabelas = {
        "apac_por_procedimento_principal": dados.group_by(procedimento_principal="ap_pripal")
        .agg(apac=pl.len(), valor_aprovado=pl.col("ap_vl_ap").sum().round(2))
        .sort("apac", descending=True)
    }
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## A6 · Citar e guardar

    `sus.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake. As
    tabelas e a citação vão para `resultados/sia_apac_medicamentos/`.
    """)
    return


@app.cell
def _(BASE, Path, sus, tabelas):
    with sus.LakeReader() as _lake:
        citacao = sus.cite(_lake, dataset=BASE)
    pasta = Path("resultados") / BASE
    pasta.mkdir(parents=True, exist_ok=True)
    for _nome, _tabela in tabelas.items():
        _tabela.write_csv(pasta / f"{_nome}.csv")
    (pasta / "citacao.txt").write_text(citacao.text, encoding="utf-8")
    print(citacao.text)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## B · Estoque BNAFAR/Hórus

    Uma página da API pública de **posição de estoque**. Não publica no lake. Uma
    página vazia não demonstra ausência de estoque, e uma página curta não demonstra
    completude. Filtros: `CODIGO_UF` e `DATA_ESTOQUE`. A resposta e a procedência
    vão para `resultados/estoque/<sha256>/`.
    """)
    return


@app.cell
def _(CODIGO_UF, DATA_ESTOQUE, Path, executar, fetch_stock_page, json, mo, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` para consultar o estoque."))
    _filtros = {"codigo_uf": CODIGO_UF}
    if DATA_ESTOQUE:
        _filtros["data_posicao_estoque"] = DATA_ESTOQUE
    pagina = fetch_stock_page(filters=_filtros, limit=20)
    pasta_estoque = Path("resultados") / "estoque" / pagina.sha256
    pasta_estoque.mkdir(parents=True, exist_ok=True)
    (pasta_estoque / "resposta.json").write_bytes(pagina.raw)
    (pasta_estoque / "procedencia.json").write_text(
        json.dumps(pagina.provenance(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    pl.DataFrame(pagina.records)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## C · O que não existe publicamente

    A investigação de 2026-09-12
    ([relatório](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-12-sinan-e-dispensacao.md),
    Parte 2) não encontrou **nenhuma fonte pública de eventos de dispensação**: a
    dispensação enviada à BNAFAR e à RNDS tem envio ou acesso autenticado. Estoque,
    entrega a DSEI e indicadores agregados não substituem dispensação. Para pesquisar
    dispensação, o caminho é uma extração fornecida pelo gestor.
    """)
    return


if __name__ == "__main__":
    app.run()
