# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.1,<0.26",
#     "omnisus==0.2.3",
#     "polars>=1.44.2,<2.0",
# ]
# ///

"""SINAN · notificações nacionais de Chagas aguda, hanseníase e tuberculose, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="SINAN · Chagas, hanseníase e tuberculose")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import polars as pl

    import omnisus as sus

    return Path, mo, sus, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # SINAN · Chagas aguda, hanseníase e tuberculose

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py)

    Notificações do Sistema de Informação de Agravos de Notificação (SINAN),
    publicadas pelo DATASUS em **um arquivo nacional por ano**, com diretório final e
    preliminar. Este notebook percorre as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com
    **Chagas aguda, 2023** (troque `BASE` para `sinan_hanseniase` ou `sinan_tuberculose`).

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).

    Antes de contar, leia as Armadilhas do perfil do agravo:
    [Chagas](https://raphaelfh.github.io/omnisus/sources/sinan_chagas/#armadilhas),
    [hanseníase](https://raphaelfh.github.io/omnisus/sources/sinan_hanseniase/#armadilhas) e
    [tuberculose](https://raphaelfh.github.io/omnisus/sources/sinan_tuberculose/#armadilhas).
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute. BASE é o `name` de uma linha do SINAN em
    # `sus.describe_datasets()`; veja bases.py.
    BASE = "sinan_chagas"
    ANO = 2023
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, executar


@app.cell(hide_code=True)
def _(BASE, mo):
    mo.md(f"""
    ## 1 · O que `{BASE}` registra

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
    ## 2 · Descobrir

    `sus.available_releases` lista agora os diretórios final e preliminar. Um ano
    preliminar pode ser revisado e depois movido para o final com o mesmo nome. Se não
    há nenhum arquivo da base, o notebook para aqui.
    """)
    return


@app.cell
def _(BASE, executar, mo, sus, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = sus.available_releases(BASE, refresh=True)
    (
        pl.DataFrame(
            [
                {"ano": e.ano, "abrangencia": "nacional", "diretorio": d}
                for e, d in publicados.items()
            ]
        ).sort("ano", descending=True)
        if publicados
        else mo.md(f"O DATASUS não lista `{BASE}`. Troque `BASE` na célula de parâmetros.")
    )
    return (publicados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3 · Baixar e ler

    `sus.load` importa o ano para o lake e devolve as linhas, com os códigos como o
    DATASUS publicou. O arquivo é nacional: não há filtro de UF na importação; filtre
    a geografia dos registros depois, na análise.
    """)
    return


@app.cell
def _(ANO, BASE, mo, publicados, sus):
    mo.stop(not publicados, mo.md("Nada a baixar: o servidor não lista o recorte."))
    dados = sus.load(BASE, years=[ANO])
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

    `sus.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. `sus.outdated` lista os anos que o DATASUS republicou ou moveu entre
    preliminar e final desde a importação; atualize-os com
    `sus.load(..., policy="replace")`.
    """)
    return


@app.cell
def _(BASE, dados, mo, sus):
    with sus.LakeReader() as _lake:
        _republicados = sus.outdated(BASE, lake=_lake)
    mo.vstack(
        [
            mo.md(f"Republicados desde a importação: {_republicados or 'nenhum'}"),
            sus.check_columns(BASE, dados),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5 · Analisar

    `sus.label` põe o rótulo do dicionário ao lado de cada código. Confira o
    dicionário oficial antes de selecionar casos confirmados ou calcular incidência.
    """)
    return


@app.cell
def _(BASE, dados, sus, pl):
    tabelas = {
        "diretorio_de_origem": dados.group_by(diretorio="_source_release").len("notificacoes"),
        "notificacoes_por_uf_de_notificacao": dados.group_by(uf_notificacao_ibge="sg_uf_not")
        .len("notificacoes")
        .sort("notificacoes", descending=True),
        "notificacoes_por_uf_de_residencia": dados.group_by(
            uf_residencia_ibge=pl.col("id_mn_resi").str.slice(0, 2)
        )
        .len("notificacoes")
        .sort("notificacoes", descending=True),
    }
    if BASE == "sinan_chagas":
        tabelas["classificacao_e_evolucao"] = (
            sus.label(BASE, dados, columns=["classi_fin", "evolucao"])
            .group_by("classi_fin", "classi_fin_rotulo", "evolucao", "evolucao_rotulo")
            .len("notificacoes")
            .sort("classi_fin", "evolucao")
        )
    elif BASE == "sinan_hanseniase":
        tabelas["modo_de_entrada_e_alta"] = (
            sus.label(BASE, dados, columns=["tpalta_n"])
            .group_by("modoentr", "tpalta_n", "tpalta_n_rotulo")
            .len("notificacoes")
            .sort("modoentr", "tpalta_n")
        )
    elif BASE == "sinan_tuberculose":
        tabelas["tipo_de_entrada_e_encerramento"] = (
            sus.label(BASE, dados, columns=["tratamento", "situa_ence"])
            .group_by("tratamento", "tratamento_rotulo", "situa_ence", "situa_ence_rotulo")
            .len("notificacoes")
            .sort("tratamento", "situa_ence")
        )
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    `sus.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação do agravo. As tabelas e a citação vão para `resultados/<BASE>/`. Veja
    [Reprodutibilidade](https://raphaelfh.github.io/omnisus/pesquisa/reprodutibilidade/).
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


if __name__ == "__main__":
    app.run()
