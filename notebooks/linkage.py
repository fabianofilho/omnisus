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

"""Tutorial 6 · Colunas com o decoder e linkage determinístico entre SIM, SINASC, SIH, SIA, SINAN e CNES."""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium", app_title="Linkage entre as bases")


@app.cell
def _():
    import marimo as mo
    import polars as pl

    import omnisus as odb

    return mo, odb, pl


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Linkage · colunas com o decoder e linkage entre as bases

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/linkage.py)

    Os outros notebooks abrem uma base de cada vez. Este junta todas as que o
    DATASUS publica para a mesma UF e o mesmo ano (SIM e os seus subconjuntos,
    SINASC, SIH, SIA com BPA-I, RAAS e APAC, SINAN e CNES) e faz três coisas:

    1. **Confere cada coluna de cada tabela com o decoder**: o que o dicionário
       diz, quanto está vazio, um exemplo bruto e o mesmo exemplo decodificado,
       códigos sem rótulo e datas que não são datas.
    2. **Procura variáveis para linkage**: data de nascimento, sexo, município e
       CEP de residência, estabelecimento, data do evento. Onde existem, quanto
       estão preenchidas e quanto distinguem uma pessoa da outra.
    3. **Faz linkage determinístico** entre os pares de bases que mostraram
       potencial e **mede a qualidade** de cada um.

    Os dados públicos do DATASUS não trazem nome nem CPF. O linkage aqui usa só o
    que está publicado; o que ele consegue (e o que não consegue) é o assunto
    deste notebook.

    **Abrir este notebook não baixa nada.** Mude `EXECUTAR = False` para `True`
    na célula abaixo. O download de RR 2022 tem cerca de 63 MB, quase a metade
    em arquivos nacionais (subconjuntos do SIM e SINAN).

    Num estado grande, algumas bases não cabem na memória de um computador
    comum (o relatório diz quais). `PULAR` lista as que ficam de fora; as
    seções que dependem delas dizem isso em vez de calcular.
    """)
    return


@app.cell
def _(mo):
    # Parâmetros: edite e reexecute. O lake é o dos outros notebooks: data/raw/
    # (ou $OMNISUS_DATA_DIR).
    UF = "RR"
    ANO = 2022
    EXECUTAR = False
    # Bases a pular: as que não cabem na memória num estado grande. Na execução
    # de SP do relatório: {"sia_bpa_individualizado", "sih_servicos_profissionais",
    # "sia_apac_medicamentos"}.
    PULAR = set()
    executar = EXECUTAR or bool(mo.cli_args().get("executar"))
    return ANO, PULAR, UF, executar


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1 · O que o DATASUS publica, e baixar

    Antes de baixar, a lista do servidor (`odb.available`): quais meses de cada
    base existem para a UF e o ano dos parâmetros. Uma base que não aparece na
    lista não é baixada, e a tabela diz isso. SIH e SIA são mensais; o CNES é
    uma foto mensal do cadastro, e basta dezembro.

    SIM e SINASC são publicados **por UF de residência**; SIH, SIA e CNES, **por
    UF do estabelecimento**. Os subconjuntos do SIM (fetais, infantis, maternos,
    externos) e o SINAN são **nacionais**: um arquivo por ano para o Brasil
    todo, e a UF de residência sai de uma coluna (seção 3.3). Isso importa para
    o linkage (seção 4).
    """)
    return


@app.cell
def _(ANO, PULAR, UF, executar, mo, odb):
    mo.stop(not executar, mo.md("Defina `EXECUTAR = True` na célula de parâmetros."))
    SUBCONJUNTOS_SIM = [
        "sim_obitos_fetais",
        "sim_obitos_infantis",
        "sim_obitos_maternos",
        "sim_obitos_externos",
    ]
    SINAN = ["sinan_tuberculose", "sinan_hanseniase", "sinan_chagas"]
    NACIONAIS = SUBCONJUNTOS_SIM + SINAN
    APAC = [
        "sia_apac_quimioterapia",
        "sia_apac_radioterapia",
        "sia_apac_nefrologia",
        "sia_apac_tratamento_dialitico",
        "sia_apac_cirurgia_bariatrica",
        "sia_apac_acompanhamento_bariatrica",
        "sia_apac_medicamentos",
        "sia_apac_laudos_diversos",
        "sia_apac_fistula_arteriovenosa",
        "sia_apac_acompanhamento_multiprofissional",
    ]
    POR_UF = [
        "sim_obitos",
        "sinasc_nascidos_vivos",
        "sih_aih_reduzida",
        "sih_servicos_profissionais",
        "sih_aih_rejeitada",
        "sih_aih_rejeitada_erro",
        "sia_bpa_individualizado",
        "sia_psicossocial",
        "sia_atencao_domiciliar",
        *APAC,
        "cnes_estabelecimentos",
    ]

    def publicado(base, ano):
        """Escopos que o servidor lista agora para a UF (ou o Brasil) e o ano."""
        return odb.available(base, years=[ano], ufs=None if base in NACIONAIS else [UF])

    def carregar(base, escopos):
        meses = sorted({escopo.mes for escopo in escopos if escopo.mes is not None})
        if base == "cnes_estabelecimentos":
            meses = [12]  # uma foto do cadastro basta
        return odb.load(
            base,
            years=sorted({escopo.ano for escopo in escopos}),
            ufs=None if base in NACIONAIS else [UF],
            months=meses or None,
        )

    RD_SEGUINTE = "sih_aih_reduzida (ano seguinte)"
    publicados = {base: publicado(base, ANO) for base in POR_UF + NACIONAIS}
    bases = {
        base: carregar(base, escopos)
        for base, escopos in publicados.items()
        if escopos and base not in PULAR
    }
    # As AIHs do ano seguinte: uma AIH rejeitada pode voltar aprovada depois (seção 4.7).
    publicados[RD_SEGUINTE] = publicado("sih_aih_reduzida", ANO + 1)
    rd_seguinte = (
        carregar("sih_aih_reduzida", publicados[RD_SEGUINTE])
        if publicados[RD_SEGUINTE] and RD_SEGUINTE not in PULAR
        else None
    )
    return APAC, SINAN, SUBCONJUNTOS_SIM, bases, publicados, rd_seguinte


@app.cell
def _(bases, pl, publicados, rd_seguinte):
    def carregada(base):
        return rd_seguinte if base.endswith("(ano seguinte)") else bases.get(base)

    def situacao(base, escopos):
        if carregada(base) is not None:
            return "baixada"
        return "pulada (PULAR)" if escopos else "não publicada"

    pl.DataFrame(
        [
            {
                "base": base,
                "escopos publicados": len(escopos),
                "meses": ", ".join(str(m) for m in sorted(e.mes for e in escopos if e.mes)),
                "situação": situacao(base, escopos),
                "linhas": carregada(base).height if carregada(base) is not None else None,
                "colunas": carregada(base).width if carregada(base) is not None else None,
            }
            for base, escopos in publicados.items()
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2 · Coluna por coluna, com o decoder

    `odb.check_columns` confere cada coluna com o dicionário da base e devolve uma
    linha por coluna:

    | campo | o que é |
    | --- | --- |
    | `rule` | a regra do dicionário: mapa de códigos, data no formato declarado, `not in dictionary` ou nenhuma |
    | `pct_empty` | nulo ou vazio |
    | `example_code` → `example_label` | o primeiro valor preenchido e o seu rótulo |
    | `unlabelled_codes` | valores que o mapa de códigos não conhece, e em quantas linhas aparecem (`unlabelled_rows`) |
    | `pct_invalid_dates` | entre as preenchidas, as que não são uma data no formato declarado |
    | `date_min`, `date_max` | a menor e a maior data: um ano impossível aparece aqui |
    """)
    return


@app.cell
def _(bases, odb):
    verificacoes = {base: odb.check_columns(base, dados) for base, dados in bases.items()}
    return (verificacoes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.1 · Resumo por base
    """)
    return


@app.cell
def _(pl, verificacoes):
    pl.DataFrame(
        [
            {
                "base": base,
                "colunas": tabela.height,
                "com regra": tabela.filter(
                    pl.col("rule").is_not_null() & (pl.col("rule") != "not in dictionary")
                ).height,
                "fora do dicionário": tabela.filter(pl.col("rule") == "not in dictionary").height,
                "sempre vazias": tabela.filter(pl.col("pct_empty") == 100).height,
                "com códigos sem rótulo": tabela.filter(pl.col("unlabelled_rows") > 0).height,
                "com datas inválidas": tabela.filter(pl.col("pct_invalid_dates") > 0).height,
            }
            for base, tabela in verificacoes.items()
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Colunas que o dicionário declara e o arquivo não traz:
    """)
    return


@app.cell
def _(bases, odb, pl):
    pl.DataFrame(
        {
            "base": list(bases),
            "declaradas e ausentes no arquivo": [
                ", ".join(
                    campo["name"]
                    for campo in odb.describe_dataset(base)["schema"]["fields"]
                    if campo["name"] not in dados.columns
                )
                for base, dados in bases.items()
            ],
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Registros por mês de competência, nas bases mensais. Um mês com muito menos
    registros que os outros muda a taxa de ligação de quem depende dele.
    """)
    return


@app.cell
def _(bases, pl):
    pl.concat(
        [
            dados.group_by("mes").len("registros").with_columns(pl.lit(base).alias("base"))
            for base, dados in bases.items()
            if "mes" in dados.columns and base != "cnes_estabelecimentos"
        ]
    ).sort("mes").pivot(on="mes", index="base", values="registros")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.2 · Base por base
    """)
    return


@app.cell
def _(mo, verificacoes):
    mo.vstack(
        [mo.vstack([mo.md(f"#### `{base}`"), tabela]) for base, tabela in verificacoes.items()]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3 · Variáveis candidatas a linkage

    Sem nome nem CPF, um registro só se liga a outro por uma **combinação** de
    variáveis, ou por um **identificador** que as duas bases publicam (o
    número da AIH, o CNS do paciente). A tabela abaixo diz quanto de cada
    candidata está preenchido em cada base (a partir da verificação da seção
    2); vazio quer dizer que a base não tem a coluna.
    """)
    return


@app.cell
def _(APAC, SINAN, SUBCONJUNTOS_SIM, pl, verificacoes):
    CANDIDATAS = {
        "data de nascimento": {
            "sim_obitos": "dtnasc",
            "sinasc_nascidos_vivos": "dtnasc",
            "sih_aih_reduzida": "nasc",
            "sih_aih_rejeitada": "nasc",
            "sia_bpa_individualizado": "dtnasc",
            "sia_psicossocial": "dtnasc",
            **{base: "dtnasc" for base in SUBCONJUNTOS_SIM},
        },
        "ano de nascimento": {base: "ano_nasc" for base in SINAN},
        "idade": {"sih_aih_reduzida": "idade", **{base: "ap_nuidade" for base in APAC}},
        "sexo": {
            "sim_obitos": "sexo",
            "sinasc_nascidos_vivos": "sexo",
            "sih_aih_reduzida": "sexo",
            "sih_aih_rejeitada": "sexo",
            "sia_bpa_individualizado": "sexopac",
            "sia_psicossocial": "sexopac",
            **{base: "ap_sexo" for base in APAC},
            **{base: "sexo" for base in SUBCONJUNTOS_SIM},
            **{base: "cs_sexo" for base in SINAN},
        },
        "município de residência": {
            "sim_obitos": "codmunres",
            "sinasc_nascidos_vivos": "codmunres",
            "sih_aih_reduzida": "munic_res",
            "sih_aih_rejeitada": "munic_res",
            "sih_aih_rejeitada_erro": "mun_res",
            "sia_bpa_individualizado": "munpac",
            "sia_psicossocial": "munpac",
            **{base: "ap_munpcn" for base in APAC},
            **{base: "codmunres" for base in SUBCONJUNTOS_SIM},
            **{base: "id_mn_resi" for base in SINAN},
        },
        "CEP de residência": {
            "sih_aih_reduzida": "cep",
            "sih_aih_rejeitada": "cep",
            **{base: "ap_ceppcn" for base in APAC},
        },
        "estabelecimento (CNES)": {
            "sim_obitos": "codestab",
            "sinasc_nascidos_vivos": "codestab",
            "sih_aih_reduzida": "cnes",
            "sih_servicos_profissionais": "sp_cnes",
            "sih_aih_rejeitada": "cnes",
            "sih_aih_rejeitada_erro": "cnes",
            "sia_bpa_individualizado": "coduni",
            "sia_psicossocial": "cnes_exec",
            **{base: "ap_coduni" for base in APAC},
            **{base: "codestab" for base in SUBCONJUNTOS_SIM},
            **{base: "id_unidade" for base in SINAN},
            "cnes_estabelecimentos": "cnes",
        },
        "data do evento": {
            "sim_obitos": "dtobito",
            "sinasc_nascidos_vivos": "dtnasc",
            "sih_aih_reduzida": "dt_saida",
            "sih_servicos_profissionais": "sp_dtsaida",
            "sih_aih_rejeitada": "dt_saida",
            "sih_aih_rejeitada_erro": "dt_saida",
            "sia_bpa_individualizado": "dt_atend",
            "sia_psicossocial": "dt_atend",
            **{base: "ap_cmp" for base in APAC},
            **{base: "dtobito" for base in SUBCONJUNTOS_SIM},
            **{base: "dt_notific" for base in SINAN},
        },
        "data de nascimento da mãe": {"sinasc_nascidos_vivos": "dtnascmae"},
        "idade da mãe": {"sim_obitos": "idademae", "sinasc_nascidos_vivos": "idademae"},
        "peso ao nascer": {"sim_obitos": "peso", "sinasc_nascidos_vivos": "peso"},
        "número da AIH": {
            "sih_aih_reduzida": "n_aih",
            "sih_servicos_profissionais": "sp_naih",
            "sih_aih_rejeitada": "n_aih",
            "sih_aih_rejeitada_erro": "aih",
            "sia_apac_cirurgia_bariatrica": "ab_numaih",
            "sia_apac_acompanhamento_bariatrica": "ab_numaih",
        },
        "CNS do paciente (criptografado)": {
            "sia_bpa_individualizado": "cns_pac",
            "sia_psicossocial": "cns_pac",
            **{base: "ap_cnspcn" for base in APAC},
        },
    }

    # Só as bases baixadas e as colunas que o arquivo traz de fato.
    candidatas = pl.DataFrame(
        [
            {
                "variável": variavel,
                "base": base,
                "% preenchido": 100 - linha["pct_empty"].item(),
            }
            for variavel, colunas in CANDIDATAS.items()
            for base, coluna in colunas.items()
            if base in verificacoes
            for linha in [verificacoes[base].filter(pl.col("column") == coluna)]
            if linha.height
        ]
    )
    candidatas.pivot(on="variável", index="base", values="% preenchido")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.1 · CEP

    Onde há CEP? Procurando `cep` no nome das colunas de cada base:
    """)
    return


@app.cell
def _(bases, pl):
    pl.DataFrame(
        {
            "base": list(bases),
            "colunas com 'cep' no nome": [
                ", ".join(c for c in dados.columns if "cep" in c) or "nenhuma"
                for dados in bases.values()
            ],
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    O CEP do paciente está no SIH (AIH reduzida e rejeitada) e nas APAC do SIA
    (`ap_ceppcn`); no CNES, `cod_cep` é o endereço do estabelecimento. E quão
    específico ele é? No SIH, por município de residência: quantos CEPs
    distintos e que parte das internações cai no CEP mais comum.
    """)
    return


