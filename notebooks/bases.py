# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.1,<0.26",
#     "omnisus==0.2.3",
#     "polars>=1.44.2,<2.0",
# ]
# ///

"""Bases do DATASUS: a lista de todas e qualquer uma delas até a citação, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="Bases do DATASUS")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import polars as pl

    import omnisus as sus

    return Path, json, mo, sus, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Bases do DATASUS

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/bases.py)

    Todas as bases do FTP do DATASUS que o omnisus importa, numa tabela, e o caminho
    de qualquer uma delas até a citação. Escolha a base em `BASE` na célula de
    parâmetros e siga as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com um
    recorte pequeno: **Roraima, janeiro de 2024**, em `cnes_leitos`.

    Os notebooks de cada sistema (`sim_obitos.py`, `sia.py`, `sinan.py`...) põem
    rótulos e analisam a base; este só conta os registros do recorte, e por isso
    serve para qualquer base.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros e ponha
    `EXECUTAR = True` (ou exporte com `-- --executar true`) para consultar a rede e
    gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Que bases existem

    `sus.describe_datasets()` devolve uma linha por base, sem rede: o nome que vai em
    `BASE` (`name`), o sistema (`category`), o que é (`title`), como é publicada e
    desde quando. `geography` diz se `sus.load` pede `ufs` (`state`) ou se o arquivo é
    nacional (`national`), e `cadence` se aceita `months` (`monthly`). A cobertura é a
    janela declarada na biblioteca, não o que o servidor publica hoje; isso, só
    `sus.available` responde. `labelled_fields` conta as colunas que `sus.label`
    rotula. No marimo e no molab, a tabela tem busca, filtro e ordenação; no HTML
    exportado, só a primeira página aparece. A lista inteira, por sistema, está em
    [Bases e argumentos](https://raphaelfh.github.io/omnisus/datasets/).
    """)
    return


@app.cell
def _(sus):
    bases = sus.describe_datasets()
    bases.select(
        "name",
        "category",
        "title",
        "geography",
        "cadence",
        "coverage_start",
        "coverage_end",
        "labelled_fields",
    )
    return (bases,)


@app.cell
def _(bases, pl):
    bases.group_by(sistema="category").agg(
        bases=pl.len(),
        por_uf=(pl.col("geography") == "state").sum(),
        mensais=(pl.col("cadence") == "monthly").sum(),
        com_preliminar=pl.col("prelim_dir").is_not_null().sum(),
    ).sort("sistema")
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute. BASE é um `name` da tabela acima. UF vale só para
    # base por UF e MES só para base mensal; a etapa 1 mostra a chamada sem eles. Nem
    # toda base tem arquivo em toda UF e mês; a etapa 2 diz se o servidor lista o recorte.
    BASE = "cnes_leitos"
    UF = "RR"
    ANO = 2024
    MES = 1
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, MES, UF, executar


@app.cell
def _(ANO, BASE, MES, UF, bases):
    linha = bases.filter(name=BASE).row(0, named=True)
    argumentos = {"years": [ANO]}
    if linha["geography"] == "state":
        argumentos["ufs"] = [UF]
    if linha["cadence"] == "monthly":
        argumentos["months"] = [MES]
    secao = f"https://raphaelfh.github.io/omnisus/datasets/#{linha['category'].lower()}"
    return argumentos, linha, secao


