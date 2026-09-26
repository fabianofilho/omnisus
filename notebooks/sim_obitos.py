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

"""SIM · óbitos: do arquivo do DATASUS a uma tabela citável, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="SIM · óbitos")


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
    # SIM · óbitos

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py)

    Base de óbitos do Sistema de Informações sobre Mortalidade (SIM), publicada
    pelo DATASUS. Este notebook percorre as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com um
    recorte pequeno: **Roraima, 2022**.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).

    Antes de interpretar números, leia o
    [perfil do SIM](https://raphaelfh.github.io/omnisus/sources/sim_obitos/):
    o que um registro representa, datas, geografia e armadilhas, com as fontes.
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute.
    BASE = "sim_obitos"
    UF = "RR"
    ANO = 2022
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, UF, executar


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1 · O que a base registra

    Campos do dicionário da biblioteca (`odb.describe_dataset`), sem rede. O
    significado dos códigos está no perfil e no documento oficial citado nele.
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

    `odb.available_releases` lista agora o FTP do DATASUS. O SIM tem um diretório
    final e um preliminar; a coluna `diretorio` diz onde cada ano está.
    """)
    return


@app.cell
def _(BASE, UF, executar, mo, odb, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = odb.available_releases(BASE, ufs=[UF], refresh=True)
    pl.DataFrame([{"uf": e.uf, "ano": e.ano, "diretorio": d} for e, d in publicados.items()]).sort(
        "ano", descending=True
    )
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
def _(ANO, BASE, UF, executar, mo, odb):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    dados = odb.load(BASE, years=[ANO], ufs=[UF])
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

    `odb.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. `odb.outdated` lista os escopos que o DATASUS republicou ou moveu do
    preliminar para o final desde a importação.
    """)
    return


@app.cell
def _(BASE, dados, mo, odb):
    with odb.LakeReader() as _lake:
        _republicados = odb.outdated(BASE, lake=_lake)
    mo.vstack(
        [
            mo.md(f"Republicados desde a importação: {_republicados or 'nenhum'}"),
            odb.check_columns(BASE, dados),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5 · Analisar

    `odb.label` põe o rótulo do dicionário ao lado de cada código (`sexo_rotulo`); um
    código que o dicionário não conhece fica sem rótulo. O perfil explica a
    diferença entre residência e ocorrência.
    """)
    return


@app.cell
def _(BASE, dados, odb, pl):
    obitos = odb.label(BASE, dados, columns=["sexo"])
    tabelas = {
        "obitos_por_mes": obitos.group_by(
            mes=pl.col("dtobito")
            .str.strptime(pl.Date, "%d%m%Y", strict=False)
            .dt.strftime("%Y-%m")
            .fill_null("sem data válida")
        )
        .len("obitos")
        .sort("mes"),
        "obitos_por_sexo_e_causa": obitos.group_by(
            "sexo", "sexo_rotulo", causa_basica_cid10_3=pl.col("causabas").str.slice(0, 3)
        )
        .len("obitos")
        .sort("obitos", descending=True),
        "residencia_e_ocorrencia": obitos.group_by(
            uf_residencia_ibge=pl.col("codmunres").str.slice(0, 2),
            uf_ocorrencia_ibge=pl.col("codmunocor").str.slice(0, 2),
        )
        .len("obitos")
        .sort("obitos", descending=True),
    }
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    `odb.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação da base. As tabelas e a citação vão para `resultados/sim_obitos/`;
    guarde a citação junto com o resultado. Veja
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