@app.cell
def _(bases, pl):
    (
        bases["sih_aih_reduzida"]
        .group_by("munic_res", "cep")
        .len("internacoes")
        .group_by("munic_res")
        .agg(
            pl.col("internacoes").sum(),
            pl.len().alias("ceps_distintos"),
            (100 * pl.col("internacoes").max() / pl.col("internacoes").sum())
            .round(1)
            .alias("% no CEP mais comum"),
        )
        .sort(["internacoes", "munic_res"], descending=[True, False])
        .head(15)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.2 · Sexo: quatro codificações, um rótulo

    Cada base grava o sexo de um jeito. O `x-decode` do dicionário traduz o
    código; a primeira letra do rótulo (`M`/`F`) vira a variável comum. O que o
    dicionário rotula como ignorado (ou "Não exigido") vira nulo e não entra no
    linkage. Bases cujo dicionário não rotula o sexo (AIH rejeitada,
    subconjuntos do SIM) ficam fora desta tabela: nelas o sexo não é usado.
    """)
    return


@app.cell
def _(bases, odb, pl):
    def rotulo(base, coluna):
        """Troca o código pelo rótulo que `odb.label` dá a ele."""
        codigos = bases[base].select(pl.col(coluna).unique())
        mapa = dict(odb.label(base, codigos).iter_rows())
        return pl.col(coluna).replace_strict(mapa, default=None, return_dtype=pl.String)

    def sexo(base, coluna):
        letra = rotulo(base, coluna).str.slice(0, 1)
        return pl.when(letra.is_in(["M", "F"])).then(letra).alias("sexo")

    def tem_rotulos(base, coluna):
        """O dicionário da base tem rótulos para a coluna?"""
        return f"{coluna}_rotulo" in odb.label(base, bases[base].head(0)).columns

    return rotulo, sexo, tem_rotulos


@app.cell
def _(APAC, SINAN, bases, pl, rotulo, sexo, tem_rotulos):
    COLUNA_DO_SEXO = {
        "sim_obitos": "sexo",
        "sinasc_nascidos_vivos": "sexo",
        "sih_aih_reduzida": "sexo",
        "sia_bpa_individualizado": "sexopac",
        "sia_psicossocial": "sexopac",
        **{base: "ap_sexo" for base in APAC},
        **{base: "cs_sexo" for base in SINAN},
    }
    pl.concat(
        [
            bases[base]
            .select(
                pl.lit(base).alias("base"),
                pl.col(coluna).cast(pl.String).alias("código"),
                rotulo(base, coluna).alias("rótulo do decoder"),
                sexo(base, coluna),
            )
            .group_by("base", "código", "rótulo do decoder", "sexo")
            .len("registros")
            for base, coluna in COLUNA_DO_SEXO.items()
            if base in bases and tem_rotulos(base, coluna)
        ]
    ).sort("base", "código")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.3 · Uma tabela padronizada por base

    Mesmos nomes em todas: `nasc` (data de nascimento), `sexo`, `mun`
    (município de residência), `estab` (CNES), `data_evento`, `idade` (anos
    completos no evento), `ano_nasc`. Datas viram `Date`, textos vazios viram
    nulo, números viram inteiros. Rótulos (`parto`, `gravidez`, `lococor`...)
    vêm do dicionário, para comparar bases pelo significado e não pelo código.

    No BPA-I, na RAAS psicossocial e nas APAC, cada linha é um procedimento; a
    pessoa é o CNS do paciente, que vem criptografado (seção 4.8 confere se ele
    se comporta como um identificador).
    """)
    return


@app.cell
def _(bases, pl, rotulo, sexo):
    def data(coluna, formato):
        return pl.col(coluna).str.strip_chars().str.strptime(pl.Date, formato, strict=False)

    def texto(coluna):
        valor = pl.col(coluna).cast(pl.String).str.strip_chars()
        return pl.when(valor != "").then(valor)

    def numero(coluna):
        return pl.col(coluna).cast(pl.String).str.strip_chars().cast(pl.Int32, strict=False)

    def anos_completos(nascimento, dia):
        """Idade em anos no dia, aproximada por 365,25 dias por ano."""
        dias = (pl.col(dia) - pl.col(nascimento)).dt.total_days()
        return (dias / 365.25).floor().cast(pl.Int32)

    sim_p = (
        bases["sim_obitos"]
        .with_row_index("id")
        .select(
            "id",
            data("dtnasc", "%d%m%Y").alias("nasc"),
            sexo("sim_obitos", "sexo"),
            texto("codmunres").alias("mun"),
            texto("codestab").alias("estab"),
            data("dtobito", "%d%m%Y").alias("data_evento"),
            texto("codmunocor").alias("mun_evento"),
            numero("peso").alias("peso"),
            numero("idademae").alias("idademae"),
            numero("semagestac").alias("semagestac"),
            rotulo("sim_obitos", "parto"),
            rotulo("sim_obitos", "gravidez"),
            rotulo("sim_obitos", "gestacao"),
            rotulo("sim_obitos", "lococor"),
            texto("causabas").alias("cid"),
        )
        .with_columns(
            pl.col("nasc").dt.year().cast(pl.Int32).alias("ano_nasc"),
            anos_completos("nasc", "data_evento").alias("idade"),  # na data do óbito
        )
    )

    nv_p = (
        bases["sinasc_nascidos_vivos"]
        .with_row_index("id")
        .select(
            "id",
            data("dtnasc", "%d%m%Y").alias("nasc"),
            sexo("sinasc_nascidos_vivos", "sexo"),
            texto("codmunres").alias("mun"),
            texto("codestab").alias("estab"),
            data("dtnasc", "%d%m%Y").alias("data_evento"),
            texto("codmunnasc").alias("mun_evento"),
            numero("peso").alias("peso"),
            numero("idademae").alias("idademae"),
            numero("semagestac").alias("semagestac"),
            rotulo("sinasc_nascidos_vivos", "parto"),
            rotulo("sinasc_nascidos_vivos", "gravidez"),
            rotulo("sinasc_nascidos_vivos", "gestacao"),
            rotulo("sinasc_nascidos_vivos", "locnasc"),
            data("dtnascmae", "%d%m%Y").alias("nasc_mae"),
        )
    )

    sih_p = (
        bases["sih_aih_reduzida"]
        .with_row_index("id")
        .select(
            "id",
            data("nasc", "%Y%m%d").alias("nasc"),
            sexo("sih_aih_reduzida", "sexo"),
            texto("munic_res").alias("mun"),
            texto("cep").alias("cep"),
            texto("cnes").alias("estab"),
            data("dt_inter", "%Y%m%d").alias("inter"),
            data("dt_saida", "%Y%m%d").alias("data_evento"),
            texto("munic_mov").alias("mun_evento"),
            pl.col("morte"),
            texto("diag_princ").alias("cid"),
        )
        .with_columns(anos_completos("nasc", "inter").alias("idade"))  # na internação
    )

    def pessoas_por_cns(base, coluna_estab):
        """BPA-I e RAAS: uma linha por procedimento; a pessoa é o CNS (criptografado)."""
        procedimentos = bases[base].select(
            texto("cns_pac").alias("cns"),
            data("dtnasc", "%Y%m%d").alias("nasc"),
            sexo(base, "sexopac"),
            texto("munpac").alias("mun"),
            texto(coluna_estab).alias("estab"),
            texto("ufmun").alias("mun_evento"),
            (pl.col("dt_atend") + "01")
            .str.strptime(pl.Date, "%Y%m%d", strict=False)
            .alias("competencia"),
        )
        pessoas = (
            procedimentos.drop_nulls("cns")
            .group_by("cns", "nasc", "sexo", "mun", maintain_order=True)
            .agg(
                pl.col("competencia").min().alias("primeira"),
                pl.col("competencia").max().alias("ultima"),
                pl.len().alias("procedimentos"),
            )
            .with_row_index("id")
        )
        return procedimentos, pessoas

    # Uma base pulada (PULAR) fica None; as seções que dependem dela dizem isso.
    sia_p = pessoas_sia = pessoas_ps = None
    if "sia_bpa_individualizado" in bases:
        sia_p, pessoas_sia = pessoas_por_cns("sia_bpa_individualizado", "coduni")
    if "sia_psicossocial" in bases:
        _, pessoas_ps = pessoas_por_cns("sia_psicossocial", "cnes_exec")

    # O código IBGE da UF: o SIM é por residência, então todos começam com ele.
    codigo_uf = sim_p["mun"].drop_nulls().str.slice(0, 2).mode().sort()[0]

    sih_p.head()
    return (
        codigo_uf,
        data,
        numero,
        nv_p,
        pessoas_ps,
        pessoas_sia,
        sia_p,
        sih_p,
        sim_p,
        texto,
        anos_completos,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    As APAC e o SINAN, padronizados do mesmo jeito:

    - **APAC**: uma linha por CNS, com o sexo, o CEP, o município e o
      estabelecimento mais frequentes, a menor idade em anos (a APAC não traz a
      data de nascimento, só `ap_nuidade` na unidade de `ap_coidade`) e a
      primeira competência. Sem rótulo para `ap_coidade` no dicionário, a idade
      fica nula.
    - **SINAN**: os casos de residentes da UF (`id_mn_resi`), com o ano de
      nascimento, o sexo, a data de notificação, o encerramento pelo rótulo do
      dicionário e se ele é um óbito (rótulo que começa com "Óbito").
    """)
    return


@app.cell
def _(
    APAC,
    SINAN,
    bases,
    codigo_uf,
    numero,
    pl,
    rotulo,
    sexo,
    tem_rotulos,
    texto,
):
    def pessoas_da_apac(base):
        if tem_rotulos(base, "ap_coidade"):
            idade = pl.when(rotulo(base, "ap_coidade") == "Anos").then(numero("ap_nuidade"))
        else:
            idade = pl.lit(None, dtype=pl.Int32)
        return (
            bases[base]
            .select(
                texto("ap_cnspcn").alias("cns"),
                sexo(base, "ap_sexo")
                if tem_rotulos(base, "ap_sexo")
                else pl.lit(None, pl.String).alias("sexo"),
                texto("ap_ceppcn").alias("cep"),
                texto("ap_munpcn").alias("mun"),
                texto("ap_coduni").alias("estab"),
                idade.alias("idade"),
                (pl.col("ap_cmp").cast(pl.String) + "01")
                .str.strptime(pl.Date, "%Y%m%d", strict=False)
                .alias("competencia"),
            )
            .drop_nulls("cns")
            .group_by("cns")
            .agg(
                # O mais frequente; num empate, o menor, para o resultado não variar.
                pl.col("sexo", "cep", "mun", "estab").drop_nulls().mode().sort().first(),
                pl.col("idade").min(),
                pl.col("competencia").min(),
            )
            .with_row_index("id")
        )

    pessoas_apac = {base: pessoas_da_apac(base) for base in APAC if base in bases}

    ENCERRAMENTO = {
        "sinan_tuberculose": "situa_ence",
        "sinan_hanseniase": "tpalta_n",
        "sinan_chagas": "evolucao",
    }

    def casos_do_sinan(base):
        dados = bases[base]
        return (
            dados.filter(texto("id_mn_resi").str.starts_with(codigo_uf))
            .with_row_index("id")
            .select(
                "id",
                numero("ano_nasc").alias("ano_nasc"),
                sexo(base, "cs_sexo"),
                texto("id_mn_resi").alias("mun"),
                pl.col("dt_notific").alias("notificacao"),
                rotulo(base, ENCERRAMENTO[base]).alias("encerramento"),
                rotulo(base, ENCERRAMENTO[base])
                .str.to_lowercase()
                .str.starts_with("óbito")
                .fill_null(False)
                .alias("obito"),
                (
                    pl.col("dt_obito") if "dt_obito" in dados.columns else pl.lit(None, pl.Date)
                ).alias("data_evento"),
            )
        )

    casos_sinan = {base: casos_do_sinan(base) for base in SINAN if base in bases}
    return casos_sinan, pessoas_apac


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.4 · Quanto cada combinação distingue

    `% única` = parte dos registros (com todas as chaves preenchidas) cuja
    combinação aparece **uma só vez** na base. Uma chave que não é única dentro
    da própria base não serve para achar um registro na outra.

    No SIH não há identificador de paciente: uma pessoa internada duas vezes
    também conta como combinação repetida.
    """)
    return


