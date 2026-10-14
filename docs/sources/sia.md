# SIA · produção ambulatorial (`sia_*`)

## Em uma frase

Quinze tabelas do Sistema de Informações Ambulatoriais do SUS (SIASUS), publicadas
pelo DATASUS um arquivo por tabela, UF e mês. Este perfil detalha sete: o boletim
individualizado (BPA-I), cinco tipos de laudo de APAC e o registro de atenção
psicossocial (RAAS).

## O que um registro representa

Cada tabela vem de um instrumento ou laudo diferente:

- `sia_bpa_individualizado` (prefixo `BI`): Boletim de Produção Ambulatorial
  Individualizado (BPA-I), instituído pela Portaria SAS/MS nº 709/2007 para registrar
  informações sobre os usuários do SUS e sua situação de saúde pela CID
  (Informe SIASUS 2019-07, p. 17).
- `sia_apac_medicamentos` (prefixo `AM`): Laudo de Medicamentos da APAC
  (Informe SIASUS 2019-07, p. 5), com peso, altura, transplante e gestante do paciente
  (p. 7).
- `sia_apac_quimioterapia` (prefixo `AQ`): Laudo de Quimioterapia da APAC
  (Informe SIASUS 2019-07, p. 5), com CID de topografia, estádio, esquema e meses de
  tratamento planejados e autorizados (p. 9–10).
- `sia_apac_tratamento_dialitico` (prefixo `ATD`): Laudo de Tratamento Dialítico da APAC
  (Informe SIASUS 2019-07, p. 5), com a data de início da primeira diálise e a data de
  início da diálise na clínica (p. 15).
- `sia_apac_laudos_diversos` (prefixo `AD`): Laudos Diversos da APAC
  (Informe SIASUS 2019-07, p. 5), com o layout comum da APAC e nenhum campo próprio
  (p. 6).
