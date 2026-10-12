# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo>=0.25.1,<0.26",
#     "omnisus==0.2.3",
#     "polars>=1.44.2,<2.0",
#     "sqlglot>=30.18.0",
#     "xlsxwriter>=3.2.9",
# ]
# ///

"""Explorar o lake: escolher bases e escopos com widgets, ver as linhas e citar."""

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="Explorar o lake")


@app.cell
def _():
    import io
    import json
    import os
    import re
    import shutil
    import tempfile
    from datetime import date
    from pathlib import Path

    import marimo as mo
    import polars as pl
    import xlsxwriter

    import omnisus as sus
    from omnisus.lake.locking import WriterBusyError

    return Path, WriterBusyError, date, io, json, mo, os, pl, re, shutil, sus, tempfile, xlsxwriter


@app.cell
def _():
    def numero(valor, casas=0):
        """`valor` como se escreve em português: 3.246 linhas, 23,5 GiB."""
        return f"{valor:,.{casas}f}".translate(str.maketrans(",.", ".,"))

    return (numero,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Explorar o lake

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/explorar.py)

    Escolha nos widgets as bases e os escopos que o lake já tem e veja as linhas numa
    tabela com busca, filtro e ordenação, o perfil de uma coluna e a citação do que
    você escolheu. Os códigos ficam como o DATASUS publicou; o rótulo vem do
    dicionário, ao lado (`sexo_rotulo`).

    **Onde está o lake.** O lake é uma pasta com `omnisus-catalog.sqlite` e
    `omnisus.ducklake/`. Escolha onde ela está:

    - *Pasta neste computador*: o caminho da pasta. Começa onde `sus.load` grava:
      `$OMNISUS_DATA_DIR`, se definida, ou `data/raw`, relativa à pasta em que você
      abriu o marimo. Uma pasta do Google Drive sincronizada no computador também serve.
    - *Google Drive*: clique em *Conectar ao Google Drive* (na primeira vez abre o
      login do Google), escreva o caminho da pasta em *Meu Drive* (o Colab cria o lake
      em `omnisus`) ou cole o link da pasta, que serve também para uma pasta
      compartilhada com você, e clique em *Copiar do Drive*. O lake é copiado para o
      disco da sessão, porque o molab não monta o Drive e o DuckLake só lê arquivos do
      disco.

    O catálogo guarda a pasta em que o lake foi criado (no Colab,
    `/content/drive/MyDrive/omnisus`); este notebook lê os dados da pasta indicada,
    onde quer que ela esteja agora. Importe só num lake que está na pasta onde foi
    criado.

    **Abrir este notebook não baixa nem grava nada.** A seção *Importar* consulta o
    DATASUS só quando você clica no botão.
    """)
    return


@app.cell
def _(Path, mo, os):
    # Onde `sus.load` grava, resolvido como a biblioteca resolve: um `~` literal não é a home.
    _padrao = Path(os.environ.get("OMNISUS_DATA_DIR") or "data/raw").resolve()
    origem = mo.ui.radio(
        {"Pasta neste computador": "pasta", "Google Drive": "drive"},
        value="Pasta neste computador",
        label="Onde está o lake",
        inline=True,
    )
    pasta = mo.ui.text(
        value=mo.cli_args().get("lake") or str(_padrao), label="Pasta do lake", full_width=True
    )
    conectar = mo.ui.run_button(label="Conectar ao Google Drive")
    pasta_drive = mo.ui.text(
        value="omnisus",
        label="Pasta no Google Drive: caminho em *Meu Drive* ou link da pasta",
        full_width=True,
    )
    copiar = mo.ui.run_button(label="Copiar do Drive")
    # Só `true` liga: o marimo converte true/false em booleano, e `no` seria um texto não vazio.
    executar = mo.cli_args().get("executar") is True
    return conectar, copiar, executar, origem, pasta, pasta_drive


@app.cell
def _(conectar, copiar, mo, origem, pasta, pasta_drive):
    _drive = mo.hstack([conectar, pasta_drive, copiar], widths=[0, 1, 0])
    mo.vstack([origem, pasta if origem.value == "pasta" else _drive])
    return


@app.cell
def _(Path, origem, pasta, pasta_drive, re, tempfile):
    if origem.value == "drive":
        # O lake do Drive é lido de uma cópia no disco da sessão, uma pasta por pasta do Drive.
        _nome = re.sub(r"\W+", "_", pasta_drive.value.strip("/"))
        diretorio = Path(tempfile.gettempdir()).resolve() / "omnisus-drive" / _nome
    else:
        diretorio = Path(pasta.value).expanduser().resolve()
    alvo = f"ducklake:{diretorio / 'omnisus.ducklake'}"
    return alvo, diretorio


@app.cell
def _(mo):
    # Uma importação muda a versão, e só ela reabre o lake: mexer nos widgets de
    # importação não refaz as consultas abaixo.
    versao, mudar_versao = mo.state(0)
    # A última importação fica na tela até o próximo clique, mesmo que um widget mude.
    ultima, guardar_ultima = mo.state(None)
    return guardar_ultima, mudar_versao, ultima, versao


@app.cell
def _(conectar, mo):
    mo.stop(not conectar.value)
    # Importado só no clique: quem não usa o Drive não precisa do pacote (o molab já o tem).
    from gdrive_fsspec import GoogleDriveFileSystem as _Drive

    def drive_em(pasta_id=None):
        """O Drive como o molab o abre em *Add remote storage*: o servidor é remoto, então
        o login do Google vai por um link e um código. `pasta_id` faz de uma pasta a raiz."""
        return _Drive(
            root_file_id=pasta_id,
            use_listings_cache=False,
            skip_instance_cache=True,
            auth_kwargs={"use_local_webserver": False},
        )

    try:
        # Na primeira vez pede o login do Google; depois o token fica guardado.
        drive = drive_em()
    except Exception as e:
        mo.stop(
            True,
            mo.callout(
                mo.md(
                    f"Não deu para conectar ao Google Drive ({type(e).__name__}: {e}). No "
                    "molab, conecte também em *Files → Add remote storage → Google Drive* "
                    "e clique de novo."
                ),
                kind="danger",
            ),
        )
    mo.md("Conectado ao Google Drive. Escreva a pasta do lake e clique em *Copiar do Drive*.")
    return drive, drive_em


@app.cell
def _(copiar, diretorio, drive, drive_em, mo, mudar_versao, pasta_drive, re, shutil):
    mo.stop(not copiar.value)
    mo.stop(not pasta_drive.value.strip(), mo.md("Escreva o caminho ou o link da pasta no Drive."))
    # Um link faz da pasta a raiz (alcança uma pasta compartilhada); um caminho parte de Meu Drive.
    _link = re.search(r"/folders/([\w-]+)", pasta_drive.value)
    _origem = drive_em(_link[1]) if _link else drive
    try:
        with mo.status.spinner(title="Copiando o lake do Google Drive"):
            shutil.rmtree(diretorio, ignore_errors=True)  # a cópia anterior, nunca o original
            _origem.get(
                "" if _link else pasta_drive.value.strip("/"), str(diretorio), recursive=True
            )
    except Exception as e:
        mo.stop(
            True,
            mo.callout(
                mo.md(
                    f"Não deu para copiar `{pasta_drive.value}` do Google Drive "
                    f"({type(e).__name__}: {e}). Confira o caminho ou o link."
                ),
                kind="danger",
            ),
        )
    mudar_versao(lambda v: v + 1)  # reabre o lake, como depois de uma importação
    mo.md(
        f"Lake copiado para `{diretorio}`. Dá para explorar e citar; para importar, use o "
        "lake na pasta onde ele foi criado (#87)."
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Importar

    Para pôr escopos no lake: escolha a base e, conforme a base, os anos, as UFs e os
    meses. Cada lista tem *Select all* e *Deselect all* no topo; digitar filtra a lista
    (`201` e depois *Select 10 matching* marca 2010 a 2019). `sus.import_dataset` baixa
    só o que o lake ainda não tem do mesmo arquivo.

    **Limites.** A importação anda em partes de 24 escopos, com um commit no lake por
    parte. O omnisus baixa até 6 arquivos por vez, de propósito: o servidor do DATASUS
    é público e compartilhado. Cada arquivo é descompactado inteiro na memória, e os
    maiores do SIA passam de 300 MB compactados (o BPA-I de SP de outubro de 2023,
    `BISP2310.dbc`, tem 370 MB); numa máquina com pouca memória, importe-os poucos de
    cada vez. O disco cresce com o que você escolhe: a linha abaixo dos seletores
    mostra o espaço livre. No molab, o lake importado fica no disco da sessão e some
    quando ela termina.

    **Falhas.** O relatório diz o que houve com cada escopo. Clique em *Importar* de
    novo para continuar: o que já está no lake é pulado sem baixar. Se o kernel cair
    (por falta de memória, por exemplo), o que as partes anteriores gravaram fica. O
    botão ■ do marimo (*Stop (interrupt) execution*, só no modo de edição) para a
    importação ao fim da parte em curso, cujo resultado não entra no relatório; o resto
    da página se atualiza no próximo *Importar*. Ligue *Substituir* só quando o motivo
    pedir `replace`: o DATASUS publicou o arquivo de novo, ou outra versão do omnisus o
    importou. Com ele, todos os escopos escolhidos são baixados e gravados de novo.
    """)
    return


