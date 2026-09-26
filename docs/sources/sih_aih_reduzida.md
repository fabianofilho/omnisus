# SIH · AIH reduzida (`sih_aih_reduzida`)

## Em uma frase

Autorizações de Internação Hospitalar (AIH) do Sistema de Informações Hospitalares do
SUS (SIH/SUS), nos arquivos RD que o DATASUS publica um por UF e mês de processamento.

## O que um registro representa

- O dicionário da biblioteca descreve a base como "SIHSUS — AIH Reduzida (RD)" e não
  declara chave primária (`src/omnisus/data/dicionarios/sih_aih_reduzida.yaml`,
  `title`, sem `primaryKey`).
- O documento oficial descreve o layout dos arquivos `RD*.dbf` para janeiro de 2008 em
  diante (Informe SIH 2016-03, p. 1).
- Cada linha traz o número da AIH em `n_aih`, com 13 caracteres, e o tipo da AIH em
  `ident` (Informe SIH 2016-03, p. 1).
- O documento não lista os códigos de `ident` (Informe SIH 2016-03, p. 1); o
  dicionário os decodifica como 1 = AIH principal, 3 = AIH de continuação e 5 = AIH de
  longa permanência (`src/omnisus/data/dicionarios/sih_aih_reduzida.yaml`).
- `seq_aih5` é o sequencial de longa permanência, da AIH tipo 5
  (Informe SIH 2016-03, p. 3).
- O layout RD não traz o número do Cartão Nacional de Saúde do paciente
  (Informe SIH 2016-03, p. 1–4); `aud_just` e `sis_just` guardam a justificativa para
  aceitar a AIH sem esse número (p. 3).
- `homonimo` indica se o paciente da AIH é homônimo do paciente de outra AIH
  (Informe SIH 2016-03, p. 3).
- `diag_princ` é o código do diagnóstico principal pela CID-10, com 4 caracteres
  (Informe SIH 2016-03, p. 2), e o dicionário o liga à tabela `aux_cid10`
  (`src/omnisus/data/dicionarios/sih_aih_reduzida.yaml`).
- `val_tot` é o valor total da AIH (Informe SIH 2016-03, p. 2).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta `ano`,
  `uf`, `mes` e `_source_release` a cada linha
  (`src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`;
  `src/omnisus/sources/datasus_ftp/_runner.py`, `ingest_raw`).

## Datas e geografia

- `ano_cmpt` e `mes_cmpt` são o ano e o mês de processamento da AIH
  (Informe SIH 2016-03, p. 1), e a data de internação é outro campo (p. 2).
- A data de internação está em `dt_inter` e a data de saída em `dt_saida`, ambas no
  formato aaaammdd no recorte; o Informe SIH 2016-03, p. 2, declara char(8), mas
  grafa o primeiro campo `DI_INTER` e seu formato `aaammdd`, inconsistências
  documentais preservadas na auditoria.
- `nasc` é a data de nascimento do paciente, no formato aaaammdd
  (Informe SIH 2016-03, p. 1).
- `gestor_dt` é a data da autorização dada pelo gestor, no formato aaaammdd
  (Informe SIH 2016-03, p. 3).
