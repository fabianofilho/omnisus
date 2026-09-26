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

"""IBGE · população: uma edição explícita e óbitos por 100 mil, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="IBGE · população")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import polars as pl

    import omnisus as odb
    from omnisus.sources.ibge.products import CENSUS_YEARS, ESTIMATE_UNAVAILABLE_YEARS

    return CENSUS_YEARS, ESTIMATE_UNAVAILABLE_YEARS, Path, mo, odb, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # IBGE · população

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py)

    População municipal publicada pelo IBGE, importada de uma **edição explícita**:
    censo ou estimativa, e um ano. Este notebook percorre as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com o
    **censo de 2022** e calcula óbitos por 100 mil em Roraima com o SIM do mesmo ano.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).

    Censo e estimativa têm datas de referência diferentes. Leia o
    [perfil da população IBGE](https://raphaelfh.github.io/omnisus/sources/ibge_populacao/)
    e a página [Indicadores](https://raphaelfh.github.io/omnisus/pesquisa/indicadores/).
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute. PRODUTO é "census" ou "estimate".
    BASE = "ibge_populacao"
    PRODUTO = "census"
    ANO = 2022
    UF = "RR"  # sigla, para o SIM
    CODIGO_UF = "14"  # a mesma UF no código IBGE dos municípios
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, CODIGO_UF, PRODUTO, UF, executar


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1 · O que a base registra

    Colunas da visão `ibge_populacao`, do dicionário da biblioteca
    (`odb.describe_dataset`), sem rede.
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

    Não há inventário de arquivos: a biblioteca aceita edições conhecidas. Esta
    tabela vem do pacote, sem rede. Uma estimativa só é aceita na edição mais
    recente do agregado; anos recusados não têm universo territorial verificado.
    """)
    return


@app.cell
def _(CENSUS_YEARS, ESTIMATE_UNAVAILABLE_YEARS, pl):
    pl.DataFrame(
        [
            {"produto": "census", "anos": ", ".join(map(str, CENSUS_YEARS))},
            {
                "produto": "estimate",
                "anos_recusados": ", ".join(map(str, ESTIMATE_UNAVAILABLE_YEARS)),
            },
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3 · Baixar

    `odb.import_ibge_populacao` importa a edição para o mesmo lake do SIM, para
    poder calcular taxas. Uma edição já importada não é importada de novo: a visão
    `ibge_populacao` falha quando um município e ano têm duas publicações. As
    publicações do lake vêm de `odb.cite`.
    """)
    return


@app.cell
def _(ANO, BASE, PRODUTO, executar, mo, odb):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    try:
        with odb.LakeReader() as _lake:
            _edicoes = odb.cite(_lake, dataset=BASE).publications
    except (odb.CatalogAttachError, LookupError):  # o lake ainda não existe
        _edicoes = ()
    ja_importada = [e for e in _edicoes if e["product"] == PRODUTO and e["ano"] == ANO]
    if ja_importada:
        importadas = []
    else:
        importadas = odb.import_ibge_populacao(years=[ANO], census=PRODUTO == "census")
    {"ja_no_lake": ja_importada, "importadas_agora": importadas}
    return (importadas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

    A contagem lê a visão, que falharia se houvesse publicações ambíguas. O código
    IBGE tem 7 dígitos; o do SIM, 6.
    """)
    return


@app.cell
def _(ANO, importadas, odb, pl):
    with odb.LakeReader() as _lake:
        populacao = (
            _lake.connect().execute("SELECT * FROM lake.ibge_populacao WHERE ano = ?", [ANO]).pl()
        )
    {
        "edicoes_importadas_agora": len(importadas),
        "resumo": populacao.select(municipios=pl.len(), populacao_total=pl.col("populacao").sum()),
        "digitos_codigo_ibge": populacao.group_by(
            digitos=pl.col("codigo_ibge").str.len_chars()
        ).len("municipios"),
    }
    return (populacao,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5 · Analisar

    `odb.load` traz os óbitos do SIM da mesma UF e ano (nada de novo se já estiverem
    no lake). A taxa junta os municípios pelos **6 primeiros dígitos**
    (`odb.municipality_join_key`); os óbitos entram pelo município de residência
    (`codmunres`).
    """)
    return


@app.cell
def _(ANO, CODIGO_UF, UF, odb, pl, populacao):
    _municipio = pl.col("municipio").map_elements(
        odb.municipality_join_key, return_dtype=pl.String
    )
    obitos = (
        odb.load("sim_obitos", years=[ANO], ufs=[UF])
        .group_by(municipio="codmunres")
        .len("obitos")
        .with_columns(_municipio)
    )
    populacao_da_uf = (
        populacao.filter(pl.col("codigo_ibge").str.starts_with(CODIGO_UF))
        .select("codigo_ibge", "populacao", municipio="codigo_ibge")
        .with_columns(_municipio)
    )
    tabelas = {
        "populacao_por_municipio": populacao_da_uf.select("codigo_ibge", "populacao").sort(
            "populacao", descending=True
        ),
        "obitos_por_100_mil": populacao_da_uf.join(
            obitos.group_by("municipio").agg(pl.col("obitos").sum()), on="municipio"
        )
        .with_columns(
            obitos_por_100_mil=(100_000 * pl.col("obitos") / pl.col("populacao")).round(1)
        )
        .sort("municipio"),
    }
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    Uma taxa cita as duas bases: `odb.cite` nomeia a URL e o SHA-256 da edição do
    IBGE e o arquivo e o SHA-256 do SIM, com o snapshot do lake. As tabelas e a
    citação vão para `resultados/ibge_populacao/`. Veja
    [Reprodutibilidade](https://raphaelfh.github.io/omnisus/pesquisa/reprodutibilidade/).
    """)
    return


@app.cell
def _(BASE, Path, odb, tabelas):
    with odb.LakeReader() as _lake:
        citacao = "\n\n".join(odb.cite(_lake, dataset=base).text for base in (BASE, "sim_obitos"))
    pasta = Path("resultados") / BASE
    pasta.mkdir(parents=True, exist_ok=True)
    for _nome, _tabela in tabelas.items():
        _tabela.write_csv(pasta / f"{_nome}.csv")
    (pasta / "citacao.txt").write_text(citacao, encoding="utf-8")
    print(citacao)
    return


if __name__ == "__main__":
    app.run()