@app.cell
def _(mo, sus):
    base_nova = mo.ui.dropdown(
        options=sorted(d.name for d in sus.datasets()),
        value=mo.cli_args().get("base") or "sim_obitos",
        label="Base",
        searchable=True,
    )
    return (base_nova,)


@app.cell
def _(base_nova, date, mo, sus):
    _base = sus.resolve(base_nova.value)
    por_uf = _base.geography == "state"
    mensal = _base.monthly

    def _da_linha(nome, padrao, tipo):
        """Os valores de `-- --nome a,b` (vírgula, espaço ou `--nome` repetido), ou o padrão."""
        valores = " ".join(map(str, mo.cli_args().get_all(nome))).replace(",", " ").split()
        return [tipo(v) for v in valores] if valores else padrao

    (_primeiro, _), _ultimo = _base.coverage
    _fim = _ultimo[0] if _ultimo else date.today().year
    _anos = list(range(_primeiro, _fim + 1))
    anos_novos = mo.ui.multiselect(
        options=_anos,
        # Fora da cobertura desta base fica de fora, como ao trocar de base.
        value=[a for a in _da_linha("anos", [min(2022, _fim)], int) if a in _anos],
        label="Anos",
    )
    ufs_novas = mo.ui.multiselect(
        options=sus.ALL_UFS, value=_da_linha("ufs", ["RR"], str.upper), label="UFs"
    )
    meses_novos = mo.ui.multiselect(
        options=list(range(1, 13)), value=_da_linha("meses", [1], int), label="Meses"
    )
    substituir = mo.ui.switch(
        value=mo.cli_args().get("substituir") is True, label="Substituir o que já está no lake"
    )
    importar = mo.ui.run_button(label="Importar")
    mo.hstack(
        [
            base_nova,
            anos_novos,
            *([ufs_novas] if por_uf else []),
            *([meses_novos] if mensal else []),
        ],
        justify="start",
        wrap=True,
    )
    return anos_novos, importar, mensal, meses_novos, por_uf, substituir, ufs_novas


