# SIM · óbitos (`sim_obitos`)

## Em uma frase

Declarações de Óbito do Sistema de Informações sobre Mortalidade (SIM), com estrutura
documentada pela Coordenação-Geral de Informações e Análise Epidemiológicas da
Secretaria de Vigilância em Saúde do Ministério da Saúde e arquivos publicados pelo
DATASUS, um por UF e ano.

## O que um registro representa

- O dicionário da biblioteca descreve a base como declarações de óbito e declara
  `numerodo` (número da DO) como chave primária
  (`src/omnisus/data/dicionarios/sim_obitos.yaml`, `title` e `primaryKey`).
- `tipobito` separa óbito fetal (1) de não fetal (2) e é campo obrigatório
  (Estrutura do SIM 2025, p. 1).
- O documento define óbito fetal como a morte antes da expulsão ou extração completa
  do corpo da mãe, independentemente da duração da gravidez
  (Estrutura do SIM 2025, p. 1).
- `causabas` é a causa básica da DO, com 4 caracteres (Estrutura do SIM 2025, p. 5).
- O dicionário liga `causabas` à tabela CID-10 (`aux_cid10`, código sem ponto, como o
  arquivo grava; todos os códigos do exemplo de 2023 resolvem)
  (`src/omnisus/data/dicionarios/sim_obitos.yaml`), e o
  diretório final é `/dissemin/publicos/SIM/CID10/DORES` ([catálogo](../datasets.md)).
- As linhas A a D e a Parte II guardam os CIDs informados em cada linha da DO
  (Estrutura do SIM 2025, p. 4–5).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta
  `ano`, `uf` e `_source_release` a cada linha
  (`src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`).

## Datas e geografia

- `dtobito` é a data em que ocorreu o óbito, no formato ddmmaaaa, e é campo
  obrigatório (Estrutura do SIM 2025, p. 1).
- Em óbito fetal, a data de nascimento (`dtnasc`) e a data do óbito devem ser iguais
  (Estrutura do SIM 2025, p. 1).
- `dtatestado` é a data em que o atestado foi assinado (Estrutura do SIM 2025, p. 5).
- `dtcadastro` é a data do cadastro do óbito, e `dtrecebim` a data do recebimento
  (Estrutura do SIM 2025, p. 6).
- `difdata` é a diferença entre a data do óbito e a data do recebimento original da DO
  (Estrutura do SIM 2025, p. 7).