@app.cell
def _(casos_sinan, nv_p, pessoas_apac, pessoas_ps, pessoas_sia, pl, sih_p, sim_p):
    def unicidade(tabela, chaves):
        """% dos registros (com as chaves preenchidas) cuja combinação é única na base."""
        completos = tabela.drop_nulls(chaves)
        unicos = completos.filter(pl.len().over(chaves) == 1).height
        return round(100 * unicos / max(completos.height, 1), 1)

    COMBINACOES = [
        ("SINASC", nv_p, ["nasc", "sexo", "mun"]),
        ("SINASC", nv_p, ["nasc", "sexo", "mun", "peso"]),
        ("SINASC", nv_p, ["nasc", "sexo", "mun", "peso", "idademae"]),
        ("SINASC (mães)", nv_p, ["nasc_mae", "estab", "data_evento"]),
        ("SIM", sim_p, ["nasc", "sexo", "mun"]),
        ("SIM", sim_p, ["nasc", "sexo", "data_evento"]),
        ("SIM", sim_p, ["nasc", "sexo", "data_evento", "estab"]),
        ("SIM", sim_p, ["mun", "sexo", "idade"]),
        ("SIM", sim_p, ["ano_nasc", "sexo", "mun"]),
        ("SIH", sih_p, ["nasc", "sexo", "mun"]),
        ("SIH", sih_p, ["nasc", "sexo", "mun", "cep"]),
        ("SIH", sih_p, ["nasc", "sexo", "data_evento", "estab"]),
        ("SIH", sih_p, ["cep", "sexo", "idade"]),
        ("SIA BPA-I (pessoas por CNS)", pessoas_sia, ["nasc", "sexo", "mun"]),
        ("SIA RAAS psicossocial (pessoas por CNS)", pessoas_ps, ["nasc", "sexo", "mun"]),
        *[
            (f"{base} (pessoas por CNS)", tabela, ["cep", "sexo", "idade"])
            for base, tabela in pessoas_apac.items()
        ],
        *[(base, tabela, ["ano_nasc", "sexo", "mun"]) for base, tabela in casos_sinan.items()],
    ]
    pl.DataFrame(
        [
            {
                "base": nome,
                "chaves": " + ".join(chaves),
                "registros": tabela.height,
                "% com chaves completas": round(
                    100 * tabela.drop_nulls(chaves).height / max(tabela.height, 1), 1
                ),
                "% única": unicidade(tabela, chaves),
            }
            for nome, tabela, chaves in COMBINACOES
            if tabela is not None
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3.5 · Pares de bases com potencial

    | par | quem se liga | chaves possíveis |
    | --- | --- | --- |
    | **SIH → SIM** | óbitos no hospital (`morte = Com óbito`) com a declaração de óbito | nascimento, sexo, data de saída = data do óbito, hospital |
    | **SIM → SINASC** | óbitos de menores de 1 ano com a declaração de nascido vivo | nascimento, sexo, município, peso, idade da mãe |
    | **SINASC → SIH** | o parto com a internação da mãe | nascimento **da mãe**, hospital, dia do parto dentro da internação |
    | **SIM → SIA** | quem morreu com quem teve atendimento ambulatorial | nascimento, sexo, município (sem evento em comum) |
    | **todas → CNES** | o estabelecimento de cada registro | código CNES |
    | **SIH SP → RD** | os atos profissionais com a sua AIH | número da AIH (chave exata) |
    | **SIH RJ → RD** | a AIH rejeitada com uma aprovada | número da AIH (chave exata) |
    | **SIA entre famílias** | a mesma pessoa no BPA-I, na RAAS e nas APAC | CNS criptografado (chave exata) |
    | **RAAS, BPA-I → SIM, SIH** | o atendimento ambulatorial com o óbito ou a internação | nascimento, sexo, município |
    | **APAC → SIH, SIM** | quimioterapia, radioterapia e diálise com a internação ou o óbito da mesma doença | CEP (ou município), sexo, idade |
    | **subconjuntos do SIM → SIM** | a declaração do subconjunto com a do arquivo por UF | todas as colunas em comum |
    | **SIM maternos → SIH** | o óbito materno com a internação | nascimento, data do óbito = data de saída, hospital |
    | **SINAN → SIM** | o caso notificado com o óbito | ano de nascimento, sexo, município |
    | **APAC bariátrica → SIH** | a APAC com a AIH da cirurgia | número da AIH (chave exata) |

    As quatro primeiras são as deste notebook (seções 4.1 a 4.4); a quinta é uma
    checagem de códigos (4.5); as outras são as seções 4.6 a 4.13.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4 · Linkage determinístico

    **Determinístico** quer dizer: dois registros são a mesma pessoa se as
    chaves forem **idênticas**. Três regras simples:

    1. **1:1** — só vale a combinação que aparece uma vez em cada base; chave
       repetida é ambígua e fica de fora (`ligar`).
    2. **Em passos** — primeiro a chave mais rigorosa; quem sobrou tenta a
       próxima (`ligar_em_passos`).
    3. **Controle negativo** — em cada passo, o mesmo linkage com a data de
       nascimento de A deslocada em 7 dias, sobre os mesmos registros que
       sobraram. Ninguém é a mesma pessoa que alguém nascido uma semana depois,
       então todo par achado ali é **por acaso**; o número estima quantos pares
       do passo real também são por acaso.

    Sem data de nascimento, o controle desloca outra coluna: o **ano de
    nascimento** em 1 ano (SINAN) e a **idade** em 2 anos (APAC). A idade, ao
    contrário do ano de nascimento, muda entre dois eventos do mesmo ano: um
    par verdadeiro pode diferir em 1 ano de idade, e um controle de 1 ano
    acharia pares verdadeiros (a seção 4.10 mostra isso nos números).

    Numa **chave exata** (número da AIH, CNS), o controle troca cada
    identificador pelo **vizinho** na ordem (`vizinho`): o par formado é, com
    certeza, de registros diferentes. O quanto esses pares concordam em sexo,
    datas e estabelecimento é a concordância por acaso, ao lado da dos pares
    reais.

    **Veredito** de cada linkage (seção 5), decidido antes dos números:

    - **viável**: todo passo mantido tem até 5% estimado por acaso, e a
      validação mais forte com variável que não foi chave concorda em pelo
      menos 90% dos pares;
    - **com cautela**: de 5% a 20% por acaso, ou validação de 75% a 90%;
    - **não viável**: o resto. Um passo com mais de 20% por acaso, ou cujo
      controle acha pelo menos tantos pares quanto ele, sai da conta.
    """)
    return


@app.cell
def _(pl):
    def ligar(a, b, chaves):
        """Linkage determinístico 1:1: a combinação precisa ser única em A e em B."""
        a_unicos = a.drop_nulls(chaves).filter(pl.len().over(chaves) == 1)
        b_unicos = b.drop_nulls(chaves).filter(pl.len().over(chaves) == 1)
        return a_unicos.select("id", *chaves).join(
            b_unicos.select(pl.col("id").alias("id_b"), *chaves), on=chaves
        )

    def ligar_em_passos(a, b, passos, deslocar="nasc", delta=None):
        """Aplica os passos em ordem; cada passo só usa quem ainda não foi ligado.

        Devolve os pares e, por passo, quantos pares o controle negativo acha
        com os mesmos registros restantes: a coluna `deslocar` de A somada a
        `delta` (padrão: nascimento + 7 dias).
        """
        delta = pl.duration(days=7) if delta is None else delta
        pares = pl.DataFrame(schema={"id": pl.UInt32, "id_b": pl.UInt32, "passo": pl.Int32})
        relatorio = []
        for passo, chaves in enumerate(passos, start=1):
            resto_a = a.join(pares.select("id"), on="id", how="anti")
            resto_b = b.join(pares.select(pl.col("id_b").alias("id")), on="id", how="anti")
            novos = ligar(resto_a, resto_b, chaves)
            por_acaso = ligar(resto_a.with_columns(pl.col(deslocar) + delta), resto_b, chaves)
            relatorio.append(
                {
                    "passo": passo,
                    "chaves": " + ".join(chaves),
                    "pares": novos.height,
                    "pares no controle negativo": por_acaso.height,
                }
            )
            novos = novos.select("id", "id_b", pl.lit(passo, dtype=pl.Int32).alias("passo"))
            pares = pl.concat([pares, novos])
        relatorio = pl.DataFrame(relatorio).with_columns(
            pl.when(pl.col("pares") > 0)
            .then(100 * pl.col("pares no controle negativo") / pl.col("pares"))
            .round(1)
            .alias("% estimado por acaso")
        )
        return pares, relatorio

    def detalhar(pares, a, b):
        """Junta aos pares as variáveis das duas bases (as de B com sufixo _b)."""
        return pares.join(a, on="id").join(b.rename(lambda coluna: f"{coluna}_b"), on="id_b")

    def concordancia(detalhe, coluna, valores=None, tolerancia=None):
        """% de pares em que a coluna é igual nas duas bases, entre os que têm as duas preenchidas.

        `valores` restringe a categorias informativas (sem "Ignorado"); `tolerancia`
        aceita números que diferem até esse tanto.
        """
        a, b = pl.col(coluna), pl.col(f"{coluna}_b")
        ambos = detalhe.drop_nulls([coluna, f"{coluna}_b"])
        if valores is not None:
            ambos = ambos.filter(a.is_in(valores) & b.is_in(valores))
        iguais = ambos.filter(a == b if tolerancia is None else (a - b).abs() <= tolerancia).height
        return {
            "variável": coluna if tolerancia is None else f"{coluna} (±{tolerancia})",
            "pares comparáveis": ambos.height,
            "% iguais": round(100 * iguais / max(ambos.height, 1), 1),
        }

    def vizinho(tabela, chave):
        """Troca cada identificador pelo seguinte na ordem: o controle de uma chave exata."""
        ordem = tabela[chave].drop_nulls().unique().sort()
        return tabela.with_columns(
            pl.col(chave).replace_strict(ordem[:-1], ordem[1:], default=None)
        )

    def pares_por_chave(a, b, chave):
        """Os pares de uma chave exata e os do controle (o identificador vizinho).

        As colunas de B ganham o sufixo _b, como em `detalhar`.
        """
        b = b.rename(lambda coluna: coluna if coluna == chave else f"{coluna}_b")
        return a.join(b, on=chave), vizinho(a, chave).join(b, on=chave)

    def comparar(reais, controle, variaveis):
        """Concordância nos pares reais e, ao lado, nos pares do controle.

        `variaveis`: pares (coluna, tolerância ou None).
        """
        return pl.DataFrame(
            [
                {
                    **concordancia(reais, coluna, tolerancia=tolerancia),
                    "% iguais no controle": concordancia(controle, coluna, tolerancia=tolerancia)[
                        "% iguais"
                    ],
                }
                for coluna, tolerancia in variaveis
            ]
        )

    def pct(tabela, variavel, coluna="% iguais"):
        return tabela.filter(pl.col("variável") == variavel)[coluna].item()

    def veredito(pares, acaso, validacao):
        """A regra da seção 4, decidida antes dos números."""
        if pares == 0 or validacao is None:
            return "não viável"
        acaso = 0 if acaso is None else acaso
        if acaso <= 5 and validacao >= 90:
            return "viável"
        if acaso <= 20 and validacao >= 75:
            return "com cautela"
        return "não viável"

    def resumo(nome, a, pares, passos, validacao, pct_validacao):
        """Uma linha da tabela da seção 5.

        Sai da conta o passo com mais de 20% estimado por acaso, ou cujo controle
        acha pelo menos tantos pares quanto ele. `passos` é None
        numa chave exata: ali não há pares por acaso para contar, e a validação
        traz a concordância do controle ao lado.
        """
        por_acaso = descartados = pares_descartados = None
        if passos is not None:
            controle, reais = pl.col("pares no controle negativo"), pl.col("pares")
            ruins = passos.filter(
                (pl.col("% estimado por acaso") > 20) | ((controle > 0) & (controle >= reais))
            )["passo"]
            pares_descartados = pares.filter(pl.col("passo").is_in(ruins.implode())).height
            pares = pares.filter(~pl.col("passo").is_in(ruins.implode()))
            por_acaso = passos.filter(~pl.col("passo").is_in(ruins.implode()))[
                "pares no controle negativo"
            ].sum()
            descartados = ", ".join(str(p) for p in ruins) or "—"
        acaso = None if por_acaso is None else round(100 * por_acaso / max(pares.height, 1), 1)
        return {
            "linkage": nome,
            "registros em A": a.height,
            "pares": pares.height,
            "% de A ligado": round(100 * pares.height / max(a.height, 1), 1),
            "passos descartados": descartados,
            "pares descartados": pares_descartados,
            "pares no controle negativo": por_acaso,
            "% estimado por acaso": acaso,
            "validação": validacao,
            "veredito": veredito(pares.height, acaso, pct_validacao),
        }

    def nao_executado(nome, motivo):
        """A linha da seção 5 de um linkage que esta execução não pôde fazer."""
        return {"linkage": nome, "veredito": motivo}

    return (
        comparar,
        concordancia,
        detalhar,
        ligar,
        ligar_em_passos,
        nao_executado,
        pares_por_chave,
        pct,
        resumo,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Para comparar diagnósticos entre bases, o capítulo da CID-10 de cada código.
    A tabela `aux_cid10` vem dentro da biblioteca (sem rede) e é gravada no lake.
    """)
    return


@app.cell
def _(executar, mo, odb, pl):
    mo.stop(not executar)
    with odb.Lake.local() as lake:
        lake.bootstrap_auxiliares()
    with odb.LakeReader() as leitor:
        cid10 = (
            leitor.connect()
            .sql(f"SELECT codigo, descricao, capitulo FROM {leitor.alias}.aux_cid10")
            .pl()
        )
    # O capítulo depende só dos três primeiros caracteres do código.
    capitulo_cid = cid10.select(
        pl.col("codigo").str.slice(0, 3).alias("categoria"), "capitulo"
    ).unique()

    def com_capitulo(tabela, coluna, nome):
        return tabela.join(
            capitulo_cid.rename({"categoria": "_categoria", "capitulo": nome}),
            left_on=pl.col(coluna).str.slice(0, 3),
            right_on="_categoria",
            how="left",
        )

    return cid10, com_capitulo


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.1 · SIH → SIM: óbitos no hospital

    A: internações que terminaram em óbito (`morte` = `Com óbito`).
    B: todas as declarações de óbito.

    | passo | chaves |
    | --- | --- |
    | 1 | nascimento + sexo + data de saída = data do óbito + hospital |
    | 2 | nascimento + sexo + data (hospital diferente ou vazio no SIM) |
    | 3 | nascimento + sexo + município + hospital (data diferente) |
    """)
    return


@app.cell
def _(ligar_em_passos, pl, sih_p, sim_p):
    obitos_sih = sih_p.filter(pl.col("morte") == 1)  # 1 = "Com óbito" no dicionário
    PASSOS_SIH_SIM = [
        ["nasc", "sexo", "data_evento", "estab"],
        ["nasc", "sexo", "data_evento"],
        ["nasc", "sexo", "mun", "estab"],
    ]
    pares_sih_sim, passos_sih_sim = ligar_em_passos(obitos_sih, sim_p, PASSOS_SIH_SIM)
    passos_sih_sim
    return obitos_sih, pares_sih_sim, passos_sih_sim


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Quantos óbitos do SIH acharam a declaração, por mês da saída.** O arquivo
    de um mês de competência traz saídas de meses anteriores; um óbito com saída
    fora do ano não tem declaração no SIM baixado.
    """)
    return