@app.cell
def _(Path, anos_novos, base_nova, mensal, meses_novos, por_uf, sus, tempfile, ufs_novas):
    escopos_novos = sus.scopes_for(
        base_nova.value,
        years=sorted(anos_novos.value),
        ufs=[u for u in sus.ALL_UFS if u in ufs_novas.value] if por_uf else None,
        months=sorted(meses_novos.value) if mensal else None,
    )
    temporaria = Path(tempfile.gettempdir())
    return escopos_novos, temporaria


@app.cell
def _(diretorio, escopos_novos, importar, mo, numero, shutil, substituir, temporaria, versao):
    versao()  # mede o disco de novo depois de cada importação

    def _livre(pasta):
        """Espaço livre no disco de `pasta` ou da primeira pasta acima dela que existe."""
        for _pasta in (pasta, *pasta.parents):
            try:
                return f"{numero(shutil.disk_usage(_pasta).free / 2**30, 1)} GiB"
            except OSError:  # não existe, sem permissão, drive ou rede fora do ar
                pass
        return "? GiB"

    mo.vstack(
        [
            mo.md(
                f"**{numero(len(escopos_novos))} escopo{'' if len(escopos_novos) == 1 else 's'}.** "
                f"Disco livre: {_livre(diretorio)} na pasta do lake e {_livre(temporaria)} "
                f"em `{temporaria}`, onde a importação prepara cada escopo antes de gravá-lo "
                "no lake."
            ),
            mo.hstack([importar, substituir], justify="start"),
        ]
    )
    return