@app.cell(hide_code=True)
def _(ANO, BASE, MES, argumentos, json, linha, mo, secao):
    _inicio, _fim = linha["coverage_start"], linha["coverage_end"]
    _ate = "em diante" if _fim is None else f"a {_fim}"
    _pedido = f"{ANO}-{MES:02d}" if "months" in argumentos else str(ANO)
    _fora = (
        f" **{_pedido} está fora da cobertura declarada.**"
        if _pedido < _inicio or (_fim is not None and _pedido > _fim)
        else ""
    )
    _publicacao = "um arquivo por UF" if linha["geography"] == "state" else "um arquivo nacional"
    _cadencia = "por mês" if linha["cadence"] == "monthly" else "por ano"
    _preliminar = (
        " O DATASUS publica também arquivos preliminares; `sus.load` lê os dois e cada"
        " linha diz `final` ou `prelim` em `_source_release`."
        if linha["prelim_dir"]
        else ""
    )
    _chamada = ", ".join(
        [json.dumps(BASE)] + [f"{k}={json.dumps(v)}" for k, v in argumentos.items()]
    )
    mo.md(f"""
    ## 1 · A base escolhida: `{BASE}`

    **{linha["title"]}.** Cobertura declarada: {_inicio} {_ate};
    {_publicacao}, {_cadencia}.{_preliminar}{_fora}

    Com os parâmetros acima, a etapa 3 chama:

    ```python
    sus.load({_chamada})
    ```

    Abaixo, os campos do dicionário da biblioteca (`sus.describe_dataset`), sem rede:
    `descrição` vem do dicionário, quando ele a tem, e `mapa de códigos` marca os campos
    que `sus.label` rotula. As outras bases do sistema estão em
    [Bases e argumentos · {linha["category"]}]({secao}).
    """)
    return


@app.cell
def _(BASE, sus, pl):
    pl.DataFrame(
        [
            {
                "campo": f["name"],
                "tipo": f["type"],
                "descrição": f.get("label"),
                "mapa de códigos": bool(f.get("x-decode")),
            }
            for f in sus.describe_dataset(BASE)["schema"]["fields"]
        ]
    ).select(pl.exclude(pl.Null))  # sem `descrição` quando o dicionário não tem nenhuma
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2 · Descobrir

    `sus.available_releases` pergunta agora ao FTP do DATASUS se ele lista o recorte da
    etapa 1, e em que diretório: `final` ou `prelim`. Se não lista, o notebook para aqui.
    """)
    return


@app.cell
def _(BASE, argumentos, executar, mo, sus, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = sus.available_releases(BASE, **argumentos, refresh=True)
    (
        pl.DataFrame({"escopo": [str(e) for e in publicados], "diretorio": [*publicados.values()]})
        if publicados
        else mo.md(
            f"O DATASUS não lista `{BASE}` nesse recorte. Troque `UF`, `ANO` ou `MES` na"
            f' célula de parâmetros; `sus.available("{BASE}")` lista o que ele publica.'
        )
    )
    return (publicados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3 · Baixar e ler

    `sus.load` importa o recorte para o lake e devolve as linhas, com os códigos como
    o DATASUS publicou. Rodar de novo não baixa nem duplica nada.
    """)
    return


@app.cell
def _(BASE, argumentos, mo, publicados, sus):
    mo.stop(not publicados, mo.md("Nada a baixar: o servidor não lista o recorte."))
    dados = sus.load(BASE, **argumentos)
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

    `sus.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. Mais tarde, `sus.outdated(BASE, lake=...)` diz quais escopos
    importados o DATASUS republicou ou passou do preliminar para o final.
    """)
    return


@app.cell
def _(BASE, dados, sus):
    sus.check_columns(BASE, dados)
    return


@app.cell(hide_code=True)
def _(linha, mo, secao):
    mo.md(f"""
    ## 5 · Contar

    Aqui, só o número de registros do recorte. Para analisar, use o dicionário da
    etapa 1, `sus.label` e o notebook do sistema, e leia o perfil da base em
    [Bases e argumentos · {linha["category"]}]({secao}).
    """)
    return


@app.cell
def _(dados, pl):
    registros = dados.select(registros=pl.len())
    registros
    return (registros,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    `sus.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação da base. A contagem e a citação vão para `resultados/<BASE>/`. Veja
    [Reprodutibilidade](https://raphaelfh.github.io/omnisus/pesquisa/reprodutibilidade/).
    """)
    return


@app.cell
def _(BASE, Path, registros, sus):
    with sus.LakeReader() as _lake:
        citacao = sus.cite(_lake, dataset=BASE)
    pasta = Path("resultados") / BASE
    pasta.mkdir(parents=True, exist_ok=True)
    registros.write_csv(pasta / "registros_no_recorte.csv")
    (pasta / "citacao.txt").write_text(citacao.text, encoding="utf-8")
    print(citacao.text)
    return


if __name__ == "__main__":
    app.run()