@app.cell
def _(obitos_sih, pares_sih_sim, pl):
    (
        obitos_sih.with_columns(pl.col("id").is_in(pares_sih_sim["id"].implode()).alias("ligado"))
        .group_by(pl.col("data_evento").dt.strftime("%Y-%m").alias("mes_da_saida"))
        .agg(pl.len().alias("obitos_sih"), pl.col("ligado").sum().alias("ligados"))
        .with_columns((100 * pl.col("ligados") / pl.col("obitos_sih")).round(1).alias("% ligado"))
        .sort("mes_da_saida")
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Validação com variáveis que não são chave.** Em pares verdadeiros, o SIM
    deve dizer que o óbito foi em hospital, e o município de residência deve
    bater (ele só é chave no passo 3). O diagnóstico da internação e a causa
    básica do óbito medem coisas diferentes; a concordância de capítulo da
    CID-10 é informativa, não um critério.
    """)
    return


@app.cell
def _(
    com_capitulo,
    concordancia,
    detalhar,
    obitos_sih,
    pares_sih_sim,
    passos_sih_sim,
    pct,
    pl,
    resumo,
    sim_p,
):
    detalhe_sih_sim = com_capitulo(
        com_capitulo(detalhar(pares_sih_sim, obitos_sih, sim_p), "cid", "capitulo"),
        "cid_b",
        "capitulo_b",
    )
    validacao_sih_sim = pl.DataFrame(
        [
            concordancia(detalhe_sih_sim.filter(pl.col("passo") != 3), "mun"),
            concordancia(detalhe_sih_sim, "capitulo"),
        ]
    )
    resumo_sih_sim = resumo(
        "SIH (óbitos) → SIM",
        obitos_sih,
        pares_sih_sim,
        passos_sih_sim,
        f"município igual em {pct(validacao_sih_sim, 'mun')}%",
        pct(validacao_sih_sim, "mun"),
    )
    validacao_sih_sim
    return detalhe_sih_sim, resumo_sih_sim


@app.cell
def _(detalhe_sih_sim):
    detalhe_sih_sim.group_by("lococor_b").len("pares").sort(
        ["pares", "lococor_b"], descending=[True, False]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Quando o hospital difere, que códigos cada base usa? Um mesmo par de códigos
    repetido muitas vezes sugere um estabelecimento registrado com códigos
    diferentes, não um erro de linkage.
    """)
    return


@app.cell
def _(detalhe_sih_sim, pl):
    (
        detalhe_sih_sim.filter(pl.col("estab") != pl.col("estab_b"))
        .group_by(
            pl.col("estab").alias("hospital_no_sih"), pl.col("estab_b").alias("estab_no_sim")
        )
        .len("pares")
        .sort(["pares", "hospital_no_sih", "estab_no_sim"], descending=[True, False, False])
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.2 · SIM → SINASC: óbitos infantis

    A: óbitos de quem nasceu no ano e morreu antes de completar 365 dias.
    B: nascidos vivos do mesmo ano. Os dois arquivos são por UF de residência,
    então quase todo óbito infantil deveria ter a sua declaração de nascido vivo:
    a taxa de ligação aqui estima a **sensibilidade**.

    | passo | chaves |
    | --- | --- |
    | 1 | nascimento + sexo + município + peso |
    | 2 | nascimento + sexo + município + idade da mãe |
    | 3 | nascimento + sexo + município + estabelecimento |
    """)
    return


@app.cell
def _(ANO, ligar_em_passos, nv_p, pl, sim_p):
    dias_de_vida = (pl.col("data_evento") - pl.col("nasc")).dt.total_days()
    obitos_infantis = sim_p.filter((pl.col("nasc").dt.year() == ANO) & (dias_de_vida < 365))
    PASSOS_SIM_NV = [
        ["nasc", "sexo", "mun", "peso"],
        ["nasc", "sexo", "mun", "idademae"],
        ["nasc", "sexo", "mun", "estab"],
    ]
    pares_sim_nv, passos_sim_nv = ligar_em_passos(obitos_infantis, nv_p, PASSOS_SIM_NV)
    passos_sim_nv
    return obitos_infantis, pares_sim_nv, passos_sim_nv


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Leia a coluna `% estimado por acaso`: um passo que acha quase tantos pares
    quanto o seu controle negativo é ruído. Num estudo, esse passo sai.

    **Validação.** Parto, gravidez e gestação estão nas duas declarações e não
    foram chave (gestação em faixas, pelo rótulo do dicionário, e em semanas).
    Peso só é chave no passo 1 e idade da mãe só no passo 2; cada uma confere
    os pares dos outros passos. Semanas e peso variam um pouco entre as duas
    declarações, então também aparecem com tolerância.
    """)
    return


@app.cell
def _(
    concordancia,
    detalhar,
    nv_p,
    obitos_infantis,
    pares_sim_nv,
    passos_sim_nv,
    pct,
    pl,
    resumo,
):
    detalhe_sim_nv = detalhar(pares_sim_nv, obitos_infantis, nv_p)
    fora_do_passo_1 = detalhe_sim_nv.filter(pl.col("passo") != 1)
    faixas_de_gestacao = ["Menos 22", "22 a 27", "28 a 31", "32 a 36", "37 a 41", "42 e +"]
    validacao_sim_nv = pl.DataFrame(
        [
            concordancia(detalhe_sim_nv, "parto", ["Vaginal", "Cesário"]),
            concordancia(detalhe_sim_nv, "gravidez", ["Única", "Dupla", "Tripla e+"]),
            concordancia(detalhe_sim_nv, "gestacao", faixas_de_gestacao),
            concordancia(detalhe_sim_nv, "semagestac"),
            concordancia(detalhe_sim_nv, "semagestac", tolerancia=2),
            concordancia(fora_do_passo_1, "peso"),
            concordancia(fora_do_passo_1, "peso", tolerancia=100),
            concordancia(detalhe_sim_nv.filter(pl.col("passo") != 2), "idademae"),
        ]
    )
    resumo_sim_nv = resumo(
        "SIM (óbitos infantis) → SINASC",
        obitos_infantis,
        pares_sim_nv,
        passos_sim_nv,
        f"tipo de parto igual em {pct(validacao_sim_nv, 'parto')}%",
        pct(validacao_sim_nv, "parto"),
    )
    validacao_sim_nv
    return (resumo_sim_nv,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Óbitos infantis que **não** acharam o nascido vivo: o que falta neles?
    """)
    return


@app.cell
def _(obitos_infantis, pares_sim_nv, pl):
    (
        obitos_infantis.join(pares_sim_nv, on="id", how="anti").select(
            pl.len().alias("nao_ligados"),
            pl.col("peso").is_null().sum().alias("sem_peso"),
            pl.col("idademae").is_null().sum().alias("sem_idade_da_mae"),
            pl.col("estab").is_null().sum().alias("sem_estabelecimento"),
        )
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.3 · SINASC → SIH: o parto e a internação da mãe

    No SIH do parto, a paciente é a **mãe**; o SINASC traz a data de nascimento
    dela (`dtnascmae`). A chave é: nascimento da mãe + hospital + **o dia do
    parto cair dentro da internação**.

    Para isso ser uma igualdade de chaves:

    - cada internação de mulher vira uma linha por dia internada;
    - os nascidos vivos da mesma mãe no mesmo dia e hospital (gêmeos) viram um
      **parto**.
    """)
    return