- As colunas `ano`, `uf` e `mes` vêm do nome do arquivo (`RDSP2401.dbc` → SP, 2024,
  mês 1) (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- `munic_res` é o município de residência do paciente, com 6 caracteres
  (Informe SIH 2016-03, p. 1).
- `munic_mov` é o município do estabelecimento, com 6 caracteres
  (Informe SIH 2016-03, p. 2).
- `uf_zi` é o município gestor, com 6 caracteres (Informe SIH 2016-03, p. 1), embora o
  dicionário o rotule "UF do gestor"
  (`src/omnisus/data/dicionarios/sih_aih_reduzida.yaml`).
- `cnes` é o código CNES do hospital, com 7 caracteres (Informe SIH 2016-03, p. 3).
- O dicionário liga `munic_res` e `munic_mov` a `aux_municipios.codigo_6`; `diag_secun`, `cid_asso` e `cid_morte` gravam `0000` quando não há causa ([vocabulários](vocabularios.md)).
  A importação preserva o comprimento dos códigos publicados; não aplica
  preenchimento de zeros guiado pelo YAML.

## Cobertura e modalidade

Arquivos mensais por UF, de janeiro de 2008 em diante, no diretório
`/dissemin/publicos/SIHSUS/200801_/Dados`, sem diretório preliminar; veja o
[catálogo de datasets](../datasets.md). Os arquivos `RJ`, `SP` e `ER`, que o mesmo documento
descreve (Informe SIH 2016-03, p. 4–5), são linhas próprias; veja abaixo.

### Outras linhas do SIH

| Linha | Prefixo | Diretório | Cobertura |
| --- | --- | --- | --- |
| `sih_aih_rejeitada` | `RJ` | `SIHSUS/200801_/Dados` | 2008-01 em diante |
| `sih_servicos_profissionais` | `SP` | `SIHSUS/200801_/Dados` | 2008-01 em diante |
| `sih_aih_rejeitada_erro` | `ER` | `SIHSUS/200801_/Dados` | 2011-01 em diante |
| `sih_aih_reduzida_1992_2007` | `RD` | `SIHSUS/199201_200712/Dados` | 1992-01 a 2007-12; o diretório `Doc` dessa era está vazio no servidor |

Os dicionários dessas linhas partem do inventário físico do descritor DBF de uma fixture real (`scripts/gen_dicionario.py`). Os rótulos de categoria vêm do CNV do TabWin quando o DEF liga o campo e todo valor não branco da fixture é chave do mapa (`sources/cnv/vinculos.json`); calendários, cadastros e faixas não são copiados. Ficam sem rótulos `sih_aih_rejeitada_erro` (o DEF só liga ano e mês) e `sih_aih_reduzida_1992_2007` (os DEF das eras antigas, `SIHSUS/200801_/Auxiliar/TAB_SIH_199201-199712.zip` e os dois seguintes, não estão arquivados). `CH` e `CM` (nacionais, desde 2019) e as eras antigas de `RJ` e `SP` não estão no catálogo.

## Armadilhas

- Há AIH de tipos diferentes em `ident` (Informe SIH 2016-03, p. 1) e um sequencial
  próprio para a AIH de longa permanência (p. 3).
- A consulta `aih_distintas` do notebook compara o número de linhas com o número de
  valores distintos de `n_aih` antes de qualquer contagem
  (`notebooks/sih_aih_reduzida.py`).
- Agregar por `mes_cmpt` conta AIH processadas no mês (Informe SIH 2016-03, p. 1); para
  contar internações por mês de ocorrência, use `dt_inter` (p. 2).
- `morte` "indica óbito", com 1 algarismo, e o documento não lista os códigos
  (Informe SIH 2016-03, p. 2); os códigos e rótulos vêm do pacote oficial
  `TAB_SIH.zip`, republicado pelo DATASUS em 2026-09-15, `RD2008.DEF` →
  `MORTES.CNV` (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`).
- `cid_morte` é a CID da morte (Informe SIH 2016-03, p. 3), e `cobranca` é o motivo de
  saída ou permanência (p. 2); os códigos e rótulos de `cobranca` vêm do mesmo pacote
  `TAB_SIH.zip`, `RD2008.DEF` → `SAIDAPERM.CNV` — por exemplo, 26 = permanência por
  mudança de procedimento e 31 = transferência para outro estabelecimento
  (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`).
- Os complementos federal e do gestor de serviços hospitalares e profissionais
  (`val_sh_fed`, `val_sp_fed`, `val_sh_ges`, `val_sp_ges`) estão incluídos no valor
  total da AIH (Informe SIH 2016-03, p. 4).
- `us_tot` é o valor total em dólar, não em reais (Informe SIH 2016-03, p. 2).
- Vários campos de valor vêm zerados: `val_sadt`, `val_rn`, `val_acomp`, `val_ortp`,
  `val_sangue`, `val_sadtsr`, `val_transp`, `val_obsang` e `val_ped1ac`
  (Informe SIH 2016-03, p. 2).
- Também vêm zerados `uti_mes_in`, `uti_mes_an`, `uti_mes_al`, `uti_int_in`,
  `uti_int_an` e `uti_int_al` (Informe SIH 2016-03, p. 1); a quantidade de dias de UTI
  no mês está em `uti_mes_to` (p. 1).
- `diag_secun` vem preenchido com zeros a partir de 201501
  (Informe SIH 2016-03, p. 2); os diagnósticos secundários estão em `diagsec1` a
  `diagsec9` (p. 4).
- `natureza` tem conteúdo só até maio de 2012; a natureza jurídica pela CONCLA está em
  `nat_jur` (Informe SIH 2016-03, p. 2).
- `idade` depende de `cod_idade` (Informe SIH 2016-03, p. 2). O pacote oficial
  `TAB_SIH.zip`, `CNV/IDADEDET.CNV`, confirma dias, meses, anos e unidade 5 com
  deslocamento de 100 anos no domínio detalhado. Os códigos compostos `000` e
  `999` são classificados como inválidos; isso não define uma sentinela global
  para o campo bruto `idade`.
- `sexo` tem 1 caractere (Informe SIH 2016-03, p. 1). A tabela oficial
  `CNV/SEXO.CNV` define 1 masculino e 2/3 feminino. A aplicação dessas regras
  exige os escopos e hashes confirmados no contrato; códigos não documentados
  permanecem desconhecidos.
- Os códigos ficam no lake como publicados: o dicionário decodifica rótulos, datas e
  idade na exibição, não na importação (`src/omnisus/transforms/dictionaries.py`,
  docstring do módulo; `src/omnisus/sources/datasus_ftp/staging.py`, que não
  decodifica).
- O texto é lido como `latin-1`: cada byte vira o caractere de mesmo valor, e
  `valor.encode("latin-1")` devolve os bytes do arquivo. Com `cp1252`,
  um único byte 0x90 em `aud_just` derrubava a importação de `RDSP2308`
  (SHA-256 `eb5d97e8…f3ebb`).
- Em `aud_just` de RD SP de 2022-12 a 2023-12 (13 arquivos, 1.056 valores), os únicos
  bytes de 0x80 a 0x9F são 0x80, 0x87 e 0x90, que em CP850 são Ç, ç e É:
  `DOA\x80AO` é "DOAÇAO", `INFORMA\x87oES` é "INFORMAçoES", `REC\x90M` é "RECÉM".
  Nenhum outro campo desses arquivos tem byte nessa faixa. Para ler em CP850:
  `valor.encode("latin-1").decode("cp850")`. A biblioteca não converte: o dicionário
  declara uma codificação por arquivo, não por campo.

### Em aberto

- O que uma linha representa: o documento traz o número da AIH (`n_aih`,
  Informe SIH 2016-03, p. 1), mas não diz que cada linha é uma AIH distinta, e o layout
  RD não traz o número do Cartão Nacional de Saúde do paciente (p. 1–4). Não trate
  linhas como pacientes, e compare linhas com valores distintos de `n_aih` (consulta
  `aih_distintas`) antes de contar AIH.
- Se uma internação longa aparece em mais de uma linha: o documento traz o tipo da AIH
  e o sequencial de longa permanência (p. 1 e p. 3), mas não diz como uma internação se
  divide em AIH. Não conte internações como linhas sem olhar `ident`, `seq_aih5` e
  `n_aih` nos seus dados.
- Se o mês do arquivo (`mes`) é sempre igual a `mes_cmpt`: o documento não explica o
  nome do arquivo. Compare as duas colunas antes de supor.
- Os códigos de `ident`: o informe não os lista. Para idade e sexo,
  a auditoria de 2026-09-14 acrescentou o pacote oficial TAB_SIH: unidade 5 usa
  100 + quantidade no domínio confirmado; sexo 1 é masculino e 2/3 feminino. A consulta `campo_morte` do notebook mostra
  os valores publicados.
- `complex`, `ident`, `instru`, `natureza`, `raca_cor`, `sexo` e `vincprev` mantêm o
  mapa manual: o CNV de cada um reivindica um código duas vezes (faixa e valor
  explícito), e o gerador rejeita esse caso
  (`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`, `sem_cnv`).
- O comprimento do código de município nos dados: o documento declara 6 caracteres
  (p. 1–2). Confira nos seus dados antes de juntar com outra base.
- Se o layout vale para arquivos processados depois de 2016-03: o documento é o informe
  desse processamento (p. 1).

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = odb.available("sih_aih_reduzida", years=[2024], ufs=["RR"], months=[1], refresh=True)
relatorio = odb.import_dataset(
    "sih_aih_reduzida", scopes=escopos, target=alvo, policy="skip_same", run_id="sih-rr-2024-01"
)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT ano, mes, count(*) AS aih FROM lake.sih_aih_reduzida GROUP BY ALL").pl())
```

Passo a passo com análise e procedência:
[notebooks/sih_aih_reduzida.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py).

## Fontes

- Disseminação de Informações do Sistema de Informações Hospitalares (SIH), Informe
  Técnico referente ao processamento 2016-03 (`IT_SIHSUS_1603.pdf`), Ministério da
  Saúde / Secretaria de Gestão Estratégica e Participativa / DATASUS:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf>
  — consultado em 2026-09-10; SHA-256
  `1e89d5f2cc41420385d7e30ba5541a387912ab3a0efb167d39def74502076220`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).

## Detalhes técnicos

### Linha de comando

```bash
omnisus inventory sih_aih_reduzida --refresh
omnisus import sih_aih_reduzida --plan inventory --years 2020-2024 --ufs RR
```

As importações acrescentam linhas a `lake.sih_aih_reduzida`. Ao terminar, a importação
devolve um `ImportReport`; o estado de uma transação interrompida aparece em
`ImportAbortedError`. Veja
[resultados e transações](../guides/inventory.md#transactions-and-interrupted-imports).

### Dicionário

As definições de campo, os metadados de chave estrangeira e as regras de decodificação
ficam em `src/omnisus/data/dicionarios/sih_aih_reduzida.yaml`. A ingestão preserva os valores e tipos do DBF, normaliza nomes de colunas e
acrescenta as partições e a modalidade de origem. O YAML descreve campos e
apresentação; ele não comanda coerções na ingestão. Colunas não listadas no YAML
também são preservadas. A validação do dicionário, sozinha, não
certifica todos os registros recebidos.

### Auditoria do contrato analítico (2026-09-14)

Regras, divergências, inventário e limites de aplicabilidade estão na
[auditoria reproduzível](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-contrato-analitico/regras.md).
Ela registra o snapshot 5, os hashes das publicações, schemas e consultas agregadas.
A aplicabilidade se restringe aos escopos confirmados; uma edição documental não
valida automaticamente toda a série histórica. A procedência de arquivo é
consultada por `LakeReader.publications()` no mesmo snapshot.

### Extensão de escopo (2026-09-14)

A regra 1.1.0 inclui o arquivo final RDRR2301.dbc, identificado pelo SHA-256
`e9f717ff378477a883d19f733efe8409aee7f7795a027584b9f383364264d8e4`.
As 4.734 linhas foram auditadas integralmente para idade, sexo e datas.
Códigos fora do domínio documentado permanecem sem interpretação exata.
Veja [relatório e reprodução](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-extensao-regras/README.md).