@app.cell
def _(
    WriterBusyError,
    alvo,
    base_nova,
    escopos_novos,
    executar,
    guardar_ultima,
    importar,
    mo,
    mudar_versao,
    pl,
    substituir,
    sus,
    temporaria,
    ultima,
):
    def _mostrar(importacao):
        """Aviso, resumo e uma linha por escopo de uma importação."""
        if importacao is None:
            return None
        aviso, tipo, resumo, tabela = importacao
        return mo.vstack(
            [
                *([mo.callout(mo.md(aviso), kind=tipo)] if aviso else []),
                mo.md(resumo),
                mo.ui.table(
                    tabela.fill_null(""), page_size=10, selection=None, wrapped_columns=["motivo"]
                ),
            ]
        )

    # `-- --executar true` é para rodar sem interface (export, script): numa sessão
    # interativa, cada mudança de widget importaria de novo. Sem clique, a célula mostra a
    # última importação: o aviso pode pedir para importar alguns escopos de novo, com
    # outros valores nos widgets.
    mo.stop(not (importar.value or executar), _mostrar(ultima()))
    mo.stop(
        not escopos_novos,
        mo.md("Nenhum escopo escolhido: marque ao menos um valor em cada lista acima."),
    )

    _por_parte = 24  # escopos por parte e por commit
    _situacoes = {
        None: "importado",
        "unchanged": "já estava no lake",
        "not_listed": "o DATASUS não publica",
        "outside_coverage": "fora da cobertura da base",
        "fetch_failed": "falhou ao baixar",
        "ingest_failed": "falhou ao gravar",
        "rolled_back": "desfeito: outro escopo da parte falhou",
    }
    _ao_abrir = {
        "attach": (
            "este lake foi criado em outra pasta e aqui só pode ser lido (#87). Importe "
            "na pasta onde foi criado, a que o erro entre parênteses mostra, ou indique "
            "uma pasta nova"
        ),
        "set_option": "outro programa está lendo este lake; feche-o",
    }
    _resultado = {}  # escopo -> (situação, motivo)

    def _causa(e):
        """O texto da exceção mais interna que tem texto: o que houve."""
        texto = str(e)
        while e.__cause__ is not None:
            e = e.__cause__
            texto = str(e) or texto
        return texto

    def _anotar(relatorio):
        for o in relatorio.outcomes:
            _resultado[o.scope] = (_situacoes[o.code], o.reason)

    def _parte(escopos):
        """Importa uma parte e anota cada escopo; devolve por que parar, se for o caso."""
        try:
            _anotar(
                sus.import_dataset(
                    base_nova.value,
                    scopes=escopos,
                    target=alvo,
                    batch_size=_por_parte,
                    policy="replace" if substituir.value else "skip_same",
                )
            )
        except sus.ImportAbortedError as e:
            _anotar(e.report)
            _resultado.update((escopo, ("sem resultado", _causa(e))) for _, escopo in e.unresolved)
            return f"A gravação no lake parou ({_causa(e)})."
        except sus.FtpUnavailable as e:
            return f"O servidor do DATASUS não respondeu ({_causa(e)})."
        except sus.FtpPathNotFound as e:
            return f"O DATASUS não tem mais um diretório desta base ({e}); atualize o omnisus."
        except sus.CatalogAttachError as e:
            _dica = _ao_abrir.get(e.stage)
            return f"Não deu para abrir o lake para gravar{f': {_dica}' if _dica else ''} ({_causa(e)})."
        except WriterBusyError:
            return (
                "Outro processo está gravando neste lake (outra aba deste notebook, outro "
                "notebook, um terminal, ou uma importação interrompida ainda terminando). "
                "Espere ele terminar."
            )
        except Exception as e:
            return f"Erro inesperado: {type(e).__name__}: {_causa(e)}."
        # Disco cheio falha cada escopo sem parar a importação; o resto falharia igual.
        if any("No space left on device" in (_motivo or "") for _, _motivo in _resultado.values()):
            return f"Disco cheio na pasta do lake ou em `{temporaria}`. Libere espaço."
        return None

    _partes = [escopos_novos[i : i + _por_parte] for i in range(0, len(escopos_novos), _por_parte)]
    parada, _escopos = None, []
    try:
        with mo.status.progress_bar(
            total=len(escopos_novos), title=f"Importando {base_nova.value}", show_eta=True
        ) as _barra:
            for _escopos in _partes:
                parada = _parte(_escopos)
                _barra.update(increment=len(_escopos))
                if parada:
                    break
    except KeyboardInterrupt:
        # A interrupção só chega aqui quando a chamada ao omnisus volta (ou, num segundo ■,
        # enquanto ela ainda termina): o relatório da parte em curso se perde.
        for _escopo in _escopos:
            _resultado.setdefault(_escopo, ("sem resultado", "interrompido"))
        parada = "Interrompido. O que a parte em curso fez não entra no relatório."

    relatorio = pl.DataFrame(
        [(str(e), *_resultado.get(e, ("não tentado", None))) for e in escopos_novos],
        schema=dict.fromkeys(["escopo", "situacao", "motivo"], pl.String),
        orient="row",
    )
    importacao = " · ".join(
        f"{s}: {n}" for s, n in relatorio["situacao"].value_counts(sort=True).rows()
    )
    # Reabre o lake quando algo pode ter sido gravado. Um clique que termina sem parar
    # também reabre: depois de uma interrupção, o marimo não refaz as células que
    # dependem da versão, e é esse clique que atualiza a página.
    if parada is None or relatorio["situacao"].is_in(["importado", "sem resultado"]).any():
        mudar_versao(lambda v: v + 1)
    if parada:
        _aviso = f"{parada} Clique em *Importar* para continuar."
    elif relatorio["situacao"].str.starts_with("falhou").any():
        _aviso = (
            "Veja o motivo de cada escopo. Se ele pedir `replace`, importe esses escopos "
            "à parte, com *Substituir* ligado; os desfeitos da mesma parte entram no clique "
            "seguinte. Senão, clique em *Importar* para tentar de novo."
        )
    else:
        _aviso = None
    _ultima = (_aviso, "danger" if parada else "warn", importacao, relatorio)
    guardar_ultima(_ultima)
    _mostrar(_ultima)
    return importacao, parada, relatorio


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## O que o lake tem

    Um escopo por linha, lido do catálogo, sem rede: a base, a UF, o ano e o mês, o
    diretório do servidor (`final` ou `prelim`), quantas linhas foram gravadas e quando.
    """)
    return


@app.cell
def _(alvo, diretorio, mo, sus, versao):
    versao()
    try:
        leitor = sus.LakeReader(alvo)
    except sus.CatalogAttachError:
        mo.stop(
            True,
            mo.md(f"Não há lake em `{diretorio}`. Indique outra pasta ou importe uma base acima."),
        )
    snapshot = sus.latest_snapshot_id(leitor)

    def _literal(valor):
        return "'" + str(valor).replace("'", "''") + "'"

    # O catálogo guarda a pasta onde o lake foi criado. Reabrir com OVERRIDE_DATA_PATH lê os
    # Parquet desta pasta, fixa o snapshot e deixa abrir uma cópia vinda do Google Drive.
    _catalogo = diretorio / "omnisus-catalog.sqlite"
    con = (
        leitor.connect()
        .execute("DETACH lake")
        .execute(
            f"ATTACH {_literal(f'ducklake:sqlite:{_catalogo}')} AS lake "
            f"(READ_ONLY, DATA_PATH {_literal(diretorio / 'omnisus.ducklake')}, "
            f"OVERRIDE_DATA_PATH true, SNAPSHOT_VERSION {snapshot})"
        )
    )
    return con, leitor, snapshot


@app.cell
def _(leitor, mo, pl):
    publicacoes = [p for p in leitor.publications() if p["active"] and p["scope"] is not None]
    mo.stop(not publicacoes, mo.md("O lake ainda não tem nenhuma base importada."))
    escopos = pl.DataFrame(
        [
            {
                "base": p["dataset"],
                "uf": p["scope"].uf,
                "ano": p["scope"].ano,
                "mes": p["scope"].mes,
                "diretorio": p["release"],
                "linhas": p["rows"],
                "importado_em": p["published_at"],
            }
            for p in publicacoes
        ],
        schema_overrides={"uf": pl.String, "mes": pl.Int64},
    ).sort("base", "ano", "mes", "uf", nulls_last=True)
    mo.ui.table(escopos, selection=None, format_mapping={"ano": str})  # 2024, não 2,024
    return escopos, publicacoes


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Escolher

    As opções vêm do que o lake tem. Uma base nacional (SINAN, subconjuntos do SIM)
    não tem UF; uma base anual não tem mês.
    """)
    return