@app.cell
def _(ligar_em_passos, nv_p, pl, sih_p):
    internacoes_de_mulheres = sih_p.filter(pl.col("sexo") == "F")
    dias_internada = (
        internacoes_de_mulheres.with_columns(pl.date_ranges("inter", "data_evento").alias("dia"))
        .explode("dia", empty_as_null=False)  # saída antes da internação: sem dias
        .select("id", "nasc", "estab", pl.col("dia").alias("data_evento"))
    )
    partos = (
        nv_p.group_by(
            pl.col("nasc_mae").alias("nasc"), "estab", "data_evento", maintain_order=True
        )
        .agg(
            pl.len().alias("nascidos"),
            # Todas as declarações do parto dizem gravidez dupla ou tripla?
            pl.col("gravidez").is_in(["Dupla", "Tripla e+"]).all().alias("gemelar"),
            # Os gêmeos têm o mesmo município e local; o mínimo não depende da ordem.
            pl.col("mun").min(),
            pl.col("locnasc").min(),
        )
        .with_row_index("id")
    )
    PASSOS_NV_SIH = [["nasc", "estab", "data_evento"]]
    pares_nv_sih, passos_nv_sih = ligar_em_passos(partos, dias_internada, PASSOS_NV_SIH)
    passos_nv_sih
    return internacoes_de_mulheres, pares_nv_sih, partos, passos_nv_sih


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Cobertura.** O SIH só tem o que o SUS pagou. O denominador justo são os
    partos em hospitais que aparecem no SIH.
    """)
    return


@app.cell
def _(pares_nv_sih, partos, pl, sih_p):
    hospitais_sih = sih_p["estab"].unique().implode()
    partos_em_hospitais_sih = partos.filter(pl.col("estab").is_in(hospitais_sih))
    partos.with_columns(
        pl.col("estab").is_in(hospitais_sih).alias("hospital_no_sih"),
        pl.col("id").is_in(pares_nv_sih["id"].implode()).alias("ligado"),
    ).group_by("locnasc", "hospital_no_sih").agg(
        pl.len().alias("partos"), pl.col("ligado").sum().alias("ligados")
    ).with_columns((100 * pl.col("ligados") / pl.col("partos")).round(1).alias("% ligado")).sort(
        ["partos", "locnasc", "hospital_no_sih"], descending=[True, False, False]
    )
    return (partos_em_hospitais_sih,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Validação.** Numa internação de parto, o diagnóstico principal deve ser do
    capítulo XV da CID-10 (gravidez, parto e puerpério). Uma internação não
    deveria se ligar a dois partos diferentes. Partos com dois ou mais nascidos
    devem ter gravidez dupla ou tripla no SINASC.
    """)
    return


@app.cell
def _(
    com_capitulo,
    detalhar,
    internacoes_de_mulheres,
    pares_nv_sih,
    partos,
    partos_em_hospitais_sih,
    passos_nv_sih,
    pl,
    resumo,
):
    detalhe_nv_sih = com_capitulo(
        detalhar(pares_nv_sih, partos, internacoes_de_mulheres), "cid_b", "capitulo_b"
    )
    validacao_nv_sih = pl.DataFrame(
        [
            {
                "verificação": "diagnóstico da internação no capítulo XV",
                "pares": detalhe_nv_sih.height,
                "%": round(100 * (detalhe_nv_sih["capitulo_b"] == 15).mean(), 1),
            },
            {
                "verificação": "município de residência igual",
                "pares": detalhe_nv_sih.drop_nulls(["mun", "mun_b"]).height,
                "%": round(100 * (detalhe_nv_sih["mun"] == detalhe_nv_sih["mun_b"]).mean(), 1),
            },
            {
                "verificação": "internação ligada a mais de um parto",
                "pares": detalhe_nv_sih.height,
                "%": round(100 * detalhe_nv_sih["id_b"].is_duplicated().mean(), 1),
            },
            {
                "verificação": "2+ nascidos, todos com gravidez dupla/tripla",
                "pares": detalhe_nv_sih.filter(pl.col("nascidos") >= 2).height,
                "%": round(
                    100 * detalhe_nv_sih.filter(pl.col("nascidos") >= 2)["gemelar"].mean(), 1
                ),
            },
        ]
    )
    # A: os partos em hospitais que aparecem no SIH (o denominador justo). Todo
    # par está entre eles, porque o hospital é chave.
    resumo_nv_sih = resumo(
        "SINASC (partos em hospitais do SIH) → SIH",
        partos_em_hospitais_sih,
        pares_nv_sih,
        passos_nv_sih,
        f"diagnóstico no cap. XV em {validacao_nv_sih['%'][0]}%",
        validacao_nv_sih["%"][0],
    )
    validacao_nv_sih
    return (resumo_nv_sih,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.4 · SIM → SIA: a armadilha da chave fraca

    O SIA não tem evento em comum com o SIM; sobra nascimento + sexo +
    município de residência. A é o SIM; B são as pessoas do SIA (um CNS
    criptografado com seus dados). Compare o linkage real com o controle
    negativo.
    """)
    return


@app.cell
def _(ligar_em_passos, mo, pessoas_sia, sim_p):
    pares_sim_sia = passos_sim_sia = None
    if pessoas_sia is None:
        saida_sim_sia = mo.md("BPA-I pulada nesta execução (`PULAR`).")
    else:
        pares_sim_sia, passos_sim_sia = ligar_em_passos(
            sim_p, pessoas_sia, [["nasc", "sexo", "mun"]]
        )
        saida_sim_sia = passos_sim_sia
    saida_sim_sia
    return pares_sim_sia, passos_sim_sia


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Outra checagem: ninguém é atendido depois de morrer. Um par cujo **primeiro**
    atendimento no SIA é posterior ao mês do óbito é, com certeza, um par errado
    (ou um erro de registro).
    """)
    return


@app.cell
def _(
    detalhar,
    mo,
    nao_executado,
    pares_sim_sia,
    passos_sim_sia,
    pessoas_sia,
    pl,
    resumo,
    sim_p,
):
    if pares_sim_sia is None:
        resumo_sim_sia = nao_executado("SIM → SIA BPA-I (pessoas)", "BPA-I pulada")
        saida_depois_do_obito = mo.md("BPA-I pulada nesta execução (`PULAR`).")
    else:
        _depois = (
            detalhar(pares_sim_sia, sim_p, pessoas_sia)
            .select(
                pl.len().alias("pares"),
                (100 * (pl.col("primeira_b") > pl.col("data_evento").dt.truncate("1mo")).mean())
                .round(1)
                .alias("% com todo atendimento depois do óbito"),
            )
            .fill_null(0)
        )
        _antes = round(100 - _depois["% com todo atendimento depois do óbito"].item(), 1)
        resumo_sim_sia = resumo(
            "SIM → SIA BPA-I (pessoas)",
            sim_p,
            pares_sim_sia,
            passos_sim_sia,
            f"atendimento até o mês do óbito em {_antes}%",
            _antes,
        )
        saida_depois_do_obito = _depois
    saida_depois_do_obito
    return (resumo_sim_sia,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.5 · Todas → CNES: o código do estabelecimento

    Não é linkage de pessoas, mas é o que liga qualquer registro ao seu
    estabelecimento. Que parte dos códigos preenchidos existe no CNES da UF em
    dezembro? Entre os que não existem, que parte aconteceu em outra UF?
    """)
    return


@app.cell
def _(bases, codigo_uf, mo, nv_p, pl, sia_p, sih_p, sim_p):
    def porcentagem(verdadeiros):
        """% de True numa série booleana; vazio quando não há nada a contar."""
        return round(100 * verdadeiros.mean(), 1) if len(verdadeiros) else None

    def conferir_codigos(nome, tabela, codigos_cnes):
        com_codigo = tabela.drop_nulls("estab")
        fora = com_codigo.filter(~pl.col("estab").is_in(codigos_cnes))
        return {
            "base": nome,
            "registros com código": com_codigo.height,
            "% no CNES da UF": porcentagem(com_codigo["estab"].is_in(codigos_cnes)),
            "códigos distintos fora": fora["estab"].n_unique(),
            "% dos fora com evento em outra UF": porcentagem(
                ~fora["mun_evento"].str.starts_with(codigo_uf)
            ),
        }

    if "cnes_estabelecimentos" not in bases:
        saida_cnes = mo.md("CNES pulado nesta execução (`PULAR`).")
    else:
        _codigos = bases["cnes_estabelecimentos"]["cnes"].unique().implode()
        saida_cnes = pl.DataFrame(
            [
                conferir_codigos(nome, tabela, _codigos)
                for nome, tabela in [
                    ("SIM", sim_p),
                    ("SINASC", nv_p),
                    ("SIH", sih_p),
                    ("SIA", sia_p),
                ]
                if tabela is not None
            ]
        )
    saida_cnes
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.6 · SIH: serviços profissionais (SP) → AIH reduzida (RD)

    O SP tem uma linha por ato profissional, com o número da AIH (`sp_naih`),
    mas sem nascimento nem sexo. A chave é **exata**: o número da AIH. O SP é
    agrupado por AIH, e cada AIH é conferida no RD: hospital, datas,
    diagnóstico, procedimento, e a soma dos valores dos atos contra o valor
    total da AIH. A coluna do controle mostra quanto concordam os pares com a
    AIH **vizinha** (o número seguinte), que é certamente outra internação.
    """)
    return


@app.cell
def _(bases, comparar, mo, nao_executado, pares_por_chave, pct, pl, resumo):
    if "sih_servicos_profissionais" not in bases:
        resumo_sp_rd = nao_executado(
            "SIH serviços profissionais → RD (número da AIH)", "serviços profissionais pulados"
        )
        saida_sp_rd = mo.md("Serviços profissionais pulados nesta execução (`PULAR`).")
    else:
        _aihs_sp = (
            bases["sih_servicos_profissionais"]
            .group_by(pl.col("sp_naih").alias("n_aih"))
            .agg(
                pl.len().alias("atos"),
                pl.col("sp_cnes").n_unique().alias("hospitais"),
                pl.col("sp_dtsaida").n_unique().alias("saidas"),
                pl.col("sp_cnes").min().alias("cnes"),
                pl.col("sp_dtinter").min().alias("dt_inter"),
                pl.col("sp_dtsaida").min().alias("dt_saida"),
                pl.col("sp_cidpri").min().alias("diag_princ"),
                pl.col("sp_procrea").min().alias("proc_rea"),
                pl.col("sp_valato").sum().alias("valor"),
            )
        )
        _rd = bases["sih_aih_reduzida"].select(
            "n_aih",
            "cnes",
            "dt_inter",
            "dt_saida",
            "diag_princ",
            "proc_rea",
            pl.col("val_tot").alias("valor"),
        )
        _reais, _controle = pares_por_chave(_aihs_sp, _rd, "n_aih")
        _validacao = comparar(
            _reais,
            _controle,
            [
                ("cnes", None),
                ("dt_inter", None),
                ("dt_saida", None),
                ("diag_princ", None),
                ("proc_rea", None),
                ("valor", 0.01),
            ],
        )
        _cobertura = pl.DataFrame(
            [
                {
                    "AIHs no SP": _aihs_sp.height,
                    "com mais de um hospital ou saída nas linhas": _aihs_sp.filter(
                        (pl.col("hospitais") > 1) | (pl.col("saidas") > 1)
                    ).height,
                    "achadas no RD": _reais.height,
                    "AIHs no RD": _rd.height,
                    "AIHs do RD com linhas no SP": _rd.filter(
                        pl.col("n_aih").is_in(_aihs_sp["n_aih"].implode())
                    ).height,
                }
            ]
        )
        resumo_sp_rd = resumo(
            "SIH serviços profissionais → RD (número da AIH)",
            _aihs_sp,
            _reais,
            None,
            f"data de saída igual em {pct(_validacao, 'dt_saida')}%"
            f" (controle: {pct(_validacao, 'dt_saida', '% iguais no controle')}%)",
            pct(_validacao, "dt_saida"),
        )
        saida_sp_rd = mo.vstack([_cobertura, _validacao])
    saida_sp_rd
    return (resumo_sp_rd,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.7 · SIH: AIHs rejeitadas (RJ e ER) → aprovadas (RD)

    O RJ traz as AIHs que o SUS rejeitou, com os dados do paciente; o ER, os
    códigos de erro de cada uma. Uma AIH rejeitada volta depois, aprovada, com
    o mesmo número? A busca é no RD do ano e do ano seguinte. `meses` é a
    competência do RD menos a do RJ: negativo quer dizer que a AIH já estava
    aprovada **antes** de ser rejeitada. Se o número é o mesmo, o paciente
    também deveria ser: nascimento, sexo e datas conferem isso.
    """)
    return


@app.cell
def _(
    bases,
    comparar,
    mo,
    nao_executado,
    odb,
    pares_por_chave,
    pct,
    pl,
    rd_seguinte,
    resumo,
):
    if "sih_aih_rejeitada" not in bases:
        resumo_rj_rd = nao_executado(
            "SIH RJ (rejeitadas) → RD (número da AIH)", "RJ não publicado"
        )
        saida_rj_rd = mo.md("O RJ não é publicado para esta UF e ano (seção 1).")
    else:
        _colunas = ["n_aih", "ano", "mes", "cnes", "nasc", "sexo", "dt_inter", "dt_saida"]
        _rejeitadas = bases["sih_aih_rejeitada"].select(_colunas)
        _aprovadas = pl.concat(
            [
                aih.select(_colunas)
                for aih in (bases["sih_aih_reduzida"], rd_seguinte)
                if aih is not None
            ]
        )
        _reais, _controle = pares_por_chave(_rejeitadas, _aprovadas, "n_aih")

        def _competencia(sufixo):
            return pl.col(f"ano{sufixo}").cast(pl.Int32) * 12 + pl.col(f"mes{sufixo}").cast(
                pl.Int32
            )

        _voltas = (
            _reais.group_by(
                pl.col("ano_b").alias("ano no RD"),
                (_competencia("_b") - _competencia("")).alias("meses"),
            )
            .len("AIHs")
            .sort("ano no RD", "meses")
        )
        _validacao = comparar(
            _reais,
            _controle,
            [(coluna, None) for coluna in ["cnes", "nasc", "sexo", "dt_inter", "dt_saida"]],
        )
        _partes = [
            mo.md(
                f"{_rejeitadas.height} AIHs rejeitadas; {_reais.height} têm o número"
                " no RD do ano ou do ano seguinte."
            ),
            _voltas,
            _validacao,
        ]
        if "sih_aih_rejeitada_erro" in bases:
            _erros = bases["sih_aih_rejeitada_erro"]
            _partes += [
                mo.md(
                    "O ER, erro por erro. `odb.label` põe o motivo ao lado do código"
                    " (tabela MOTERRO do TabWin do SIH)."
                ),
                pl.DataFrame(
                    [
                        {
                            "erros": _erros.height,
                            "AIHs com erro": _erros["aih"].n_unique(),
                            "dessas, no RJ": _erros.filter(
                                pl.col("aih").is_in(_rejeitadas["n_aih"].implode())
                            )["aih"].n_unique(),
                            "AIHs do RJ sem erro no ER": _rejeitadas.filter(
                                ~pl.col("n_aih").is_in(_erros["aih"].implode())
                            ).height,
                        }
                    ]
                ),
                odb.label(
                    "sih_aih_rejeitada_erro",
                    _erros.group_by("co_erro")
                    .agg(
                        pl.len().alias("erros"),
                        pl.col("aih")
                        .is_in(_reais["n_aih"].implode())
                        .sum()
                        .alias("em AIHs achadas no RD"),
                    )
                    .sort(["erros", "co_erro"], descending=[True, False])
                    .head(15),
                    columns=["co_erro"],
                ),
            ]
        resumo_rj_rd = resumo(
            "SIH RJ (rejeitadas) → RD (número da AIH)",
            _rejeitadas,
            _reais,
            None,
            f"mesmo nascimento em {pct(_validacao, 'nasc')}%"
            f" (controle: {pct(_validacao, 'nasc', '% iguais no controle')}%)",
            pct(_validacao, "nasc"),
        )
        saida_rj_rd = mo.vstack(_partes)
    saida_rj_rd
    return (resumo_rj_rd,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.8 · SIA: o CNS criptografado como identificador

    O BPA-I, a RAAS psicossocial e as APAC trazem o CNS do paciente cifrado.
    Antes de usá-lo como chave, três perguntas aos dados:

    1. **Que forma ele tem?** Comprimento e quantos símbolos distintos usa.
    2. **Um CNS é uma pessoa dentro da família?** Que parte dos CNS aparece
       com mais de um sexo, município ou nascimento.
    3. **O mesmo CNS em duas famílias é a mesma pessoa?** Para quem aparece na
       família de referência (o BPA-I, ou a RAAS se o BPA-I foi pulado) e em
       outra: sexo, município, nascimento, e idade (±1 ano; a de referência é
       a idade em 1º de julho do ano), com o controle do CNS vizinho ao lado.
    """)
    return


