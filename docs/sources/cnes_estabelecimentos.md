# CNES · estabelecimentos (`cnes_estabelecimentos`)

## Em uma frase

Arquivo de estabelecimentos (ST) do Cadastro Nacional de Estabelecimentos de Saúde
(CNES), que o DATASUS publica por UF e mês de competência.

## O que um registro representa

- Os arquivos do CNES trazem os dados cadastrais dos estabelecimentos de saúde
  cadastrados no Sistema de Cadastro Nacional de Estabelecimentos do SUS
  (Informe CNES 2017-06, p. 1).
- O ST é o arquivo de estabelecimentos; o mesmo documento descreve outros arquivos,
  como dados complementares (DC), profissionais (PF), leitos (LT) e equipamentos (EQ)
  (Informe CNES 2017-06, p. 1–2).
- `cnes` é o número nacional do estabelecimento de saúde, com 7 caracteres
  (Informe CNES 2017-06, p. 3).
- `competen` é o ano e o mês de competência da informação, no formato AAAAMM
  (Informe CNES 2017-06, p. 11).
- O layout ST numera os campos de 1 a 203 (Informe CNES 2017-06, p. 3–11) e não traz
  o nome do estabelecimento (p. 3–11).
- O dicionário da biblioteca descreve a base como "CNES — Estabelecimentos (ST)", não
  declara chave primária e declara 12 colunas
  (`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`, `title` e
  `schema.fields`, sem `primaryKey`).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta `ano`,
  `uf`, `mes` e `_source_release` a cada linha, então a tabela guarda também as
  colunas que o dicionário não declara
  (`src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`;
  `src/omnisus/sources/datasus_ftp/_runner.py`, `ingest_raw`).
- `cpf_cnpj` traz o CPF do estabelecimento, se pessoa física, ou o CNPJ, se pessoa
  jurídica; `pf_pj` indica 1 = física e 3 = jurídica; `cnpj_man` é o CNPJ da
  mantenedora (Informe CNES 2017-06, p. 3).
- `vinc_sus` indica o vínculo com o SUS: 1 = sim, 0 = não
  (Informe CNES 2017-06, p. 3).

## Datas e geografia

- O arquivo se chama `STufaamm`: `uf` é a Unidade da Federação, `aa` o ano e `mm` o
  mês da competência (Informe CNES 2017-06, p. 2).
- `competen` é o ano e o mês de competência da informação, e o documento grafa
  `DT_ATUA` o ano e o mês de competência da atualização da informação pelo
  estabelecimento, ambos no formato AAAAMM (Informe CNES 2017-06, p. 11).
