# SINASC · nascidos vivos (`sinasc_nascidos_vivos`)

## Em uma frase

Declarações de Nascido Vivo do Sistema de Informações sobre Nascidos Vivos (SINASC),
com estrutura documentada pela Secretaria de Vigilância em Saúde do Ministério da
Saúde e arquivos publicados pelo DATASUS, um por UF e ano.

## O que um registro representa

- O dicionário da biblioteca descreve a base como declarações de nascidos vivos
  (`src/omnisus/data/dicionarios/sinasc_nascidos_vivos.yaml`, campo `title`).
- O primeiro campo dos arquivos é o número da DN (`numerodn`), sequencial por UF
  informante e por ano (Estrutura do SINASC para CD, p. 1).
- Os arquivos são DBF compactados no formato DBC (Estrutura do SINASC para CD, p. 1).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta
  `ano`, `uf` e `_source_release` a cada linha
  (`src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`).

## Datas e geografia

- `dtnasc` é a data do nascimento, no formato ddmmaaaa (Estrutura do SINASC para CD, p. 2).
- `dtrecebim` é a data de recebimento no nível central e a data da última atualização
  do registro, não a data do nascimento (Estrutura do SINASC para CD, p. 2).
- `DTCADASTR0` (assim grafado no documento) é a data de cadastramento no sistema
  (Estrutura do SINASC para CD, p. 2).