@app.cell
def _(APAC, bases, pl):
    COLUNAS_DA_PESSOA = {
        "sia_bpa_individualizado": {
            "sexo": "sexopac",
            "município": "munpac",
            "nascimento": "dtnasc",
        },
        "sia_psicossocial": {"sexo": "sexopac", "município": "munpac", "nascimento": "dtnasc"},
        **{base: {"sexo": "ap_sexo", "município": "ap_munpcn"} for base in APAC},
    }

    def forma_do_cns(base):
        coluna = "ap_cnspcn" if base in APAC else "cns_pac"
        dados = bases[base].filter(pl.col(coluna).cast(pl.String).str.strip_chars() != "")
        valores = dados[coluna].cast(pl.String)
        simbolos = sorted(set("".join(valores.unique().to_list())))
        por_cns = dados.group_by(coluna).agg(
            pl.col(list(COLUNAS_DA_PESSOA[base].values())).n_unique()
        )
        linha = {
            "base": base,
            "registros": bases[base].height,
            "% vazio": round(100 * (1 - dados.height / max(bases[base].height, 1)), 1),
            "CNS distintos": por_cns.height,
            "comprimentos (registros)": ", ".join(
                f"{comprimento}: {n}"
                for comprimento, n in valores.str.len_chars().value_counts(sort=True).iter_rows()
            ),
            "símbolos distintos": len(simbolos),
            "do símbolo": hex(ord(simbolos[0])) if simbolos else None,
            "ao símbolo": hex(ord(simbolos[-1])) if simbolos else None,
        }
        for nome, coluna_da_pessoa in COLUNAS_DA_PESSOA[base].items():
            linha[f"% CNS com mais de um {nome}"] = round(
                100 * (por_cns[coluna_da_pessoa] > 1).sum() / max(por_cns.height, 1), 2
            )
        return linha

    pl.from_dicts(
        [forma_do_cns(base) for base in COLUNAS_DA_PESSOA if base in bases],
        infer_schema_length=None,
    )
    return


@app.cell
def _(
    ANO,
    anos_completos,
    comparar,
    mo,
    nao_executado,
    pares_por_chave,
    pct,
    pessoas_apac,
    pessoas_ps,
    pessoas_sia,
    pl,
    resumo,
):
    _nome_ref, _ref = (
        ("BPA-I", pessoas_sia) if pessoas_sia is not None else ("RAAS psicossocial", pessoas_ps)
    )
    _nome = f"SIA: CNS em outra família → CNS do {_nome_ref}"
    if _ref is None:
        resumo_cns = nao_executado(_nome, "BPA-I e RAAS puladas")
        saida_cns = mo.md("Sem família de referência nesta execução.")
    else:

        def _uma_linha_por_cns(pessoas):
            """A combinação de nascimento, sexo e município com mais procedimentos."""
            return pessoas.sort(
                ["procedimentos", "nasc", "sexo", "mun"],
                descending=[True, False, False, False],
                nulls_last=True,
            ).unique("cns", keep="first", maintain_order=True)

        _referencia = (
            _uma_linha_por_cns(_ref)
            .with_columns(pl.date(ANO, 7, 1).alias("meio_do_ano"))
            .select(
                "cns", "nasc", "sexo", "mun", anos_completos("nasc", "meio_do_ano").alias("idade")
            )
        )
        _outras = {
            base: tabela.select("cns", "sexo", "mun", "idade")
            for base, tabela in pessoas_apac.items()
        }
        if _ref is pessoas_sia and pessoas_ps is not None:
            _outras["sia_psicossocial"] = _uma_linha_por_cns(pessoas_ps).select(
                "cns", "sexo", "mun", "nasc"
            )
        _tabelas = []
        for _base, _outra in _outras.items():
            _reais, _controle = pares_por_chave(_outra, _referencia, "cns")
            _variaveis = [("sexo", None), ("mun", None)]
            if "nasc" in _outra.columns:
                _variaveis.append(("nasc", None))
            if "idade" in _outra.columns and _outra["idade"].is_not_null().any():
                _variaveis.append(("idade", 1))
            _tabelas.append(
                comparar(_reais, _controle, _variaveis).select(
                    pl.lit(_base).alias("base"), pl.all()
                )
            )
        _todas = pl.concat([outra.select("cns", "sexo") for outra in _outras.values()])
        _reais, _controle = pares_por_chave(_todas, _referencia, "cns")
        _sexo = comparar(_reais, _controle, [("sexo", None)])
        resumo_cns = resumo(
            _nome,
            _todas,
            _reais,
            None,
            f"sexo igual em {pct(_sexo, 'sexo')}%"
            f" (controle: {pct(_sexo, 'sexo', '% iguais no controle')}%)",
            pct(_sexo, "sexo"),
        )
        saida_cns = mo.vstack(
            [mo.md(f"Referência: {_nome_ref}, {_referencia.height} CNS.")]
            + ([pl.concat(_tabelas)] if _tabelas else [])
        )
    saida_cns
    return (resumo_cns,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.9 · BPA-I e RAAS psicossocial → SIM e SIH

    O BPA-I e a RAAS trazem nascimento, sexo e município; é a chave, sem evento
    em comum. Três linkages:

    - **SIM → RAAS psicossocial**: como o SIM → BPA-I da seção 4.4. Validação:
      o primeiro atendimento não é depois do mês do óbito;
    - **BPA-I → SIH**: pessoas com atendimento ambulatorial e internações.
      Validação: a internação cai entre a primeira e a última competência de
      atendimento da pessoa, com um mês de folga;
    - **RAAS psicossocial → SIH, capítulo V** (transtornos mentais): B se
      restringe às internações da mesma área de cuidado. Mesma validação.
    """)
    return


@app.cell
def _(
    com_capitulo,
    detalhar,
    ligar_em_passos,
    mo,
    nao_executado,
    pessoas_ps,
    pessoas_sia,
    pl,
    resumo,
    sih_p,
    sim_p,
):
    _ate_o_obito = pl.col("primeira_b") <= pl.col("data_evento").dt.truncate("1mo")
    _internacao = pl.col("inter_b").dt.truncate("1mo")
    _no_periodo = (_internacao >= pl.col("primeira").dt.offset_by("-1mo")) & (
        _internacao <= pl.col("ultima").dt.offset_by("1mo")
    )
    _cap_v = com_capitulo(sih_p, "cid", "capitulo").filter(pl.col("capitulo") == 5)
    _ligacoes = [
        (
            "SIM → SIA RAAS psicossocial (pessoas)",
            sim_p,
            pessoas_ps,
            _ate_o_obito,
            "atendimento até o mês do óbito",
        ),
        (
            "SIA BPA-I (pessoas) → SIH",
            pessoas_sia,
            sih_p,
            _no_periodo,
            "internação no período de atendimento",
        ),
        (
            "SIA RAAS psicossocial (pessoas) → SIH cap. V",
            pessoas_ps,
            _cap_v,
            _no_periodo,
            "internação no período de atendimento",
        ),
    ]
    resumos_sia_sim_sih, _saidas = [], []
    for _nome, _a, _b, _condicao, _texto in _ligacoes:
        if _a is None:
            resumos_sia_sim_sih.append(nao_executado(_nome, "base pulada ou não publicada"))
            continue
        _pares, _passos = ligar_em_passos(_a, _b, [["nasc", "sexo", "mun"]])
        _detalhe = detalhar(_pares, _a, _b)
        _ok = round(100 * _detalhe.filter(_condicao).height / max(_detalhe.height, 1), 1)
        resumos_sia_sim_sih.append(resumo(_nome, _a, _pares, _passos, f"{_texto} em {_ok}%", _ok))
        _saidas += [mo.md(f"**{_nome}** · {_texto}: {_ok}% dos pares"), _passos]
    mo.vstack(_saidas)
    return (resumos_sia_sim_sih,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.10 · APAC → SIH e SIM: CEP, sexo e idade

    A APAC não traz a data de nascimento, só a idade. A chave é CEP + sexo +
    idade para o SIH (que tem CEP) e município + sexo + idade para o SIM (que
    não tem). B se restringe à mesma doença: capítulo II da CID-10
    (neoplasias) para quimio e radioterapia, capítulo XIV (aparelho
    geniturinário) para a diálise. No SIH, as internações da mesma pessoa
    (nascimento + sexo + CEP) viram uma linha, com a menor idade.

    **Uma idade não é uma data.** Numa cidade, muita gente tem a mesma idade e
    o mesmo sexo, e o CEP, fora da capital, é quase o município (seção 3.1).
    Primeiro, qual deslocamento da idade serve de controle: o mesmo linkage com
    a idade da APAC somada de 0 a 3 anos.
    """)
    return