- `sia_apac_cirurgia_bariatrica` (prefixo `ABO`): APAC de acompanhamento pós-cirurgia
  bariátrica. O `TAB_SIA.zip` lê os arquivos `ABO` com `APAC_Pos_Cirurgia_Bariatica.def`,
  e todas as 844 linhas de `ABOSP2401.dbc` têm `ap_pripal` 0301120056, "ACOMPANHAMENTO DE
  PACIENTE POS- CIRURGIA BARIATRICA" no SIGTAP de 2008-01; `ab_procaih` traz o
  procedimento da cirurgia na AIH (0407010173, gastroplastia com derivação intestinal, em
  837 linhas) e `ab_numaih` o número dessa AIH
  (`tests/unit/sources/datasus_ftp/test_sia_apac.py`). O nome do dataset fica por
  compatibilidade: trocá-lo mudaria a API. O Laudo de Acompanhamento à Cirurgia
  Bariátrica do informe é o arquivo `AB` (veja [Armadilhas](#armadilhas)).
- `sia_psicossocial` (prefixo `PS`): Registro das Ações Ambulatoriais de Saúde (RAAS) –
  Psicossocial (Informe SIASUS 2019-07, p. 15–16).

Sobre as linhas:

- As informações dos arquivos de APAC referem-se aos atendimentos ambulatoriais
  realizados em pacientes submetidos à APAC, nas respectivas competências (ano e mês),
  a partir de janeiro de 2008 (Informe SIASUS 2019-07, p. 5).
- `ap_autoriz` é o número da APAC, com a lei de formação UF, ano, tipo, sequencial e
  dígito (Informe SIASUS 2019-07, p. 6).
- O valor aprovado dos arquivos de APAC refere-se ao valor total da APAC
  (Informe SIASUS 2019-07, p. 5).
- Nos arquivos de APAC, o procedimento contido no arquivo refere-se ao procedimento
  principal (Informe SIASUS 2019-07, p. 5), em `ap_pripal` (p. 6).
- Na RAAS psicossocial, cada linha traz a quantidade de atendimentos (`qtdate`) e a
  quantidade de pacientes (`qtdpcn`) (Informe SIASUS 2019-07, p. 16–17).
- Nenhum dos dicionários do SIA declara chave primária
  (`src/omnisus/data/dicionarios/sia_*.yaml`, sem `primaryKey`).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta `ano`,
  `uf`, `mes` e `_source_release` a cada linha
  (`src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`;
  `src/omnisus/sources/datasus_ftp/_runner.py`, `ingest_raw`).

## Datas e geografia

- O documento diz que o `aamm` do nome do arquivo é o ano e o mês da competência
  (Informe SIASUS 2019-07, p. 5 para APAC e p. 17 para BPA-I).
- As colunas `ano`, `uf` e `mes` vêm do nome do arquivo (`AMRR2401.dbc` → RR, 2024,
  mês 1) (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- Na APAC, `ap_mvm` é a data de processamento ou movimento e `ap_cmp` a data de
  atendimento ao paciente ou competência, ambas AAAAMM (Informe SIASUS 2019-07, p. 6).
- A APAC tem validade: `ap_dtinic` e `ap_dtfim` são as datas de início e de fim da
  validade, AAAAMMDD, e `ap_dtocor` é a data de ocorrência que substitui a data de fim
  (Informe SIASUS 2019-07, p. 6).
- `ap_tpapac` indica se a APAC é 1 = inicial, 2 = continuidade ou 3 = única, e
  `ap_apacant` guarda o número da APAC anterior (Informe SIASUS 2019-07, p. 6).
- No BPA-I, `dt_process` é o ano e mês de processamento da produção e `dt_atend` o ano e
  mês do atendimento (Informe SIASUS 2019-07, p. 17).
- Na RAAS psicossocial, `dt_process` é a data de processamento e `dt_atend` a data do
  atendimento, AAAAMM, e `inicio` e `fim` são as datas de início e fim do atendimento
  (Informe SIASUS 2019-07, p. 16).
- Na APAC, `ap_munpcn` é UF + município de residência do paciente, com 6 caracteres, e
  `ap_ufmun` é UF + município do estabelecimento (Informe SIASUS 2019-07, p. 6).
- No BPA-I, `munpac` é UF + município de residência do paciente ou do estabelecimento,
  quando não há identificação do paciente, o que ocorre no BPA
  (Informe SIASUS 2019-07, p. 17).
- Na RAAS psicossocial, `munpac` é UF + município de residência do paciente, e `ufmun`
  o do estabelecimento (Informe SIASUS 2019-07, p. 16).
- `ap_ufdif` e `ap_mndif` (APAC) e `ufdif` e `mndif` (BPA-I) indicam se a UF ou o
  município de residência do paciente difere do local do estabelecimento
  (Informe SIASUS 2019-07, p. 6 e p. 18).

## Cobertura e modalidade

Arquivos mensais por UF, todos no diretório `/dissemin/publicos/SIASUS/200801_/Dados`,
sem diretório preliminar. O início difere por tabela: 2008-01 para BPA-I, medicamentos,
quimioterapia e laudos diversos; 2012-11 para a RAAS psicossocial; 2014-01 para o
acompanhamento pós-cirurgia bariátrica (`ABO`); 2014-08 para tratamento dialítico. Veja
[Bases e argumentos](../datasets.md#sia).

### Produção ambulatorial (PA)

| Linha | Prefixo | Diretório | Cobertura |
| --- | --- | --- | --- |
| `sia_producao_ambulatorial` | `PA` | `SIASUS/200801_/Dados` | 2008-01 em diante; meses grandes vêm em partes `a`–`d` (`PASP2401a.dbc`), importadas como uma publicação |
| `sia_producao_ambulatorial_1994_2007` | `PA` | `SIASUS/199407_200712/Dados` | 1994-07 a 2007-12; o diretório `Doc` dessa era está vazio no servidor |

Os dicionários dessas linhas partem do inventário físico do descritor DBF de uma fixture real (`scripts/gen_dicionario.py`). Os rótulos de categoria vêm do CNV do TabWin quando o DEF liga o campo e todo valor não branco da fixture é chave do mapa (`sources/cnv/vinculos.json`); calendários, cadastros e faixas não são copiados. `sia_producao_ambulatorial_1994_2007` fica sem rótulos: os DEF dessa era (`SIASUS/200801_/Auxiliar/TAB_SIA_199407-199910.zip` e os dois seguintes) não estão arquivados.

### Outras APAC e atenção domiciliar

Nomes do Informe Técnico SIASUS 2019-07 (p. 5 e p. 15); cobertura lida da listagem de
`SIASUS/200801_/Dados` em 2026-09-23.

| Linha | Prefixo | Cobertura |
| --- | --- | --- |
| `sia_apac_acompanhamento_bariatrica` | `AB` | 2008-01 a 2025-07, 18 UFs, meses esparsos |
| `sia_apac_fistula_arteriovenosa` | `ACF` | 2014-08 em diante |
| `sia_apac_acompanhamento_multiprofissional` | `AMP` | 2016-03 em diante, 13 UFs |
| `sia_apac_nefrologia` | `AN` | 2008-01 a 2014-10 (depois, `ATD`) |
| `sia_apac_radioterapia` | `AR` | 2008-01 em diante |
| `sia_atencao_domiciliar` | `SAD` | 2012-04 a 2018-10 |

`AB` e `ABO` são famílias diferentes: a linha 3 de `APAC_Cirurgia_Bariatica.DEF` lê
`DADOS\AB*.DBC` e a de `APAC_Pos_Cirurgia_Bariatica.def` lê `DADOS\ABO*.DBF`
(`TAB_SIA.zip`). Só o DEF pós-cirurgia liga os campos de acompanhamento `AB_PRCAIH4` a
`AB_PRCAIH6`, `AP_MEDICAM`, `AP_POLIVIT`, `AP_ATV_FIS`, `AP_REG_PES`, `AP_ADESAO` e
`AP_CID_C1` a `AP_CID_C5`, que o arquivo `ABO` de SP tem e o `AB` de SE não
(`tests/unit/sources/datasus_ftp/test_sia_apac.py`,
`test_each_bariatric_def_reads_the_family_vinculos_gives_it`). Nas duas fixtures, todas
as linhas têm `ap_pripal` 0301120056, o acompanhamento pós-cirurgia. `AMP` não tem
DEF no `TAB_SIA.zip`, por isso não tem rótulos. Todas declaram identidade de arquivo
(mês e UF), como as outras APAC.

## Armadilhas

- Os códigos de `ap_ufdif` e `ap_mndif` mudam entre layouts: 0 e 1 em laudos diversos
  (Informe SIASUS 2019-07, p. 6), N e S em quimioterapia (p. 9), acompanhamento à
  cirurgia bariátrica (`AB`, p. 12) e tratamento dialítico (p. 14), e nenhum código, com
  2 caracteres, em
  medicamentos (p. 7).
- Os cinco dicionários de APAC decodificam `ap_ufdif` e `ap_mndif` a partir de
  `Invasao.CNV`, ligado pelo DEF de cada laudo de APAC no pacote oficial
  `TAB_SIA.zip` (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`).
- O Laudo de Acompanhamento à Cirurgia Bariátrica do informe é o arquivo `AB`
  (`sia_apac_acompanhamento_bariatrica`), não o `ABO`: o documento o nomeia
  `ABufaamm.dbf` (p. 5) e `ABUFMM.DBF` (p. 11), e o layout das p. 11–12 lista 58 campos
  com `AP_TIPPRE`, `AP_APACANT`, `AP_DTOCOR` e `AP_CIDPRI`, como o cabeçalho de
  `ABSE2507.dbc` (58 campos; `src/omnisus/data/dicionarios/sia_apac_acompanhamento_bariatrica.yaml`,
  `x-evidence`).
- O cabeçalho de `ABOSP2401.dbc` tem outro layout: 86 campos, 8 sem nome, que o parser
  descarta, com `AP_TPPRE`, `AP_APACAN`, `AP_DTOOCOR` e `CO_CIDPRIM` no lugar daqueles
  quatro, e os campos de acompanhamento que só o DEF pós-cirurgia liga
  (`tests/unit/sources/datasus_ftp/test_sia_apac.py`, docstring do módulo).
- No `ABO`, `ap_mn_ind` e `ap_cid_c1` a `ap_cid_c5` ficam sem rótulos. O DEF pós-cirurgia
  liga `AP_MN_IND` a `MANT_IND.CNV` sem a pasta `CNV/` (linha 241), um caminho que não é o
  do `CNV/MANT_IND.CNV` empacotado (`vinculos.json`, `sem_cnv`); o `AB` usa esse CNV. Os
  campos de comorbidade são ligados a `CNV/CID_COM.CNV`, que não está entre os membros
  do `TAB_SIA.zip` que o pacote arquiva (`vinculos.json`, `membros`).
- Os dicionários de APAC e da RAAS psicossocial foram gerados do cabeçalho de arquivos
  DBF reais de 2024, não do informe técnico, e muitos rótulos só repetem o nome do campo
  (`src/omnisus/data/dicionarios/sia_apac_*.yaml` e `sia_psicossocial.yaml`,
  comentário inicial e `label`).
- Quantidade e valor aparecem apresentados e aprovados: `qt_apres` e `qt_aprov`,
  `vl_apres` e `vl_aprov` no BPA-I (Informe SIASUS 2019-07, p. 17–18).
- No BPA-I, o número de autorização `autoriz` não é obrigatório e não é criticado
  (Informe SIASUS 2019-07, p. 17).
- No BPA-I, `etnia` só é preenchida quando `racacor` é 05 (indígena), a partir da
  competência de outubro de 2010 (Informe SIASUS 2019-07, p. 18).
- O CNS do paciente vem cifrado (`cns_pac` na RAAS, "criptografia";
  Informe SIASUS 2019-07, p. 16), e os dicionários marcam os campos de CNS com
  `x-crypto: datasus-cns` (`src/omnisus/data/dicionarios/sia_*.yaml`).
- A biblioteca não decifra o CNS. O valor cifrado, comparado como publicado, liga a mesma
  pessoa entre tabelas do SIA (`evidence/2026-09-23-linkage-ampliado.md`, seção "SIA: the
  encrypted CNS"). Nos arquivos de teste de Roraima, janeiro de 2024, 312 CNS distintos
  aparecem no BPA-I (`cns_pac`) e na APAC de medicamentos (`ap_cnspcn`), e 56 no BPA-I e
  na RAAS psicossocial (`cns_pac`) (`tests/unit/sources/datasus_ftp/test_sia_apac.py`,
  `test_cross_family_cns_intersection_rr`).
- Os códigos ficam no lake como publicados: o dicionário decodifica rótulos e datas na
  exibição, não na importação (`src/omnisus/transforms/dictionaries.py`, docstring do
  módulo; `src/omnisus/sources/datasus_ftp/staging.py`, que não decodifica).
- O CNS cifrado do paciente vem em branco em boa parte das linhas recentes, e a falta
  muda com a família, a UF e o mês
  ([censo de 2026-10-08](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-10-08-cns-vazio-sia/README.md)).
  - Somadas as UFs fora de SP e GO, a parte em branco subiu de 2024-10 para 2026-07:
    de 6,0% para 68,4% no BPA-I, de 0,3% para 70,2% no tratamento dialítico, de 2,7%
    para 45,4% nos laudos diversos, de 0,8% para 29,9% na quimioterapia e de 0,8% para
    29,6% no acompanhamento pós-cirurgia bariátrica (`ABO`).
  - Em 2026-07, a parte em branco do BPA-I vai de 27,0% (RR e TO) a 84,0% (GO).
  - A RAAS psicossocial não tem nenhuma linha em branco nesses meses.
  - A APAC de medicamentos perdeu o CNS em GO e SP
    ([Medicamentos](medicamentos.md#armadilhas)) e quase nada nas outras UFs.

  Meça a parte em branco por UF e mês antes de ligar pessoas pelo CNS.

### Em aberto

- O que uma linha de APAC representa: o documento diz que a APAC gera um registro por
  código de procedimento realizado, principal ou secundário, e, na frase seguinte, que
  nos arquivos de APAC o procedimento se refere ao principal (p. 5). Vale para
  `sia_apac_medicamentos`, `sia_apac_quimioterapia`, `sia_apac_tratamento_dialitico`,
  `sia_apac_laudos_diversos` e `sia_apac_cirurgia_bariatrica`. Compare o número de
  linhas com o de valores distintos de `ap_autoriz` antes de contar APAC.
- Se a mesma APAC reaparece em meses seguintes: o documento prevê APAC de continuidade e
  período de validade (p. 6), mas não diz se cada mês publica a APAC de novo. Não some
  meses sem conferir `ap_autoriz` e `ap_tpapac`.
- Qual mês o arquivo representa: o documento chama o `aamm` do nome de mês da
  competência (p. 5 e p. 17), mas separa processamento (`ap_mvm`, `dt_process`) de
  atendimento ou competência (`ap_cmp`, `dt_atend`) (p. 6, p. 16 e p. 17). Compare `mes`
  com esses campos nos seus dados.
- O que uma linha de `sia_bpa_individualizado` representa: o documento diz que o BPA-I
  gera um registro por atendimento no arquivo de procedimentos ambulatoriais (PA)
  (p. 3), mas não diz o mesmo do arquivo BI.
- O que uma linha de `sia_psicossocial` representa: cada linha traz quantidades de
  atendimentos e de pacientes (p. 16–17), e o documento não diz se ela é um atendimento,
  um paciente ou um período.
- O formato de `inicio` e `fim` na RAAS psicossocial: o documento dá DDMMAAAA (p. 16),
  e o dicionário lê `yyyyMMdd` (`src/omnisus/data/dicionarios/sia_psicossocial.yaml`).
  Confira nos seus dados antes de converter.
- Que procedimentos entram em `sia_apac_laudos_diversos`: o documento lista o laudo e
  seu layout (p. 5–6), sem dizer o que ele cobre.
- Se o layout de 2019 vale para todos os anos: o documento diz que não houve mudanças
  nos arquivos de APAC (p. 6), sem data de referência.

## Como usar

```python
import omnisus as sus

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = sus.available("sia_bpa_individualizado", years=[2024], ufs=["RR"], months=[1], refresh=True)
relatorio = sus.import_dataset(
    "sia_bpa_individualizado", scopes=escopos, target=alvo, policy="skip_same", run_id="sia-bpai-rr-2024-01"
)
with sus.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT ano, mes, count(*) AS registros FROM lake.sia_bpa_individualizado GROUP BY ALL").pl())
```

Passo a passo com as sete tabelas, análise e procedência:
[notebooks/sia.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sia.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py).

## Fontes

- Disseminação de Dados em Saúde, Sistema de Informações Ambulatoriais do SUS
  (SIASUS), Informe Técnico (`Informe_Tecnico_SIASUS_2019_07.pdf`), Ministério da
  Saúde / Secretaria Executiva / DATASUS / CGGOV:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Doc/Informe_Tecnico_SIASUS_2019_07.pdf>
  — consultado em 2026-09-10; SHA-256
  `70fe69dbd4cf0827452e3c265d8d83ebeabe145f63a7e054e57c7848d070c8dc`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`. Em 2026-09-13, o
  diretório `/dissemin/publicos/SIASUS/200801_/Doc` só continha este informe.
- Censo do CNS do paciente em branco nos arquivos do SIA, lido em 2026-10-08, com o
  SHA-256 de cada arquivo:
  <https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-10-08-cns-vazio-sia/README.md>.
- [Bases e argumentos](../datasets.md#sia), página gerada do registro da biblioteca.

## Detalhes técnicos

### As tabelas de 2008 em diante

As 14 tabelas abaixo usam o mesmo diretório do FTP,
`/dissemin/publicos/SIASUS/200801_/Dados`, e se distinguem pelo prefixo do arquivo
([Bases e argumentos](../datasets.md#onde-fica-no-servidor)). A décima quinta,
`sia_producao_ambulatorial_1994_2007`, fica em `SIASUS/199407_200712/Dados` (veja
Produção ambulatorial, acima).

| Dataset | Prefixo |
| --- | --- |
| `sia_bpa_individualizado` | `BI` |
| `sia_apac_medicamentos` | `AM` |
| `sia_apac_quimioterapia` | `AQ` |
| `sia_apac_tratamento_dialitico` | `ATD` |
| `sia_apac_laudos_diversos` | `AD` |
| `sia_apac_cirurgia_bariatrica` | `ABO` |
| `sia_psicossocial` | `PS` |
| `sia_producao_ambulatorial` | `PA` |
| `sia_apac_acompanhamento_bariatrica` | `AB` |
| `sia_apac_fistula_arteriovenosa` | `ACF` |
| `sia_apac_acompanhamento_multiprofissional` | `AMP` |
| `sia_apac_nefrologia` | `AN` |
| `sia_apac_radioterapia` | `AR` |
| `sia_atencao_domiciliar` | `SAD` |

Todos os arquivos que o informe técnico cita (Informe SIASUS 2019-07, p. 1 e p. 5) têm
linha em [Bases e argumentos](../datasets.md#sia).

### Linha de comando

```bash
omnisus inventory sia_bpa_individualizado --refresh
omnisus import sia_bpa_individualizado --plan inventory --years 2020-2024 --ufs RR
```

As importações acrescentam linhas à tabela do dataset, por exemplo
`lake.sia_bpa_individualizado`. Ao terminar, a importação devolve um `ImportReport`; o
estado de uma transação interrompida aparece em `ImportAbortedError`. Veja
[resultados e transações](../guides/inventory.md#transactions-and-interrupted-imports).

### Dicionários

As definições de campo e as regras de decodificação ficam em
`src/omnisus/data/dicionarios/<dataset>.yaml`, um arquivo por tabela. Todos os `sia_*`
usam a codificação `latin-1`, porque o CNS cifrado usa bytes que o `cp1252` não define
(comentário inicial dos sete dicionários detalhados neste perfil). O parser aplica o dicionário e preserva os
campos não listados; por isso as colunas físicas da tabela podem ser mais numerosas que
as do dicionário.

Os campos de CID-10 de `sia_producao_ambulatorial` (`pa_cidpri`, `pa_cidsec`,
`pa_cidcas`), `sia_apac_quimioterapia` (`ap_cid*`, `aq_cid10`, `aq_cidini1-3`) e
`sia_apac_radioterapia` (`ap_cid*`, `ar_cid10`, `ar_cidini1-3`, `ar_cidtr1-3`) declaram
referência a `aux_cid10.codigo`, como os do SIH; `sus.reference_join_sql` dá o nome da
doença. Os DEFs do `TAB_SIA.zip` relacionam esses campos a `DBF/S_CID.DBF`. Eles são
C(4) em todo arquivo do censo em `evidence/2026-10-07-sia-cid-widths/` (PA de RR e AQ e
AR de AL, um arquivo por mês de 2008-01 a 2026-07). O `0000` quer dizer CID não
informado (ver [Vocabulários](vocabularios.md)).

`sia_producao_ambulatorial_1994_2007` também declara referência a `aux_cid10.codigo` em
`pa_cidpri` e `pa_cidsec`, os dois campos de CID que o PA tem de 1999-07 a 2007-12 (antes
disso não há campo de CID). Os DEFs dessa era não estão arquivados, então nenhum DEF diz
quais campos se relacionam ao `S_CID.DBF`; a lista vem do censo de RR em
`evidence/2026-10-07-sia-cid-widths/`. Os códigos ficam como publicados, e muitos não
encontram linha na `aux_cid10`, por isso ficam sem rótulo (ver
[Vocabulários](vocabularios.md)): o `0`, o `0000` e categorias de três caracteres
completadas com zero (`C610`). Os códigos CID-10 válidos encontram o nome da doença,
inclusive as categorias de três caracteres escritas sem zero (`G20`); as completadas com
zero (`C610`), não.

Também declaram referência a `aux_cid10.codigo` os campos de CID-10 de
`sia_apac_laudos_diversos`, `sia_apac_medicamentos`, `sia_apac_nefrologia` e
`sia_apac_tratamento_dialitico` (`ap_cidpri`, `ap_cidsec`, `ap_cidcas`),
`sia_atencao_domiciliar` (`cidpri`, `cidassoc`, `pa_cid`) e `sia_psicossocial`
(`cidpri`, `cidassoc`). O DEF de cada um no `TAB_SIA.zip` relaciona esses campos a
`S_CID.DBF`. Para eles não houve censo de larguras: são C(4) nos arquivos de exemplo
dos testes (AD de RR e SP, PS de RR e SP, AM e ATD de RR, AN do PA, SAD do MA), onde o
único valor sem linha na `aux_cid10` é o `0000`. No ATD de RR de 2024-01, `ap_cidpri`
é `0000` em todas as 358 linhas.