@app.cell
def _(escopos, mo):
    _nomes = escopos["base"].unique().sort().to_list()
    # Começa na base de `--base`, se o lake a tem: um export mostra e cita o que importou.
    _pedida = mo.cli_args().get("base")
    bases = mo.ui.multiselect(
        options=_nomes, value=[_pedida] if _pedida in _nomes else _nomes[:1], label="Bases"
    )
    bases
    return (bases,)


@app.cell
def _(bases, con, escopos, mo, pl):
    mo.stop(not bases.value, mo.md("Escolha ao menos uma base."))
    _das_bases = escopos.filter(pl.col("base").is_in(bases.value))

    def _filtro(coluna, rotulo):
        opcoes = _das_bases[coluna].drop_nulls().unique().sort().to_list()
        return mo.ui.multiselect(options=opcoes, value=opcoes, label=rotulo)

    ufs, anos, meses = _filtro("uf", "UFs"), _filtro("ano", "Anos"), _filtro("mes", "Meses")
    esquemas = {
        _base: {
            nome: tipo for nome, tipo, *_ in con.execute(f'DESCRIBE lake."{_base}"').fetchall()
        }
        for _base in bases.value
    }
    colunas = mo.ui.dictionary(
        {
            _base: mo.ui.multiselect(options=list(e), value=list(e), label=_base)
            for _base, e in esquemas.items()
        }
    )
    _filtros = [f for f in (ufs, anos, meses) if f.options]  # base anual: sem Meses
    mo.vstack([mo.hstack(_filtros, justify="start"), *colunas.values()])
    return anos, colunas, esquemas, meses, ufs