@app.cell
def _(com_capitulo, ligar, mo, pessoas_apac, pl, sih_p):
    CAPITULO_DA_APAC = {
        "sia_apac_quimioterapia": 2,
        "sia_apac_radioterapia": 2,
        "sia_apac_tratamento_dialitico": 14,
    }

    def pessoas_internadas(capitulo):
        """Internações do capítulo; as da mesma pessoa (nascimento + sexo + CEP) viram uma linha."""
        return (
            com_capitulo(sih_p, "cid", "capitulo")
            .filter(pl.col("capitulo") == capitulo)
            .group_by("nasc", "sexo", "cep")
            .agg(
                pl.col("idade").min(),
                # Da primeira internação (empate: o menor código).
                pl.col("mun").sort_by("inter", "mun").first(),
                pl.col("estab").sort_by("inter", "estab").first(),
                pl.col("inter").min(),
                pl.len().alias("internacoes"),
            )
            .with_row_index("id")
        )

    _base = next(
        (
            base
            for base in CAPITULO_DA_APAC
            if base in pessoas_apac and pessoas_apac[base]["idade"].is_not_null().any()
        ),
        None,
    )
    if _base is None:
        saida_deslocamento = mo.md("Nenhuma APAC com idade nesta execução.")
    else:
        _internadas = pessoas_internadas(CAPITULO_DA_APAC[_base])
        saida_deslocamento = pl.DataFrame(
            [
                {
                    "linkage": f"{_base} → SIH cap. {CAPITULO_DA_APAC[_base]}",
                    "idade somada (anos)": anos,
                    "pares": ligar(
                        pessoas_apac[_base].with_columns(pl.col("idade") + anos),
                        _internadas,
                        ["cep", "sexo", "idade"],
                    ).height,
                }
                for anos in range(4)
            ]
        )
    saida_deslocamento
    return CAPITULO_DA_APAC, pessoas_internadas


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Somar 0 é o linkage real. Um par verdadeiro pode diferir em 1 ano de idade
    entre a APAC e a internação, então somar 1 ainda acha pares verdadeiros; a
    partir de 2, o número para de cair e fica no que é só acaso. Por isso o
    controle das APAC soma **2 anos**.

    Validação: no SIH, o estabelecimento e o município, que não são chave; no
    SIM, que a primeira APAC não seja posterior ao mês do óbito.
    """)
    return


@app.cell
def _(
    CAPITULO_DA_APAC,
    com_capitulo,
    concordancia,
    detalhar,
    ligar_em_passos,
    mo,
    nao_executado,
    pessoas_apac,
    pessoas_internadas,
    pl,
    resumo,
    sim_p,
):
    resumos_apac, _saidas = [], []
    for _base, _capitulo in CAPITULO_DA_APAC.items():
        _destinos = [
            (f"{_base} → SIH cap. {_capitulo}", "SIH", ["cep", "sexo", "idade"]),
            (f"{_base} → SIM cap. {_capitulo}", "SIM", ["mun", "sexo", "idade"]),
        ]
        for _nome, _destino, _chave in _destinos:
            if _base not in pessoas_apac:
                resumos_apac.append(nao_executado(_nome, "APAC não baixada"))
                continue
            _a = pessoas_apac[_base]
            if _a["idade"].is_null().all():
                resumos_apac.append(nao_executado(_nome, "sem rótulo para ap_coidade"))
                continue
            if _destino == "SIH":
                _b = pessoas_internadas(_capitulo)
            else:
                _b = com_capitulo(sim_p, "cid", "capitulo").filter(pl.col("capitulo") == _capitulo)
            _pares, _passos = ligar_em_passos(_a, _b, [_chave], deslocar="idade", delta=2)
            _detalhe = detalhar(_pares, _a, _b)
            if _destino == "SIH":
                _validacao = pl.DataFrame(
                    [concordancia(_detalhe, "estab"), concordancia(_detalhe, "mun")]
                )
                _ok, _texto = _validacao["% iguais"][0], "estabelecimento igual"
            else:
                _antes = pl.col("competencia") <= pl.col("data_evento_b").dt.truncate("1mo")
                _ok = round(100 * _detalhe.filter(_antes).height / max(_detalhe.height, 1), 1)
                _texto, _validacao = "APAC até o mês do óbito", None
            resumos_apac.append(resumo(_nome, _a, _pares, _passos, f"{_texto} em {_ok}%", _ok))
            _saidas += [mo.md(f"**{_nome}** · {_texto}: {_ok}% dos pares"), _passos]
            _saidas += [_validacao] if _validacao is not None else []
    mo.vstack(_saidas)
    return (resumos_apac,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.11 · Subconjuntos do SIM → SIM por UF

    DOFET, DOINF, DOMAT e DOEXT são arquivos nacionais. São recortes das
    declarações do arquivo por UF (DO) ou registros à parte? Sem `numerodo`
    publicado, o teste é o mais estrito possível: cada declaração do
    subconjunto (residentes da UF) casa com uma do DO em **todas** as colunas
    que os dois arquivos têm, comparadas como texto.
    """)
    return


@app.cell
def _(SUBCONJUNTOS_SIM, bases, codigo_uf, com_capitulo, mo, pl, sim_p):
    PARTICAO = {"ano", "uf", "mes", "_source_ano", "_source_release"}
    _do = bases["sim_obitos"].with_row_index("id_do")  # o mesmo id de sim_p

    def casar_com_do(base):
        """Cada declaração de residente da UF, com os DO iguais a ela em todas as colunas comuns."""
        subconjunto = bases[base].filter(
            pl.col("codmunres").cast(pl.String).str.starts_with(codigo_uf)
        )
        comuns = [c for c in subconjunto.columns if c in _do.columns and c not in PARTICAO]
        como_texto = [pl.col(c).cast(pl.String).fill_null("") for c in comuns]
        casados = (
            subconjunto.with_row_index("id_sub")
            .select("id_sub", *como_texto)
            .join(_do.select("id_do", *como_texto), on=comuns, how="left")
        )
        return casados, len(comuns)

    casamentos = {base: casar_com_do(base) for base in SUBCONJUNTOS_SIM if base in bases}
    _contagem = pl.DataFrame(
        [
            {
                "base": base,
                "declarações no Brasil": bases[base].height,
                "de residentes da UF": por_declaracao.height,
                "colunas em comum": comuns,
                "iguais a exatamente 1 DO": por_declaracao.filter(pl.col("n") == 1).height,
                "a nenhum": por_declaracao.filter(pl.col("n") == 0).height,
                "a mais de 1": por_declaracao.filter(pl.col("n") > 1).height,
            }
            for base, (casados, comuns) in casamentos.items()
            for por_declaracao in [
                casados.group_by("id_sub").agg(pl.col("id_do").drop_nulls().len().alias("n"))
            ]
        ]
    )

    _do_cap = com_capitulo(sim_p, "cid", "capitulo")
    CRITERIO = {
        "sim_obitos_infantis": (
            "menos de 365 dias de vida",
            (pl.col("data_evento") - pl.col("nasc")).dt.total_days() < 365,
        ),
        "sim_obitos_maternos": ("causa básica no capítulo XV", pl.col("capitulo") == 15),
        "sim_obitos_externos": ("causa básica no capítulo XX", pl.col("capitulo") == 20),
    }

    def ids_no_do(base):
        return casamentos[base][0]["id_do"].drop_nulls().implode()

    _criterios = pl.DataFrame(
        [
            {
                "base": base,
                "critério no DO": texto,
                "DO com o critério": _do_cap.filter(criterio).height,
                "desses, no subconjunto": _do_cap.filter(
                    criterio & pl.col("id").is_in(ids_no_do(base))
                ).height,
                "no subconjunto sem o critério": _do_cap.filter(
                    ~criterio & pl.col("id").is_in(ids_no_do(base))
                ).height,
            }
            for base, (texto, criterio) in CRITERIO.items()
            if base in casamentos
        ]
    )
    obitos_maternos = (
        sim_p.filter(pl.col("id").is_in(ids_no_do("sim_obitos_maternos")))
        if "sim_obitos_maternos" in casamentos
        else None
    )
    _partes = [_contagem, mo.md("O que o DO diz de cada subconjunto:"), _criterios]
    if "sim_obitos_maternos" in casamentos:
        _partes += [
            mo.md("Causas do capítulo XV no DO que não estão no DOMAT:"),
            _do_cap.filter(
                (pl.col("capitulo") == 15) & ~pl.col("id").is_in(ids_no_do("sim_obitos_maternos"))
            )
            .group_by("cid")
            .len("declarações")
            .sort(["declarações", "cid"], descending=[True, False]),
        ]
    if "sim_obitos_fetais" in bases:
        _partes += [
            mo.md("`tipobito` como publicado, no DO e no DOFET (residentes da UF):"),
            pl.concat(
                [
                    bases["sim_obitos"].select(pl.lit("DO").alias("arquivo"), "tipobito"),
                    bases["sim_obitos_fetais"]
                    .filter(pl.col("codmunres").cast(pl.String).str.starts_with(codigo_uf))
                    .select(pl.lit("DOFET").alias("arquivo"), "tipobito"),
                ]
            )
            .group_by("arquivo", "tipobito")
            .len("declarações")
            .sort("arquivo", "tipobito"),
        ]
    mo.vstack(_partes)
    return (obitos_maternos,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Óbito materno → internação.** A: as declarações do DO que estão no
    DOMAT. B: as internações de mulheres no SIH, de qualquer diagnóstico. Os
    passos são os do SIH → SIM (4.1), sem o sexo. Validação: o SIH diz que a
    internação terminou em óbito (`morte`, que não é chave), e o SIM diz que o
    óbito foi em hospital. A última tabela mostra o capítulo da CID-10 do
    diagnóstico da internação: restringir B às internações obstétricas
    (capítulo XV) perderia os pares fora dele.
    """)
    return


@app.cell
def _(
    com_capitulo,
    detalhar,
    ligar_em_passos,
    mo,
    nao_executado,
    obitos_maternos,
    pl,
    resumo,
    sih_p,
):
    _nome = "SIM maternos (DOMAT) → SIH (internações de mulheres)"
    if obitos_maternos is None:
        resumo_domat_sih = nao_executado(_nome, "DOMAT não publicado")
        saida_domat_sih = mo.md("O DOMAT não foi baixado (seção 1).")
    else:
        _mulheres = com_capitulo(sih_p, "cid", "capitulo").filter(pl.col("sexo") == "F")
        _pares, _passos = ligar_em_passos(
            obitos_maternos,
            _mulheres,
            [["nasc", "data_evento", "estab"], ["nasc", "data_evento"], ["nasc", "mun", "estab"]],
        )
        _detalhe = detalhar(_pares, obitos_maternos, _mulheres)
        _morte = round(
            100 * _detalhe.filter(pl.col("morte_b") == 1).height / max(_detalhe.height, 1), 1
        )
        _hospital = round(
            100
            * _detalhe.filter(pl.col("lococor") == "Hospital").height
            / max(_detalhe.height, 1),
            1,
        )
        resumo_domat_sih = resumo(
            _nome,
            obitos_maternos,
            _pares,
            _passos,
            f"internação com óbito no SIH em {_morte}%",
            _morte,
        )
        saida_domat_sih = mo.vstack(
            [
                _passos,
                pl.DataFrame(
                    [
                        {
                            "pares": _detalhe.height,
                            "% com óbito na internação (SIH)": _morte,
                            "% com óbito em hospital (SIM)": _hospital,
                        }
                    ]
                ),
                _detalhe.group_by(pl.col("capitulo_b").alias("capítulo do diagnóstico no SIH"))
                .len("pares")
                .sort(["pares", "capítulo do diagnóstico no SIH"], descending=[True, False]),
            ]
        )
    saida_domat_sih
    return (resumo_domat_sih,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.12 · SINAN → SIM

    O SINAN traz só o **ano** de nascimento, o sexo e o município de
    residência (e, na doença de Chagas, a data do óbito). Dois linkages por
    doença, com o ano de nascimento deslocado em 1 ano no controle:

    - **todos os casos** de residentes contra todos os óbitos: a linha de
      base, sem evento em comum. Validação: o caso do par foi encerrado como
      óbito;
    - **só os casos encerrados como óbito** (rótulo do dicionário), com a
      data do óbito como chave quando ela existe. Validação: entre os pares
      cujo encerramento não diz "outras causas", a causa básica no SIM é a
      doença do SINAN (as categorias da CID-10 abaixo, com a descrição da
      `aux_cid10`).
    """)
    return


@app.cell
def _(cid10, pl):
    CAUSAS_DO_AGRAVO = {
        "sinan_tuberculose": ["A15", "A16", "A17", "A18", "A19"],
        "sinan_hanseniase": ["A30", "B92"],
        "sinan_chagas": ["B57"],
    }
    cid10.filter(
        pl.col("codigo").is_in([c for causas in CAUSAS_DO_AGRAVO.values() for c in causas])
    ).select("codigo", "descricao").sort("codigo")
    return (CAUSAS_DO_AGRAVO,)