- As colunas `ano`, `uf` e `mes` vêm do nome do arquivo (`STRR2401.dbc` → RR, 2024,
  mês 1) (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- `codufmun` é o código do município do estabelecimento, "UF + MUNIC (sem dígito)",
  declarado com 7 caracteres (Informe CNES 2017-06, p. 3).
- `regsaude` é o código da região de saúde NOAS, e `micr_reg` o da micro-região de
  saúde NOAS (Informe CNES 2017-06, p. 3).
- O dicionário marca `codufmun` com `lpad_6` e o liga a `aux_municipios.codigo_6`
  (`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`), mas a importação não
  ajusta o comprimento dos códigos: `x-normalization-hint: lpad_6` é uma anotação descritiva;
  a importação não executa esse preenchimento.
- O código de município da população do IBGE tem 7 dígitos
  (`src/omnisus/data/dicionarios/ibge_populacao.yaml`, `codigo_ibge`), e o notebook
  da população junta municípios pelos 6 primeiros dígitos
  (`notebooks/ibge_populacao.py`, consulta `obitos_por_100_mil`).

## Cobertura e modalidade

Arquivos mensais por UF, de agosto de 2005 em diante, no diretório
`/dissemin/publicos/CNES/200508_/Dados/ST`, sem diretório preliminar; veja o
[catálogo de datasets](../datasets.md). Os demais arquivos que o mesmo documento descreve
(Informe CNES 2017-06, p. 1–2) são linhas próprias; veja abaixo.

### Os outros subtipos do CNES

Cada subtipo é uma linha mensal por UF em `CNES/200508_/Dados/<prefixo>`. Os nomes vêm dos
arquivos DEF de `TAB_CNES.zip`, cuja linha `A` nomeia o prefixo de cada um.

| Linha | Prefixo | DEF | Cobertura |
| --- | --- | --- | --- |
| `cnes_dados_complementares` | `DC` | `DadosComplementares.def` | 2005-08 em diante |
| `cnes_equipamentos` | `EQ` | `Equipamento.def` | 2005-08 em diante |
| `cnes_equipes` | `EP` | `Equipes.def` | 2007-04 em diante |
| `cnes_estabelecimentos_ensino` | `EE` | `Estabel_Ensino.def` | 2007-03 a 2019-12, mais um arquivo vazio de 2021-07 (`EEMG2107`) |
| `cnes_estabelecimentos_filantropicos` | `EF` | `Estabel_Filantropico.def` | 2007-03 em diante |
| `cnes_gestao_metas` | `GM` | `Gestao_de_Metas.def` | 2007-03 em diante |
| `cnes_habilitacoes` | `HB` | `Habilitacao.def` | 2007-03 em diante |
| `cnes_incentivos` | `IN` | `Incentivos.def` | 2007-10 em diante |
| `cnes_leitos` | `LT` | `Leitos_Especialidade.def` | 2005-10 em diante |
| `cnes_regras_contratuais` | `RC` | `Regras_Contratuais.def` | 2007-03 em diante |
| `cnes_servicos_especializados` | `SR` | `Servico_Especializado_200803_.def` | 2005-08 em diante |

Os dicionários dessas linhas partem do inventário físico do descritor DBF de uma fixture real (`scripts/gen_dicionario.py`). Os rótulos de categoria vêm do CNV do TabWin quando o DEF liga o campo e todo valor não branco da fixture é chave do mapa (`sources/cnv/vinculos.json`); calendários, cadastros e faixas não são copiados. Um nome de marcação por diretório (`EFufAAmm.dbc`) não é um arquivo de dados e é ignorado.

## Armadilhas

- Cada arquivo ST é de um mês da competência (Informe CNES 2017-06, p. 2), e o
  documento não declara chave nem diz quantas vezes um `cnes` aparece por arquivo
  (p. 3–11; veja Em aberto). Não some linhas de várias competências como se fossem
  estabelecimentos.
- A consulta `estabelecimentos_por_tipo` do notebook mostra, lado a lado, linhas e
  códigos CNES distintos por competência (`notebooks/cnes_estabelecimentos.py`).
- `tp_unid` é o "Tipo de unidade (estabelecimento)", com 2 caracteres, e o documento
  não lista os códigos (Informe CNES 2017-06, p. 3); os códigos e rótulos vêm do
  pacote oficial `TAB_CNES.zip`, `Estabelecimento.def` → `TP_ESTAB.CNV`
  (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`).
- `turno_at` é o código de turno de atendimento, sem lista de códigos no documento
  (Informe CNES 2017-06, p. 3); os códigos e rótulos vêm do pacote oficial
  `TAB_CNES.zip`, `Estabelecimento.def` → `TurnosAt.CNV`, com as chaves escritas
  como no CNV: `01` a `07` e `'  -99'` (com dois espaços à esquerda, como no CNV)
  para turno não informado
  (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`). A chave `'  -99'` tem
  5 caracteres e não ocorre em `turno_at`, que tem 2 (`TURNO_AT`, C 2 no descritor de
  `tests/fixtures/dbc/cnes_rr_2024_01_mini.dbc`).
- `nivate_a` indica se existe nível de atenção ambulatorial, de gestão municipal ou
  estadual, para o CNES, com 1 = sim e 0 = não (Informe CNES 2017-06, p. 4), embora o
  dicionário o rotule "Nível de atenção"
  (`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`).
- Há dois campos de natureza: `natureza`, código da natureza da organização com 2
  caracteres (Informe CNES 2017-06, p. 3), e `nat_jur`, natureza jurídica com 4
  caracteres (p. 11).
- O dicionário rotula `nat_jur` "Natureza jurídica (CONCLA)", e o documento não cita
  a CONCLA nesse campo (Informe CNES 2017-06, p. 11;
  `src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`).
- O documento grafa `DT_ATUA` (Informe CNES 2017-06, p. 11), e o dicionário declara
  `dt_atual` com o rótulo "Data de atualização"
  (`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`).
- `motdesab` é o código do motivo de desabilitação do estabelecimento
  (Informe CNES 2017-06, p. 11).
- As quantidades de leitos tipo 1 (cirúrgico), 2 (clínico) e 3 (complementar) estão em
  `qtleitp1` a `qtleitp3` (Informe CNES 2017-06, p. 5); o arquivo de leitos é o LT
  (p. 2), que a biblioteca não importa ([catálogo](../datasets.md)).
- O nome do estabelecimento não está no ST (Informe CNES 2017-06, p. 3–11):
  `odb.import_cnes_master` busca os nomes na API pública e os junta a `aux_cnes`
  (`src/omnisus/__init__.py`, docstring de `import_cnes_master`).
- `aux_cnes` mostra `tp_unid` e `codufmun` da competência mais recente de cada CNES,
  não os da competência que você analisa
  (`src/omnisus/lake/operations.py`, `ensure_aux_cnes_view`).
- Toda importação do CNES-ST (`odb.load`, `odb.import_dataset`, `odb.import_research`)
  atualiza `aux_cnes` ao terminar (`src/omnisus/__init__.py`, `_AFTER_IMPORT`).
- Os códigos ficam no lake como publicados: `odb.label` põe o rótulo do dicionário ao
  lado de cada código, sem mudar o lake (`src/omnisus/transforms/dictionaries.py`,
  docstring do módulo; `src/omnisus/sources/datasus_ftp/staging.py`, que não
  decodifica).
- O texto é lido como `latin-1`: cada byte vira o caractere de mesmo valor, e
  `valor.encode("latin-1")` devolve os bytes do arquivo. Com `cp1252`, o
  valor `.\x8f6018202200448734` de `alvara` derrubava a importação de ST SP de
  2022-09 a 2022-12 (`STSP2212`: SHA-256 `dba6fff6…bd285`).

### Em aberto

- Se um `cnes` aparece mais de uma vez no mesmo arquivo: o documento não declara chave
  (p. 3–11), o dicionário não declara chave primária, e `aux_cnes` recusa linhas
  conflitantes na competência mais recente
  (`src/omnisus/lake/operations.py`). Compare `count(*)` com
  `count(DISTINCT cnes)` antes de contar estabelecimentos.
- Se o ST inclui estabelecimentos desabilitados: o documento traz o código do motivo
  de desabilitação (p. 11), mas não diz quais estabelecimentos entram no arquivo.
  Olhe a distribuição de `motdesab` nos seus dados.
- Se `competen` é sempre igual ao ano e mês do nome do arquivo: o documento descreve os
  dois (p. 2 e p. 11), mas não afirma que coincidem. Compare `competen` com `ano` e
  `mes`.
- O comprimento do código de município nos dados: o documento declara 7 caracteres
  para "UF + MUNIC (sem dígito)" (p. 3), e o dicionário indica `lpad_6`. Confira nos
  seus dados antes de juntar com outra base.
- Se o layout vale para competências anteriores a 2017-06: o documento é o informe
  técnico dessa data (p. 1), e os arquivos começam em 2005-08.

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = odb.available("cnes_estabelecimentos", years=[2024], ufs=["RR"], months=[1], refresh=True)
relatorio = odb.import_dataset(
    "cnes_estabelecimentos", scopes=escopos, target=alvo, policy="skip_same", run_id="cnes-rr-2024-01"
)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT competen, count(DISTINCT cnes) AS estabelecimentos FROM lake.cnes_estabelecimentos GROUP BY ALL").pl())
```

A importação também atualiza a visão `aux_cnes`.

Passo a passo com análise e procedência:
[notebooks/cnes_estabelecimentos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py).

## Fontes

- Disseminação de Informações do Sistema de Cadastro Nacional de Estabelecimentos do
  SUS (CNES), CNES - Informe Técnico 2017-06 (`IT_CNES_1706.pdf`), Ministério da Saúde /
  Secretaria Executiva / DATASUS:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/doc/IT_CNES_1706.pdf>
  — consultado em 2026-09-10; SHA-256
  `71af7438a8cd77ed3fd7af03f7594b94aecf7eaa71082e28fa85c23c5524a1bb`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).

## Detalhes técnicos

### Importação e `aux_cnes`

O CNES-ST usa o pipeline do FTP do DATASUS; o [catálogo](../datasets.md) define
cadência, cobertura e partições. Qualquer importação devolve um `ImportReport` e
atualiza `aux_cnes` depois da carga:

```python
import omnisus as odb

escopos = odb.scopes_for("cnes_estabelecimentos", years=[2023], ufs=["RR"], months=[1])
relatorio = odb.import_dataset("cnes_estabelecimentos", scopes=escopos)
print(relatorio.rows, relatorio.failed)
```

A importação do CNES-ST acrescenta linhas por padrão e aceita as políticas explícitas
de reimportação descritas em
[reprocessamento](../guides/reprocessing-and-maintenance.md). A substituição sempre
casa UF, ano e mês, embora a UF não seja partição física.

`aux_cnes` tem uma linha por código CNES, com `cnes`, `nome`, `tp_unid`, `codufmun` e
`yyyymm_max`, tirados das linhas do maior `ano`/`mes` de cada código. NULLs dessa linha
continuam NULL; um valor mais antigo não é levado adiante. Linhas idênticas na
competência mais recente se fundem na visão; linhas conflitantes causam erro até que o
escopo de origem seja reconciliado. A tabela subjacente guarda o histórico. O nome,
coletado à parte, é enriquecimento atual e não estabelece um nome histórico para a
competência selecionada.

A função atualiza a visão depois da carga do FTP, numa operação separada. Um empate
conflitante pode, portanto, fazer a atualização da visão falhar depois que os lotes de
origem já foram gravados; examine os dados e o manifesto de publicação antes de tentar
de novo.

<a id="establishment-names"></a>

### Nomes dos estabelecimentos

Os nomes vêm à parte, por `import_cnes_master()`, da API pública do CNES. O valor
devolvido é o número de registros úteis obtidos, não um `ImportReport`.

```python
atualizados = odb.import_cnes_master()  # códigos ausentes, descobertos em cnes_estabelecimentos
```

A atualização valida os registros antes de alterar o lake e grava juntas a criação da
tabela, a substituição das linhas e a atualização da visão. Códigos explícitos
repetidos são buscados uma vez. Falhas HTTP individuais e respostas sem nome útil são
omitidas; o inteiro devolvido não identifica quais códigos falharam, e as linhas
antigas desses códigos permanecem. `only_missing=True` filtra os códigos descobertos no
lake quando `codes=None`; códigos explícitos são pedidos mesmo que já estejam
presentes.

### Dicionário

As definições de campo e os metadados de decodificação ficam em
`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`. Veja
[o contrato de transações](../guides/inventory.md#transactions-and-interrupted-imports)
para a exigência de um único escritor e o tratamento de falhas.
