# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.0,<0.26",
#     "omnisus==0.2.1",
#     "polars>=1.44.2,<2.0",
# ]
# ///

"""SIH · AIH reduzida: do arquivo do DATASUS a uma tabela citável, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="SIH · AIH reduzida")


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
    # SIH · AIH reduzida

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py)

    Autorizações de internação hospitalar (AIH) do Sistema de Informações
    Hospitalares do SUS (SIH/SUS), publicadas pelo DATASUS por UF e mês. Este
    notebook percorre as seis etapas do
    [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/) com um
    recorte pequeno: **Roraima, janeiro de 2024**.

    **Abrir este notebook não baixa nem grava nada.** Edite os parâmetros na célula
    seguinte e ponha `EXECUTAR = True` (ou exporte com `-- --executar true`) para
    consultar a rede e gravar no lake (`data/raw/`, ou `$OMNISUS_DATA_DIR`).

    Uma AIH não é um paciente. Antes de interpretar números, leia o
    [perfil do SIH](https://raphaelfh.github.io/omnisus/sources/sih_aih_reduzida/).
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute.
    BASE = "sih_aih_reduzida"
    UF = "RR"
    ANO = 2024
    MES = 1
    EXECUTAR = False
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, BASE, MES, UF, executar


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1 · O que a base registra

    Campos do dicionário da biblioteca (`sus.describe_dataset`), sem rede. O
    significado dos códigos está no perfil e no documento oficial citado nele.
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
    ## 3 · Baixar e ler

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
    ## 4 · Conferir

    `sus.check_columns` mostra, por coluna, vazios, códigos sem rótulo e datas fora
    do esperado. O SIH é publicado num único diretório, então `sus.outdated` não se
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
    ## 5 · Analisar

    `sus.label` põe o rótulo do dicionário ao lado de cada código. `aih_distintas`
    compara linhas e números de AIH antes de qualquer contagem de internações.
    """)
    return


@app.cell
def _(BASE, dados, sus, pl):
    aih = sus.label(BASE, dados, columns=["morte"])
    tabelas = {
        "aih_por_diagnostico_principal": aih.group_by(
            diagnostico_cid10_3=pl.col("diag_princ").str.slice(0, 3)
        )
        .agg(
            aih=pl.len(),
            dias_de_permanencia=pl.col("dias_perm").sum(),
            media_dias=pl.col("dias_perm").mean().round(1),
            valor_total=pl.col("val_tot").sum().round(2),
        )
        .sort("aih", descending=True),
        "campo_morte": aih.group_by("morte", "morte_rotulo").len("aih").sort("morte"),
        "aih_distintas": aih.select(
            linhas=pl.len(), numeros_de_aih_distintos=pl.col("n_aih").n_unique()
        ),
    }
    tabelas
    return (tabelas,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · Citar e guardar

    `sus.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação da base. As tabelas e a citação vão para `resultados/sih_aih_reduzida/`.
    Veja [Reprodutibilidade](https://raphaelfh.github.io/omnisus/pesquisa/reprodutibilidade/).
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