@app.cell
def _(anos, esquemas, meses, publicacoes, ufs):
    def _escolhido(e):
        return (
            (e.uf is None or e.uf in ufs.value)
            and e.ano in anos.value
            and (e.mes is None or e.mes in meses.value)
        )

    escolhidas = {
        _base: [p for p in publicacoes if p["dataset"] == _base and _escolhido(p["scope"])]
        for _base in esquemas
    }
    return (escolhidas,)


@app.cell
def _(escolhidas, esquemas, json, sus):
    def _condicao(publicacoes):
        """`WHERE` e parâmetros que selecionam os escopos destas publicações.

        Cada publicação guarda em `scope_json` as colunas e os valores que gravou
        (`uf`, `ano`, `mes`; `_source_ano` numa base nacional).
        """
        campos = [json.loads(p["scope_json"]) for p in publicacoes]
        if not campos:
            return "false", []
        chaves = list(campos[0])
        colunas = ", ".join(f'"{c}"' for c in chaves)
        listas = ", ".join("unnest(?)" for _ in chaves)
        return f"({colunas}) IN (SELECT {listas})", [[e[c] for e in campos] for c in chaves]

    filtros = {_base: _condicao(_pubs) for _base, _pubs in escolhidas.items()}
    projecoes = {
        _base: sus.analytical_projection(
            _base,
            observed_schema=esquemas[_base],
            scopes=[sus.SourceContext.from_publication(p) for p in _pubs],
        )
        for _base, _pubs in escolhidas.items()
    }
    totais = {_base: sum(p["rows"] for p in _pubs) for _base, _pubs in escolhidas.items()}
    return filtros, projecoes, totais


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Linhas

    Uma aba por base. A contagem é de todos os escopos escolhidos; a tabela mostra até
    *Linhas na tabela* delas, porque a tabela do marimo guarda na memória tudo o que
    recebe. *Todas as linhas* mostra todas, sem limite: com muitos escopos de uma base
    grande (SIH, SIM de várias UFs e anos), isso pode ocupar gigabytes de memória e
    demorar; para ver mais linhas com menos memória, filtre os escopos ou tire colunas.
    As categorias harmonizadas (`idade_anos_completos`, `sexo_categoria`...) só
    aparecem quando todos os escopos vêm de fontes validadas (ADR 0003); a aba diz o
    motivo quando faltam.

    *Baixar o dicionário (XLSX)* traz uma planilha com duas abas. A aba `colunas` tem
    uma linha por coluna gravada no lake, com o tipo dela e, quando o dicionário
    descreve a coluna (`no_dicionario`), o título, a descrição, o tipo declarado e
    quantos códigos ela tem; para o mapa de códigos, como foi conferido
    (`verified_in_source`, `conflicting` ou `unreviewed`), a `nota` que explica um
    conflito e, quando foi conferido, o documento oficial de onde veio (URL, SHA-256 e
    onde ler). As colunas `_rotulo` e as categorias harmonizadas, que a tabela acima
    calcula, não entram. A aba `codigos` tem uma linha por código, com o rótulo que a
    tabela mostra; os códigos são texto, e `06` continua `06`; uma célula vazia em
    `codigo` é o código vazio (o campo em branco do arquivo). O nome do arquivo leva a
    versão do dicionário, a que se cita. Nomes de CID-10, de municípios e de ocupações
    não estão no dicionário: ficam nas tabelas `aux_*`, que *Importar* não grava.
    """)
    return


@app.cell
def _(mo):
    linhas = mo.ui.number(
        start=100,
        stop=1_000_000,
        step=100,
        value=int(mo.cli_args().get("linhas") or 10_000),
        label="Linhas na tabela",
        debounce=True,
    )
    # Só `true` liga, como em `--substituir`.
    todas = mo.ui.switch(value=mo.cli_args().get("todas") is True, label="Todas as linhas")
    rotulos = mo.ui.switch(value=True, label="Rótulos do dicionário")
    mo.hstack([linhas, todas, rotulos], justify="start")
    return linhas, rotulos, todas


@app.cell
def _(colunas, con, filtros, linhas, mo, projecoes, todas):
    # Apagar o número deixa o campo sem valor; com *Todas as linhas* ele não conta.
    mo.stop(
        not todas.value and linhas.value is None,
        mo.md("Indique quantas linhas a tabela mostra."),
    )

    _limite = "" if todas.value else f" LIMIT {int(linhas.value)}"
    brutas = {}
    for _base, (_onde, _parametros) in filtros.items():
        _selecao = ", ".join(f'"{c}"' for c in colunas.value[_base]) or "NULL AS sem_colunas"
        _categorias = "".join(f', {c.expression} AS "{c.name}"' for c in projecoes[_base].columns)
        brutas[_base] = con.execute(
            f'SELECT {_selecao}{_categorias} FROM lake."{_base}" WHERE {_onde}{_limite}',
            _parametros,
        ).pl()
    return (brutas,)


@app.cell
def _(esquemas, io, pl, sus, xlsxwriter):
    def _juntar(valores):
        return " | ".join(valores) or None

    def _dicionario(base):
        """O dicionário da tabela `base` numa planilha: (nome do arquivo, bytes).

        Aba `colunas`: uma linha por coluna gravada no lake, também as que o dicionário
        não descreve. Aba `codigos`: uma linha por código de cada coluna.
        """
        meta = sus.describe_dataset(base)
        documentos = {d["id"]: d for d in meta["sources"]}
        descritas = {item["field"]["name"]: item for item in meta["fields"]}
        colunas, codigos = [], []
        for nome, tipo in esquemas[base].items():
            linha = {"coluna": nome, "tipo_no_lake": tipo, "no_dicionario": "não"}
            if (item := descritas.get(nome)) is not None:
                campo = item["field"]
                mapa = next(c for c in item["claims"] if c["target"] == "/field/codes")
                provas = mapa["evidence"] if campo["codes"] else []
                linha |= {
                    "no_dicionario": "sim",
                    "titulo": campo["label"],
                    "descricao": campo["description"],
                    "tipo_no_dicionario": campo["logical_type"],
                    "codigos": len(campo["codes"]),
                    "conferencia": mapa["status"] if campo["codes"] else None,
                    "nota": mapa["note"] if campo["codes"] else None,
                    "fonte": _juntar(documentos[p["source_id"]]["url"] for p in provas),
                    "fonte_sha256": _juntar(documentos[p["source_id"]]["sha256"] for p in provas),
                    "onde": _juntar(
                        " ".join([p["locator"] or "", *(f"p. {n}" for n in p["pages"])]).strip()
                        for p in provas
                    ),
                }
                codigos += [
                    {"coluna": nome, "codigo": c["value"], "rotulo": c["label"]}
                    for c in campo["codes"]
                ]
            colunas.append(linha)
        nomes = ["coluna", "tipo_no_lake", "no_dicionario", "titulo", "descricao"]
        nomes += ["tipo_no_dicionario", "codigos", "conferencia", "nota", "fonte"]
        nomes += ["fonte_sha256", "onde"]
        abas = {
            "colunas": pl.DataFrame(
                colunas, schema=dict.fromkeys(nomes, pl.String) | {"codigos": pl.Int64}
            ),
            "codigos": pl.DataFrame(
                codigos, schema=dict.fromkeys(["coluna", "codigo", "rotulo"], pl.String)
            ),
        }
        arquivo = io.BytesIO()
        # Texto puro: uma fonte com várias URLs viraria um link só, que não existe.
        with xlsxwriter.Workbook(arquivo, {"strings_to_urls": False}) as livro:
            for aba, tabela in abas.items():
                tabela.write_excel(livro, worksheet=aba, autofit=True, freeze_panes="A2")
        return f"{base}_dicionario_{meta['dictionary_version']}.xlsx", arquivo.getvalue()

    dicionarios = {_base: _dicionario(_base) for _base in esquemas}
    return (dicionarios,)


@app.cell
def _(brutas, dicionarios, escolhidas, mo, numero, projecoes, rotulos, sus, totais):
    amostras = {
        _base: sus.label(_base, _bruta) if rotulos.value else _bruta
        for _base, _bruta in brutas.items()
    }

    _por_que = {
        "unconfirmed_source_scope": "nem todos os escopos vêm de fontes validadas",
        "missing_source_field": "falta na tabela a coluna de onde ela sai",
        "unsupported_field": "a base não tem regra para ela",
        "unsupported_date_format": "a data tem um formato sem regra",
    }

    def _resumo(base):
        fora = {}
        # Sem escopo escolhido não há fonte a conferir, nem categoria a explicar.
        for u in projecoes[base].unavailable if escolhidas[base] else []:
            if u.reason != "unsupported_dataset":
                fora.setdefault(_por_que.get(u.reason, u.reason), []).append(f"`{u.field}`")
        notas = "".join(
            f" Categorias harmonizadas fora, porque {motivo}: {', '.join(campos)}."
            for motivo, campos in fora.items()
        )
        linhas = (
            f"**{numero(totais[base])}** linhas; a tabela mostra {numero(amostras[base].height)}."
        )
        return linhas + notas

    def _cabecalho(base):
        nome, conteudo = dicionarios[base]
        baixar = mo.download(
            conteudo,
            filename=nome,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            label="Baixar o dicionário (XLSX)",
        )
        return mo.vstack([baixar, mo.md(_resumo(base))], align="start")  # a nota pode ser longa

    # Todas as colunas: as categorias harmonizadas vêm por último e o marimo mostra só 50.
    mo.ui.tabs(
        {
            _base: mo.vstack(
                [
                    _cabecalho(_base),
                    mo.ui.table(
                        _amostra, page_size=20, max_columns=None, format_mapping={"ano": str}
                    ),
                ]
            )
            for _base, _amostra in amostras.items()
        }
    )
    return (amostras,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Perfil de uma coluna

    Quantas linhas tem cada código, em todos os escopos escolhidos (não só nas da
    tabela acima), com o rótulo do dicionário. Começa no primeiro campo que o
    dicionário rotula.
    """)
    return