- As colunas `ano` e `uf` vêm do nome do arquivo (`DNMG2022.dbc` → MG, 2022), não de
  `dtnasc` (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- `codmunres` é o município de residência da mãe, com 7 caracteres
  (Estrutura do SINASC para CD, p. 1).
- `codmunnasc` é o município de ocorrência do nascimento, com 7 caracteres
  (Estrutura do SINASC para CD, p. 1).
- Na estrutura até 2005, o documento diz que o município de ocorrência usa a mesma
  codificação do município de residência, conforme a tabela TABMUN
  (Estrutura do SINASC para CD, p. 3).
- `ufinform` é o código da UF que informou o registro, um campo diferente da coluna
  `uf` que vem do nome do arquivo (Estrutura do SINASC para CD, p. 2;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- A importação não ajusta o comprimento dos códigos de município: `x-normalization-hint: lpad_6` é
  uma anotação descritiva e não é executada pela importação.

## Cobertura e modalidade

Arquivos anuais por UF, de 1996 em diante, no diretório final
`/dissemin/publicos/SINASC/1996_/Dados/DNRES` e no preliminar
`/dissemin/publicos/SINASC/PRELIM/DNRES`; veja o
[catálogo de datasets](../datasets.md).

Um ano pode estar em só um dos dois diretórios. Para saber qual:

```python
import omnisus as odb

publicados = odb.available_releases("sinasc_nascidos_vivos", ufs=["RR"], refresh=True)
```

### 1994 e 1995

`sinasc_1994_1995` lê `SINASC/1994_1995/Dados/DNRES`, com arquivos `DNR` + UF + ano
(`DNRRR1995.dbc`), 1994 e 1995. `DNBR1994.dbc` e `DNBR1995.dbc`, no mesmo diretório, são
o Brasil. A documentação dessa era no servidor é `Doc/NASC98.HLP`. Os dicionários dessas linhas são o inventário físico do descritor DBF de uma fixture real (`scripts/gen_dicionario.py`): nomes e tipos, sem rótulos de categoria.

## Armadilhas

- `consultas` é uma faixa, não o número de consultas de pré-natal: 1 = nenhuma,
  2 = de 1 a 3, 3 = de 4 a 6, 4 = 7 e mais, 9 = ignorado
  (Estrutura do SINASC para CD, p. 1–2).
- `peso` é o peso ao nascer em gramas, com 4 caracteres
  (Estrutura do SINASC para CD, p. 2).
- O documento não define faixas de peso; o corte de 2 500 g do notebook é uma escolha
  da análise (Estrutura do SINASC para CD, p. 1–2;
  `notebooks/sinasc_nascidos_vivos.py`, consulta `peso_ao_nascer`).
- `parto` usa 1 = vaginal, 2 = cesáreo e 9 = ignorado
  (Estrutura do SINASC para CD, p. 1).
- `sexo` usa 0 = ignorado, 1 = masculino e 2 = feminino
  (Estrutura do SINASC para CD, p. 2).
- `numerodn` é sequencial por UF informante e por ano (Estrutura do SINASC para CD,
  p. 1), e o dicionário não declara chave primária para a base
  (`src/omnisus/data/dicionarios/sinasc_nascidos_vivos.yaml`, sem `primaryKey`).
- O documento traz duas estruturas: a primeira, "Estrutura do SINASC para o CD-ROM",
  sem período no título (p. 1), e a segunda, "Estrutura do SINASC para o CD-ROM até
  2005" (p. 3). Alguns campos mudam de tamanho: `codestab` tem 7 caracteres na primeira
  e 9 na segunda, e `codanomal` tem 20 na primeira e 4 na segunda
  (Estrutura do SINASC para CD, p. 1–4).
- Em `estcivmae`, o código 5 (união consensual) aparece só na estrutura até 2005,
  marcado como de versões anteriores (Estrutura do SINASC para CD, p. 1 e p. 3).
- O documento lista 30 campos (Estrutura do SINASC para CD, p. 1–2); o dicionário da
  biblioteca inclui campos que ele não descreve, como `consprenat` e `semagestac`,
  cujos rótulos não têm apoio neste documento
  (`src/omnisus/data/dicionarios/sinasc_nascidos_vivos.yaml`). Os rótulos de
  `kotelchuck` e `tprobson` vêm do pacote oficial
  `Arq_Para_Tabulacao_A_Partir_1996.zip`, em `KOTELCHUCK.CNV` e `ROBSON.CNV`
  (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`).
- Os códigos ficam no lake como publicados: o dicionário decodifica rótulos e datas na
  exibição, não na importação (`src/omnisus/transforms/dictionaries.py`,
  docstring do módulo; `src/omnisus/sources/datasus_ftp/staging.py`, que não
  decodifica).

### Em aberto

- Se um arquivo `DNUFAAAA` reúne nascimentos de mães residentes na UF ou nascimentos
  ocorridos na UF: o documento não explica o diretório `DNRES`. Compare o prefixo de
  `codmunres` com a UF do arquivo antes de supor.
- Se `dtnasc` cai sempre no ano do arquivo: o documento não diz.
- O comprimento do código de município nos dados: o documento declara 7 caracteres
  (p. 1), e o dicionário liga `codmunres` a `aux_municipios.codigo_6` com a indicação `lpad_6`.
  Confira nos seus dados antes de juntar com outra base.
- Se `numerodn` identifica um registro sozinho: o documento o descreve como sequencial
  por UF informante e por ano (p. 1), e o dicionário não declara chave primária. Compare
  `count(*)` com `count(DISTINCT numerodn)` antes de usá-lo como chave.
- Onde passa a fronteira entre as duas estruturas: o título da segunda diz "até 2005"
  (p. 3), mas o documento não diz se 2005 já usa a primeira, se uma única estrutura vale
  para todos os anos até 2005 (o código 5 de `estcivmae` é marcado "versões
  anteriores", p. 3) nem se a primeira descreve os arquivos recentes; o documento não
  traz data de edição.

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = odb.available("sinasc_nascidos_vivos", years=[2022], ufs=["RR"], refresh=True)
relatorio = odb.import_dataset(
    "sinasc_nascidos_vivos", scopes=escopos, target=alvo, policy="skip_same", run_id="sinasc-rr-2022"
)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT ano, count(*) AS nascidos_vivos FROM lake.sinasc_nascidos_vivos GROUP BY ano").pl())
```

Passo a passo com análise e procedência:
[notebooks/sinasc_nascidos_vivos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py).

## Fontes

- Estrutura do SINASC para o CD-ROM (`Estrutura_SINASC_para_CD.pdf`), Secretaria de
  Vigilância em Saúde / MS:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/NOV/DOCS/Estrutura_SINASC_para_CD.pdf>
  — consultado em 2026-09-10; SHA-256
  `24e0d4388ea1d5fbe58a328136f1cb464e461985d3ed737210e0ecda5000cb08`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).

## Detalhes técnicos

### Linha de comando

```bash
omnisus inventory sinasc_nascidos_vivos --refresh
omnisus import sinasc_nascidos_vivos --plan inventory --years 2020-2024 --ufs RR
```

As importações acrescentam linhas a `lake.sinasc_nascidos_vivos`. Ao terminar, a
importação devolve um `ImportReport`; o estado de uma transação interrompida aparece em
`ImportAbortedError`. Veja
[resultados e transações](../guides/inventory.md#transactions-and-interrupted-imports).

### Dicionário

As definições de campo, os metadados de chave estrangeira e as regras de decodificação
ficam em `src/omnisus/data/dicionarios/sinasc_nascidos_vivos.yaml`. O parser aplica
o dicionário e preserva os campos não listados; por isso as colunas físicas da tabela
podem ser mais numerosas que as do dicionário. A validação do dicionário, sozinha, não
certifica todos os registros recebidos.

### Dados preliminares

O DATASUS também publica `sinasc_nascidos_vivos` em
`/dissemin/publicos/SINASC/PRELIM/DNRES`, ao lado do diretório final. Um ano pode estar
disponível apenas em um dos dois; `available_releases()` (em
[Cobertura e modalidade](#cobertura-e-modalidade)) mostra qual.

Cada linha carrega `_source_release` (`final` ou `prelim`), então um ano preliminar
convive na mesma tabela com anos finais sem se confundir com eles. Quando o DATASUS
republica um ano preliminar como final:

```python
with odb.LakeReader() as leitor:
    movidos = odb.outdated("sinasc_nascidos_vivos", lake=leitor)
odb.import_dataset("sinasc_nascidos_vivos", scopes=movidos,
                   policy="replace", run_id="sinasc-final-2026")
```

### Idade materna na projeção analítica

A regra 1.0.0 interpreta `idademae` em anos completos da mãe no momento do parto,
conforme o manual oficial de 2011, p. 16, campo 19. Exige a identidade auditada do
arquivo final DNRR2023.dbc; não se aplica automaticamente a outros arquivos.
`idade_anos_completos` é idade **materna**, enquanto `sexo` pertence ao bebê.
A regra não oferece sexo materno.

O domínio suportado é 1–65 anos. 00/99 têm estado `ignored` pela tabulação oficial;
66–98 permanecem `unsupported` devido a limites/divergências das tabelas consultadas.
Vazios são `missing`; valores malformados são `invalid`. Isso não é um limite
biológico. Três divergências com a idade calculada por datas foram preservadas.

Veja [evidências, hashes e reprodução](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-extensao-regras/README.md).
Os arquivos finais estão em `1996_/Dados/DNRES`, o diretório que o registro lê desde
2026-09-21; `NOV/DNRES` parou em 2022.
