# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.0,<0.26",
#     "omnisus",
#     "polars>=1.44.2,<2.0",
# ]
#
# [tool.uv.sources]
# omnisus = { git = "https://github.com/raphaelfh/omnisus.git", rev = "6df1890e81cbb250306d5d98294b49b73c391a7a" }
# ///

"""SIA · produção ambulatorial: sete tabelas do DATASUS, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="SIA · produção ambulatorial")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import polars as pl

    import omnisus as odb

    return Path, mo, odb, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # SIA · produção ambulatorial

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py)

    O Sistema de Informações Ambulatoriais do SUS (SIA/SUS) é publicado pelo DATASUS
    em várias tabelas, por UF e mês; este notebook trata sete. Escolha uma em `BASE`
    na célula de parâmetros e siga as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/)
    com um recorte pequeno: **Roraima, janeiro de 2024**.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).

    Cada tabela registra uma coisa diferente. Antes de interpretar números, leia o
    [perfil do SIA](https://raphaelfh.github.io/omnisus/sources/sia/).
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute. BASE é uma de:
    # sia_bpa_individualizado (BPA individualizado), sia_apac_medicamentos,
    # sia_apac_quimioterapia, sia_apac_tratamento_dialitico, sia_apac_laudos_diversos,
    # sia_apac_cirurgia_bariatrica (APAC) e sia_psicossocial (RAAS).
    BASE = "sia_bpa_individualizado"
    UF = "RR"
    ANO = 2024
    MES = 1
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, MES, UF, executar


@app.cell(hide_code=True)
def _(BASE, mo):
    mo.md(f"""
    ## 1 · O que a tabela `{BASE}` registra

    Campos do dicionário da biblioteca (`odb.describe_dataset`), sem rede.
    """)
    return


@app.cell
def _(BASE, odb, pl):
    pl.DataFrame(
        [
            {"campo": f["name"], "tipo": f["type"], "rótulo": f.get("label", "")}
            for f in odb.describe_dataset(BASE)["schema"]["fields"]
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2 · Descobrir

    `odb.available` lista agora os arquivos da tabela no FTP do DATASUS. Nem toda
    tabela existe para toda UF e mês.
    """)
    return


@app.cell
def _(BASE, UF, executar, mo, odb, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = odb.available(BASE, ufs=[UF], refresh=True)
    pl.DataFrame(publicados).sort("ano", "mes", descending=True)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3 · Baixar e ler

    `odb.load` importa o recorte para o lake e devolve as linhas, com os códigos como
    o DATASUS publicou. Rodar de novo não baixa nem duplica nada.
    """)
    return


@app.cell
def _(ANO, BASE, MES, UF, executar, mo, odb):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    dados = odb.load(BASE, years=[ANO], ufs=[UF], months=[MES])
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

    `odb.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. O SIA é publicado num único diretório, então `odb.outdated` não se
    aplica.
    """)
    return


@app.cell
def _(BASE, dados, odb):
    odb.check_columns(BASE, dados)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5 · Analisar

    Três tabelas têm uma análise própria; nas outras, a etapa mostra só a contagem.
    Use o dicionário da etapa 1 e o perfil.
    """)
    return


@app.cell
def _(BASE, dados, pl):
    if BASE == "sia_bpa_individualizado":
        tabelas = {
            "quantidade_por_procedimento": dados.group_by(procedimento="proc_id")
            .agg(registros=pl.len(), quantidade_aprovada=pl.col("qt_aprov").sum())
            .sort("quantidade_aprovada", descending=True, nulls_last=True)
        }
    elif BASE == "sia_apac_medicamentos":
        tabelas = {
            "apac_por_procedimento_principal": dados.group_by(procedimento_principal="ap_pripal")
            .agg(apac=pl.len(), valor_aprovado=pl.col("ap_vl_ap").sum().round(2))
            .sort("apac", descending=True)
        }
    elif BASE == "sia_psicossocial":
        tabelas = {
            "acoes_por_cid_principal": dados.group_by(
                acao_realizada="pa_proc_id", cid10_principal=pl.col("cidpri").str.to_uppercase()
            )
            .len("registros")
            .sort("registros", descending=True)
        }
    else:
        tabelas = {"registros_no_recorte": dados.select(registros=pl.len())}
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    `odb.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação da tabela. As tabelas e a citação vão para `resultados/<BASE>/`. Veja
    [Reprodutibilidade](https://raphaelfh.github.io/omnisus/pesquisa/reprodutibilidade/).
    """)
    return


@app.cell
def _(BASE, Path, odb, tabelas):
    with odb.LakeReader() as _lake:
        citacao = odb.cite(_lake, dataset=BASE)
    pasta = Path("resultados") / BASE
    pasta.mkdir(parents=True, exist_ok=True)
    for _nome, _tabela in tabelas.items():
        _tabela.write_csv(pasta / f"{_nome}.csv")
    (pasta / "citacao.txt").write_text(citacao.text, encoding="utf-8")
    print(citacao.text)
    return


if __name__ == "__main__":
    app.run()