@app.cell
def _(esquemas, mo):
    base_perfil = mo.ui.dropdown(options=list(esquemas), value=next(iter(esquemas)), label="Base")
    return (base_perfil,)


@app.cell
def _(base_perfil, esquemas, mo, sus):
    _colunas = list(esquemas[base_perfil.value])
    _rotuladas = [
        f["name"]
        for f in sus.describe_dataset(base_perfil.value)["schema"]["fields"]
        if f.get("x-decode") and f["name"] in _colunas
    ]
    coluna_perfil = mo.ui.dropdown(
        options=_colunas, value=(_rotuladas or _colunas)[0], label="Coluna", searchable=True
    )
    mo.hstack([base_perfil, coluna_perfil], justify="start")
    return (coluna_perfil,)


@app.cell
def _(base_perfil, coluna_perfil, con, filtros, sus):
    _onde, _parametros = filtros[base_perfil.value]
    perfil = sus.label(
        base_perfil.value,
        con.execute(
            f'SELECT "{coluna_perfil.value}", count(*) AS registros, '
            "round(100 * count(*) / sum(count(*)) OVER (), 2) AS pct "
            f'FROM lake."{base_perfil.value}" WHERE {_onde} '
            "GROUP BY ALL ORDER BY registros DESC LIMIT 1000",
            _parametros,
        ).pl(),
    )
    perfil
    return (perfil,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Consultar em SQL

    Para ir além das linhas da tabela, consulte o lake inteiro: as tabelas estão em
    `lake.<base>`. A consulta abaixo começa na base do perfil.
    """)
    return


@app.cell
def _(base_perfil, con, mo):
    consulta = mo.sql(
        f"""
        SELECT * FROM lake.{base_perfil.value} LIMIT 100
        """,
        engine=con,
    )
    return (consulta,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Citar

    A citação nomeia o arquivo do servidor, o SHA-256 e o snapshot do lake de cada
    escopo escolhido. Guarde-a junto com o resultado.
    """)
    return


@app.cell
def _(escolhidas, mo, snapshot, sus):
    citacoes = {
        _base: sus.citation_from_publications(_pubs, snapshot_id=snapshot, dataset=_base).text
        for _base, _pubs in escolhidas.items()
        if _pubs
    }
    _texto = "\n\n".join(citacoes.values())
    (
        mo.vstack(
            [
                mo.md(f"```text\n{_texto}\n```"),
                mo.download(_texto.encode(), filename="citacao.txt", label="Baixar citação"),
            ]
        )
        if citacoes
        else mo.md("Nenhum escopo escolhido para citar.")
    )
    return (citacoes,)


if __name__ == "__main__":
    app.run()