- As colunas `ano` e `uf` vêm do nome do arquivo (`DOSP2024.dbc` → SP, 2024), não de
  `dtobito` (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- Numa importação real de Roraima, nenhum registro de 2022 ou 2023 tinha ano de
  `dtobito` diferente do ano do arquivo
  (`evidence/2026-09-10-marimo-real/verification.json`, `quality`;
  `evidence/2026-09-10-notebook-dados-reais.md`, "Validações concluídas").
- `codmunres` é o município de residência, com 7 caracteres; em óbito fetal, vale o
  município de residência da mãe (Estrutura do SIM 2025, p. 3).
- `codmunocor` é o município onde ocorreu o óbito, com 8 caracteres
  (Estrutura do SIM 2025, p. 3).
- `lococor` diz o local de ocorrência: 1 = hospital, 2 = outros estabelecimentos de
  saúde, 3 = domicílio, 4 = via pública, 5 = outros, 6 = aldeia indígena,
  9 = ignorado (Estrutura do SIM 2025, p. 3).
- A importação não ajusta o comprimento dos códigos de município: o staging
  preserva os códigos publicados. Confira o comprimento antes de fazer junções.

## Cobertura e modalidade

Arquivos anuais por UF, de 1996 em diante, no diretório final
`/dissemin/publicos/SIM/CID10/DORES` e no preliminar
`/dissemin/publicos/SIM/PRELIM/DORES`; veja o
[catálogo de datasets](../datasets.md).

Um ano pode estar em só um dos dois diretórios. Para saber qual:

```python
import omnisus as odb

publicados = odb.available_releases("sim_obitos", ufs=["RR"], refresh=True)
```

### Subconjuntos nacionais e a era CID-9

| Linha | Prefixo | Diretório | Cobertura |
| --- | --- | --- | --- |
| `sim_obitos_fetais` | `DOFET` | `SIM/CID10/DOFET` | 1996–2025, um arquivo nacional por ano (`DOFET23.dbc`) |
| `sim_obitos_externos` | `DOEXT` | `SIM/CID10/DOFET` | idem |
| `sim_obitos_infantis` | `DOINF` | `SIM/CID10/DOFET` | idem |
| `sim_obitos_maternos` | `DOMAT` | `SIM/CID10/DOFET` | idem |
| `sim_obitos_cid9` | `DOR` | `SIM/CID9/DORES` | 1979–1995, por UF, ano com dois dígitos (`DORRR79.DBC`) |

Os subconjuntos não leem `SIM/PRELIM/DOFET`: em 2026-09-22 o ano de 2025 estava nos dois
diretórios, com o mesmo tamanho e data, e a biblioteca recusa um escopo publicado duas
vezes; os arquivos preliminares de 2026 ficam de fora até o DATASUS remover a cópia.
`DOREXT` (2013–2025, no mesmo diretório) fica de fora enquanto a documentação não disser o
que é. `DORBR79`–`DORBR95` são o Brasil, não uma UF.

`sim_obitos_infantis`, `sim_obitos_maternos` e `sim_obitos_externos` usam os campos de
`sim_obitos`, copiados por `scripts/metadados/gerar_subconjuntos_sim.py`: os
registros do DOINF, DOMAT e DOEXT são registros do DO. Em 11 anos de 1996 a 2024, os 7.999
residentes de RR com um único par no DORR (mesmas data e hora do óbito, nascimento, sexo e
causa básica) são iguais a ele, exceto `CONTADOR`, a numeração do arquivo.
Em 2010 e 2015 o subconjunto deixa vazios `CODBAIRES`, `CODBAIOCOR` e `NUDIASOBIN`, que o
DO preenche; nenhum campo traz um valor não vazio diferente
(`evidence/2026-09-23-sim-subconjuntos/`). O DOFET é outro registro e o CID-9 é
outra era: os dicionários deles partem do inventário físico do descritor DBF de uma fixture
real (`scripts/gen_dicionario.py`). Os rótulos de categoria vêm do CNV do TabWin quando o DEF
liga o campo e todo valor não branco da fixture é chave do mapa
(`sources/cnv/vinculos.json`); calendários, cadastros e faixas não são copiados. `sexo`
fica sem rótulo no DOFET e no CID-9: `SEXO.CNV` rotula só com as letras M, F e I.

## Armadilhas

- `idade` não está em anos: são 3 caracteres, o primeiro com a unidade e os dois
  seguintes com a quantidade (Estrutura do SIM 2025, p. 2).
- O documento lista as unidades 1 = minuto, 2 = hora, 3 = mês, 4 = ano e
  5 = idade maior que 100 anos, e 9 = ignorado (Estrutura do SIM 2025, p. 2).
- A unidade 3 é mês: o documento dá para ela a faixa "de 1 a menos de 12 meses
  completos", com quantidade de 01 a 11 (Estrutura do SIM 2025, p. 2). Em SIM Roraima
  2022, os 123 registros com unidade 3 tinham quantidade de 01 a 11
  (`evidence/2026-09-13-guia-pesquisador-validacao.md`, §4.3).
- Em óbito fetal, `idade` não deve ser preenchida (Estrutura do SIM 2025, p. 2).
- `sexo` usa M ou 1 = masculino, F ou 2 = feminino, e I, 0 ou 9 = ignorado
  (Estrutura do SIM 2025, p. 2).
- O contrato declara `sexo` como código textual, preservando letras e dígitos.
  O exemplo experimental antigo registra a divergência histórica de tipo lógico;
  a definição atual está no contrato público `describe_dataset()`.
- `causabas_o` guarda a causa básica informada antes da resseleção
  (Estrutura do SIM 2025, p. 6). Em outro campo, `altcausa` indica se houve correção
  ou alteração da causa do óbito após investigação (Estrutura do SIM 2025, p. 8).
- `tp_altera` traz códigos como "CausaBas em branco", "CausaBas com ausência do 4
  caractere" e "CausaBas inválida para o Sexo Feminino" (Estrutura do SIM 2025, p. 9).
- `codmunres` (residência) e `codmunocor` (ocorrência) respondem a perguntas
  diferentes e têm tamanhos declarados diferentes, 7 e 8 caracteres
  (Estrutura do SIM 2025, p. 3).
- A escolaridade do falecido aparece em mais de um campo: `esc` em anos de estudo
  (Estrutura do SIM 2025, p. 5), `esc2010` pelo nível da última série concluída
  (p. 2) e `escfalagr1` para o formulário a partir de 2010 (p. 7).
- `gestacao` é a faixa de semanas de gestação do formulário antigo
  (Estrutura do SIM 2025, p. 9); `semagestac` traz as semanas com dois algarismos
  (p. 4).
- `peso` é o peso ao nascer em gramas (Estrutura do SIM 2025, p. 4).
- O documento é a edição atualizada em 07/2025 (Estrutura do SIM 2025, p. 1).
- O documento não descreve `numerodo` nem `contador`, que o dicionário da biblioteca
  declara (Estrutura do SIM 2025, p. 1–9;
  `src/omnisus/data/dicionarios/sim_obitos.yaml`).
- Os códigos ficam no lake como publicados: o dicionário decodifica rótulos, datas e
  idade na exibição, não na importação (`src/omnisus/transforms/dictionaries.py`,
  docstring do módulo; `src/omnisus/sources/datasus_ftp/staging.py`, que não
  decodifica).

### Em aberto

- Se os arquivos `DORES` trazem óbitos fetais: o documento define os dois valores de
  `tipobito` (p. 1), mas na importação real de Roraima 2022–2023 nenhum dos 6 557
  registros era fetal (`evidence/2026-09-10-marimo-real/verification.json`,
  `filter_2022_non_fetal` e `empty_fetal_selection`). Não conte óbitos fetais com esta
  base sem conferir `tipobito` nos seus dados.
- A edição de 07/2025 diverge das unidades dos documentos anterior e DOM. O DOM
  confirma 0 = minutos, 1 = horas, 2 = dias e 3 = meses. O documento anterior
  distingue `000` ignorado e `400` menor de um ano sem subunidade. Há 91 valores
  `100`/`200` no snapshot fora dos mínimos documentais; a projeção aceita zero
  anos completos nesses escopos e registra essa decisão, conforme a auditoria abaixo.
- Se a edição de 07/2025 vale para arquivos de anos anteriores: o exemplo auditado do
  campo `sexo` deixa aberta a confirmação de uma referência aplicável a 2023
  (`docs/dicionario/exemplos/sim_obitos.sexo.json`, questão `edition-applicability`).
- Se um arquivo `DOUFAAAA` reúne óbitos de residentes na UF ou óbitos ocorridos na UF:
  o documento não explica o diretório `DORES`. Compare o prefixo de `codmunres` e de
  `codmunocor` com a UF do arquivo; a consulta `residencia_e_ocorrencia` do notebook faz
  isso.
- O comprimento do código de município nos dados: o documento declara 7 e 8
  caracteres (p. 3); os arquivos gravam 6, e o dicionário liga esses campos a
  `aux_municipios.codigo_6` ([vocabulários](vocabularios.md)). Confira nos seus dados
  antes de juntar com a população do IBGE.

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = odb.available("sim_obitos", years=[2022], ufs=["RR"], refresh=True)
relatorio = odb.import_dataset(
    "sim_obitos", scopes=escopos, target=alvo, policy="skip_same", run_id="sim-rr-2022"
)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT ano, count(*) AS obitos FROM lake.sim_obitos GROUP BY ano").pl())
```

Passo a passo com análise e procedência:
[notebooks/sim_obitos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py).

## Fontes

- Estrutura do SIM (`Estrutura_do_SIM_2025.pdf`), CGIAE/DASNT/SVS/MS, arquivo
  atualizado em 07/2025:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOCS/Estrutura_do_SIM_2025.pdf>
  — consultado em 2026-09-10; SHA-256
  `b4195ac8e0f825a794cb487df93db41601a2f430a708172f494f1251b55eeeb1`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).
- Exemplo auditado do campo `sexo`, com as questões abertas citadas acima:
  [sim_obitos.sexo.json](../dicionario/exemplos/sim_obitos.sexo.json).

## Detalhes técnicos

### Linha de comando

```bash
omnisus inventory sim_obitos --refresh
omnisus import sim_obitos --plan inventory --years 2020-2024 --ufs RR
```

As importações acrescentam linhas a `lake.sim_obitos`. Ao terminar, a importação
devolve um `ImportReport`; o estado de uma transação interrompida aparece em
`ImportAbortedError`. Veja
[resultados e transações](../guides/inventory.md#transactions-and-interrupted-imports).

### Dicionário

As definições de campo, os metadados de chave estrangeira e as regras de decodificação
ficam em `src/omnisus/data/dicionarios/sim_obitos.yaml`. A ingestão preserva os valores e tipos do DBF, normaliza nomes de colunas e
acrescenta as partições e a modalidade de origem. O YAML descreve campos e
apresentação; ele não comanda coerções na ingestão. Colunas não listadas no YAML
também são preservadas. A validação do dicionário, sozinha, não
certifica todos os registros recebidos.

### Dados preliminares

O DATASUS também publica `sim_obitos` em `/dissemin/publicos/SIM/PRELIM/DORES`, ao
lado do diretório final. Um ano pode estar disponível apenas em um dos dois;
`available_releases()` (em [Cobertura e modalidade](#cobertura-e-modalidade)) mostra
qual.

Cada linha carrega `_source_release` (`final` ou `prelim`), então um ano preliminar
convive na mesma tabela com anos finais sem se confundir com eles. Quando o DATASUS
republica um ano preliminar como final:

```python
with odb.LakeReader() as leitor:
    movidos = odb.outdated("sim_obitos", lake=leitor)
odb.import_dataset("sim_obitos", scopes=movidos,
                   policy="replace", run_id="sim-final-2026")
```

### Auditoria do contrato analítico (2026-09-14)

Regras, divergências, inventário e limites de aplicabilidade estão na
[auditoria reproduzível](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-contrato-analitico/regras.md).
Ela registra o snapshot 5, os hashes das publicações, schemas e consultas agregadas.
A aplicabilidade se restringe aos escopos confirmados; uma edição documental não
valida automaticamente toda a série histórica. A procedência de arquivo é
consultada por `LakeReader.publications()` no mesmo snapshot.

### Extensão de escopo (2026-09-14)

A regra 1.1.0 inclui o arquivo final DORR2021.dbc, identificado pelo SHA-256
`600b8af449468fec082e4e7ab6e852abae188cac73743c64dd470d122a41213a`.
As 4.306 linhas foram auditadas integralmente para idade, sexo e datas.
Os demais arquivos continuam sujeitos à confirmação individual de identidade.
Veja [relatório e reprodução](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-extensao-regras/README.md).
