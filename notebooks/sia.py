# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.1,<0.26",
#     "omnisus==0.2.3",
#     "polars>=1.44.2,<2.0",
# ]
# ///

"""SIA · produção ambulatorial: qualquer tabela que o omnisus importa, em seis etapas."""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium", app_title="SIA · produção ambulatorial")


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
    # SIA · produção ambulatorial

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py)

    O Sistema de Informações Ambulatoriais do SUS (SIA/SUS) é publicado pelo DATASUS
    em várias tabelas, por UF e mês. Este notebook roda com qualquer uma das que o
    omnisus importa (as linhas do SIA em `sus.describe_datasets()`); três têm análise
    própria na etapa 5. Escolha uma em `BASE` na célula de parâmetros e siga as seis
    etapas do
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
    # Parâmetros: edite e reexecute. BASE é o `name` de uma linha do SIA em
    # `sus.describe_datasets()`; veja bases.py.
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

    `sus.available` lista agora os arquivos da tabela no FTP do DATASUS. Nem toda
    tabela existe para toda UF e mês; se não há nenhum para a UF, o notebook para aqui.
    """)
    return


@app.cell
def _(BASE, UF, executar, mo, sus, pl):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    publicados = sus.available(BASE, ufs=[UF], refresh=True)
    (
        pl.DataFrame(publicados).sort("ano", "mes", descending=True)
        if publicados
        else mo.md(
            f"O DATASUS não lista `{BASE}` para `{UF}`. Troque `UF` na célula de"
            f' parâmetros; `sus.available("{BASE}")` lista o que ele publica.'
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
def _(ANO, BASE, MES, UF, mo, publicados, sus):
    mo.stop(not publicados, mo.md("Nada a baixar: o servidor não lista o recorte."))
    dados = sus.load(BASE, years=[ANO], ufs=[UF], months=[MES])
    dados
    return (dados,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Conferir

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
    O CNS cifrado do paciente (`cns_pac` no BPA-I e na RAAS, `ap_cnspcn` nas APAC) é a
    única chave de pessoa do SIA. De 2024-11 em diante ele vem em branco em boa parte
    dos arquivos: na APAC de medicamentos de GO e SP, em quase todas as linhas; no
    BPA-I, na diálise, na quimioterapia e nas outras APAC, em 30% a 70% delas em
    2026-07. A tabela abaixo mostra quanto falta em cada escopo do recorte. Antes de
    ligar pessoas, leia a seção Armadilhas do
    [perfil do SIA](https://raphaelfh.github.io/omnisus/sources/sia/).
    """)
    return


@app.cell
def _(dados, pl):
    # Em branco: nulo ou só espaços, como no censo de evidence/2026-10-08-cns-vazio-sia/.
    _colunas = sorted({"cns_pac", "ap_cnspcn"} & set(dados.columns))
    cns_em_branco = (
        dados.group_by("uf", "ano", "mes")
        .agg(
            coluna=pl.lit(_colunas[0]),
            registros=pl.len(),
            em_branco=(pl.col(_colunas[0]).str.strip_chars().fill_null("") == "").sum(),
        )
        .with_columns(pct_em_branco=(100 * pl.col("em_branco") / pl.col("registros")).round(1))
        .sort("uf", "ano", "mes")
        if _colunas
        else None
    )
    cns_em_branco
    return (cns_em_branco,)


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

    `sus.cite` nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    publicação da tabela. As tabelas e a citação vão para `resultados/<BASE>/`. Veja
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