@app.cell
def _(
    CAUSAS_DO_AGRAVO,
    casos_sinan,
    detalhar,
    ligar_em_passos,
    mo,
    nao_executado,
    pl,
    resumo,
    sim_p,
):
    resumos_sinan, _saidas = [], []
    for _base, _casos in casos_sinan.items():
        _pares, _passos = ligar_em_passos(
            _casos, sim_p, [["ano_nasc", "sexo", "mun"]], deslocar="ano_nasc", delta=1
        )
        _detalhe = detalhar(_pares, _casos, sim_p)
        _obito = round(100 * _detalhe["obito"].sum() / max(_detalhe.height, 1), 1)
        resumos_sinan.append(
            resumo(
                f"{_base} (todos os casos) → SIM",
                _casos,
                _pares,
                _passos,
                f"caso encerrado como óbito em {_obito}%",
                _obito,
            )
        )
        _saidas += [
            mo.md(f"**{_base}**, todos os casos · encerrado como óbito: {_obito}%"),
            _passos,
        ]

        _nome = f"{_base} (encerrados como óbito) → SIM"
        _obitos = _casos.filter(pl.col("obito"))
        if _obitos.height == 0:
            resumos_sinan.append(nao_executado(_nome, "nenhum caso encerrado como óbito"))
            continue
        _chaves = [["ano_nasc", "sexo", "mun"]]
        if _obitos["data_evento"].is_not_null().any():
            _chaves = [["ano_nasc", "sexo", "mun", "data_evento"], *_chaves]
        _pares, _passos = ligar_em_passos(_obitos, sim_p, _chaves, deslocar="ano_nasc", delta=1)
        _pela_doenca = detalhar(_pares, _obitos, sim_p).filter(
            ~pl.col("encerramento").str.to_lowercase().str.contains("outras")
        )
        _causa = round(
            100
            * _pela_doenca.filter(
                pl.col("cid_b").str.slice(0, 3).is_in(CAUSAS_DO_AGRAVO[_base])
            ).height
            / max(_pela_doenca.height, 1),
            1,
        )
        resumos_sinan.append(
            resumo(
                _nome,
                _obitos,
                _pares,
                _passos,
                f"causa básica da doença em {_causa}% ({_pela_doenca.height} pares)",
                _causa if _pela_doenca.height else None,
            )
        )
        _saidas += [
            mo.md(
                f"**{_base}**, encerrados como óbito · causa básica da doença em {_causa}%"
                f" de {_pela_doenca.height} pares"
            ),
            _passos,
        ]
    mo.vstack(_saidas)
    return (resumos_sinan,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4.13 · APAC de cirurgia bariátrica → AIH da cirurgia

    A APAC de cirurgia bariátrica (ABO) traz o número da AIH da cirurgia
    (`ab_numaih`): uma chave exata para o SIH. Validação: sexo, idade (±1 ano),
    hospital, e a data da cirurgia dentro da internação, com o controle da AIH
    vizinha. A busca é no RD do ano e do ano seguinte; cirurgias de anos
    anteriores ficam de fora e aparecem na tabela por ano.
    """)
    return


@app.cell
def _(
    anos_completos,
    bases,
    comparar,
    data,
    mo,
    nao_executado,
    numero,
    pares_por_chave,
    pct,
    pl,
    rd_seguinte,
    resumo,
    rotulo,
    sexo,
    texto,
):
    _base = "sia_apac_cirurgia_bariatrica"
    _nome = "SIA APAC bariátrica → SIH RD (número da AIH)"
    if _base not in bases:
        resumo_abo_rd = nao_executado(_nome, "ABO não publicada")
        saida_abo_rd = mo.md(
            "A APAC de cirurgia bariátrica não é publicada para esta UF e ano (seção 1)."
        )
    else:
        _cirurgias = (
            bases[_base]
            .select(
                texto("ab_numaih").alias("n_aih"),
                sexo(_base, "ap_sexo"),
                pl.when(rotulo(_base, "ap_coidade") == "Anos")
                .then(numero("ap_nuidade"))
                .alias("idade"),
                texto("ap_coduni").alias("cnes"),
                data("ab_dtcirur", "%Y%m%d").alias("cirurgia"),
            )
            .drop_nulls("n_aih")
            .group_by("n_aih")
            .agg(
                pl.col("sexo", "cnes").drop_nulls().mode().sort().first(),
                pl.col("idade").min(),
                pl.col("cirurgia").min(),
                pl.len().alias("apacs"),
            )
        )
        _aihs = (
            pl.concat(
                [
                    aih.select("n_aih", "sexo", "cnes", "nasc", "dt_inter", "dt_saida")
                    for aih in (bases["sih_aih_reduzida"], rd_seguinte)
                    if aih is not None
                ]
            )
            .select(
                "n_aih",
                sexo("sih_aih_reduzida", "sexo"),
                texto("cnes").alias("cnes"),
                data("nasc", "%Y%m%d").alias("nasc"),
                data("dt_inter", "%Y%m%d").alias("inter"),
                data("dt_saida", "%Y%m%d").alias("saida"),
            )
            .with_columns(anos_completos("nasc", "inter").alias("idade"))
        )
        _reais, _controle = pares_por_chave(_cirurgias, _aihs, "n_aih")
        _na_internacao = pl.col("cirurgia").is_between(pl.col("inter_b"), pl.col("saida_b"))

        def _pct_na_internacao(pares):
            comparaveis = pares.filter(_na_internacao.is_not_null())
            return round(
                100 * comparaveis.filter(_na_internacao).height / max(comparaveis.height, 1), 1
            )

        _validacao = pl.concat(
            [
                comparar(_reais, _controle, [("sexo", None), ("cnes", None), ("idade", 1)]),
                pl.DataFrame(
                    [
                        {
                            "variável": "data da cirurgia dentro da internação",
                            "pares comparáveis": _reais.filter(
                                _na_internacao.is_not_null()
                            ).height,
                            "% iguais": _pct_na_internacao(_reais),
                            "% iguais no controle": _pct_na_internacao(_controle),
                        }
                    ]
                ),
            ],
            how="vertical_relaxed",
        )
        _por_ano = (
            _cirurgias.with_columns(
                pl.col("n_aih").is_in(_reais["n_aih"].implode()).alias("achada")
            )
            .group_by(pl.col("cirurgia").dt.year().alias("ano da cirurgia"))
            .agg(pl.len().alias("AIHs na APAC"), pl.col("achada").sum().alias("achadas no RD"))
            .sort("ano da cirurgia")
        )
        _dentro = pct(_validacao, "data da cirurgia dentro da internação")
        resumo_abo_rd = resumo(
            _nome,
            _cirurgias,
            _reais,
            None,
            f"cirurgia dentro da internação em {_dentro}%"
            f" (controle: {pct(_validacao, 'data da cirurgia dentro da internação', '% iguais no controle')}%)",
            _dentro,
        )
        saida_abo_rd = mo.vstack([_por_ano, _validacao])
    saida_abo_rd
    return (resumo_abo_rd,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5 · Qualidade do linkage, lado a lado

    - `% de A ligado`: sensibilidade aproximada, quando se espera que todo A
      esteja em B (óbitos infantis, óbitos no hospital);
    - `passos descartados` e `pares descartados`: os passos com mais de 20%
      estimado por acaso, ou cujo controle acha tantos pares quanto eles, saem
      dos pares e da conta do acaso (a tabela de cada passo, na seção 4,
      mostra os números deles);
    - `% estimado por acaso`: pares do controle negativo ÷ pares reais, nos
      passos mantidos, uma estimativa da taxa de falsos positivos. Vazio numa
      chave exata: ali a validação traz a concordância do controle ao lado;
    - `validação`: a checagem mais forte de cada linkage, com variável que não
      foi chave, calculada sobre todos os pares da cascata;
    - `veredito`: a regra da seção 4. Quando a execução não pôde fazer o
      linkage (base não publicada ou pulada), o veredito diz por quê.
    """)
    return


@app.cell
def _(
    pl,
    resumo_abo_rd,
    resumo_cns,
    resumo_domat_sih,
    resumo_nv_sih,
    resumo_rj_rd,
    resumo_sih_sim,
    resumo_sim_nv,
    resumo_sim_sia,
    resumo_sp_rd,
    resumos_apac,
    resumos_sia_sim_sih,
    resumos_sinan,
):
    pl.from_dicts(
        [
            resumo_sih_sim,
            resumo_sim_nv,
            resumo_nv_sih,
            resumo_sim_sia,
            resumo_sp_rd,
            resumo_rj_rd,
            resumo_cns,
            *resumos_sia_sim_sih,
            *resumos_apac,
            resumo_domat_sih,
            *resumos_sinan,
            resumo_abo_rd,
        ],
        infer_schema_length=None,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 6 · O que aprendemos (RR, 2022)

    Os números abaixo são da execução com `UF = "RR"` e `ANO = 2022`; com outro
    recorte as tabelas mudam e este texto não. Os relatórios completos, com a
    execução de SP 2022 ao lado, estão em
    [`evidence/2026-09-23-colunas-e-linkage.md`](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-23-colunas-e-linkage.md)
    (as cinco bases) e
    [`evidence/2026-09-23-linkage-ampliado.md`](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-23-linkage-ampliado.md)
    (as demais).

    **Colunas**

    - O sexo tem quatro codificações (SIM e SINASC `1/2`, SIH `1/3`, SIA
      `M/F`), e o dicionário do SINASC rotula `M`/`F` em vez de por extenso.
      Pelo rótulo do decoder, as quatro viram a mesma variável.
    - Ainda há códigos publicados fora do `x-decode`: `homonimo = 2` no SIH,
      `tpidadepac` `0/5/9` no BPA-I, `tp_droga` `AC`, `ACO`, `AO` (mais de uma
      substância) na RAAS psicossocial, `ap_coidade = 5` nas APAC.
    - `cid_morte` e `cid_asso` do SIH são `0000` em todas as AIHs: a causa do
      óbito só existe no SIM.
    - A faixa de datas acusa o que a validação de formato não pega: nascimento
      em 1192 no BPA-I, `1899-12-30` no SIH, autorização de APAC em 2222 e
      3033, solicitação em 0222.
    - A RAAS psicossocial publica a coluna `tippre` com espaços no nome
      (`tippre  `): o dicionário não a encontra.
    - Junho de 2022 é incompleto em RR: 668 AIHs no RD contra 3.340 a 4.863
      nos outros meses, e o mesmo no SP (serviços profissionais) e no BPA-I.

    **Variáveis de linkage**

    - O CEP está no SIH e nas APAC. Fora de Boa Vista, cada município tem de
      2 a 6 CEPs, e o mais comum concentra até 98% das internações: não
      distingue pessoas.
    - Nascimento + sexo + município é única para 21% dos nascidos vivos e 46%
      das pessoas do BPA-I. Ano de nascimento + sexo + município, a única
      chave do SINAN, é única para 19% dos óbitos e 28% dos casos de
      tuberculose.
    - O que torna uma chave boa é um **evento em comum**: data do óbito = data
      de saída, dia do parto dentro da internação, peso ao nascer. Ou um
      **identificador publicado**: o número da AIH, o CNS criptografado.

    **Linkage das cinco bases**

    - **SIH → SIM**: 88% dos óbitos hospitalares ligados, 1 par por acaso.
      O veredito é "com cautela" só porque o município de residência, a
      validação escolhida, concorda em 86% dos pares; 99,9% dos pares têm
      óbito "Hospital" no SIM.
    - **SIM → SINASC**: pela regra da seção 4, só o passo com peso fica (117
      pares, nenhum por acaso); o passo com idade da mãe (22% por acaso) e o
      com estabelecimento saem.
    - **SINASC → SIH**: 83% dos partos em hospitais do SIH, 2% por acaso.
    - **SIM → SIA**: 58% por acaso. Sem evento em comum, não ligue.

    **Linkage das bases novas**

    - **Serviços profissionais → AIH reduzida**: as 46.613 AIHs do SP estão
      no RD, e hospital, datas, diagnóstico, procedimento e valor total
      concordam em 100%. No controle (a AIH vizinha), as datas concordam em 7%
      a 14%, mas o hospital em 99,9%: o número da AIH é distribuído por
      hospital, então o hospital não valida nada.
    - **AIH rejeitada → aprovada**: das 271 rejeitadas, nenhuma volta aprovada
      depois com o mesmo número. As 8 que estão no RD foram aprovadas 1 ou 2
      meses **antes** da rejeição, todas com o erro `040006`, e 4 delas têm
      outro nascimento: o número foi reapresentado, não o paciente.
    - **CNS criptografado**: 15 símbolos de um alfabeto de 10 bytes
      (`0x7b` a `0x84`), o mesmo em todas as famílias do SIA. O mesmo CNS em
      duas famílias tem o mesmo sexo em 96,3% a 98,8% das pessoas (51% no
      controle) e a mesma idade ±1 ano em 93,5% a 98,3% (5% no controle). Dentro
      do SIA, ele identifica a pessoa.
    - **BPA-I e RAAS → SIM e SIH**: 56% a 57% por acaso. A RAAS → internações
      psiquiátricas (capítulo V) tem 13% por acaso, mas só 23 pares e
      validação fraca.
    - **APAC → SIH e SIM pela idade**: somar 1 ano à idade ainda acha pares
      verdadeiros (51 contra 84); a partir de 2 anos o controle para de cair
      (26 e 33). Com esse controle, quimioterapia → SIH tem 31% por acaso,
      diálise → SIH 31%, e APAC → SIM é ruído. **Idade + sexo + CEP não liga
      pessoas em RR.**
    - **Subconjuntos do SIM**: DOINF (246), DOMAT (19) e DOEXT (611) são
      cópias exatas de declarações do DO, iguais em todas as 87 colunas
      comuns; o DOFET (122) é outro registro (`tipobito = 1`, que o DO não
      tem). O DOMAT deixa de fora as causas `O96` (2 declarações).
    - **Óbito materno → internação**: 9 dos 19 ligados, nenhum por acaso, e
      só 1 com diagnóstico da internação no capítulo XV: os óbitos maternos
      indiretos entram no SIH pela doença de base.
    - **SINAN → SIM**: com ano de nascimento + sexo + município, a
      tuberculose acha 29 pares e o controle 25. RR tem poucos casos (494 de
      tuberculose, 65 de hanseníase, 7 de Chagas); o relatório mostra SP.
    """)
    return


if __name__ == "__main__":
    app.run()
