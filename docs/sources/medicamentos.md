# Medicamentos · APAC, estoque e o que falta (`sia_apac_medicamentos`)

## Em uma frase

Três fontes públicas tocam medicamentos do SUS e nenhuma registra dispensação: a APAC
de medicamentos do SIA (no lake), a posição de estoque BNAFAR/Hórus (uma página por
consulta) e os indicadores de pessoas atendidas pela Farmácia Popular (sem importador);
eventos de dispensação não têm fonte pública confirmada.

## O que um registro representa

APAC de medicamentos (`sia_apac_medicamentos`, arquivo `AM`):

- As informações dos arquivos de APAC referem-se aos atendimentos ambulatoriais
  realizados em pacientes submetidos à APAC, nas respectivas competências
  (Informe SIASUS 2019-07, p. 5).
- O instrumento APAC gera um registro para cada código de procedimento realizado,
  principal ou secundário, e nos arquivos de APAC o procedimento contido refere-se ao
  procedimento principal (Informe SIASUS 2019-07, p. 5).
- `ap_autoriz` é o número da APAC, `ap_pripal` o procedimento principal da APAC e
  `ap_vl_ap` o valor total da APAC aprovado (Informe SIASUS 2019-07, p. 7).
- O layout do arquivo de medicamentos acrescenta ao layout comum da APAC só peso,
  altura, transplante, quantidade de transplantes e gestante do paciente
  (`AM_PESO` a `AM_GESTANT`) e não tem campo de quantidade de medicamento
  (Informe SIASUS 2019-07, p. 7).
- O dicionário da biblioteca foi gerado do cabeçalho do arquivo real `AMRR2401.dbf`,
  não do informe técnico (`src/omnisus/data/dicionarios/sia_apac_medicamentos.yaml`,
  comentário inicial).

Posição de estoque BNAFAR/Hórus:

- O endpoint `/daf/estoque-medicamentos-bnafar-horus` devolveu, numa consulta com
  `codigo_uf=14&limit=1`, um registro com data da posição de estoque, código CATMAT,
  quantidade em estoque, lote, validade e programa; o relatório classifica a unidade
  como item ou lote em estoque por estabelecimento
  ([relatório de 2026-09-12](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-12-sinan-e-dispensacao.md),
  Parte 2).
- A biblioteca lê uma página por chamada e marca a página como incompleta
  (`complete` é sempre falso), inclusive quando vem vazia ou curta
  (`src/omnisus/sources/medicamentos/horus.py`, `StockPage`).

Farmácia Popular:

- O catálogo MGDI descreve o Programa Farmácia Popular do Brasil como programa que
  entrega medicamentos utilizados na Atenção Primária à Saúde e lista recursos de
  pessoas atendidas por modalidade e por condição (catálogo MGDI Farmácia Popular,
  lido em 2026-09-13).
- Um desses recursos, `sntpbih.csv.zip`, tinha 22.283 linhas com número de pessoas por
  município e competência (relatório de 2026-09-12, Parte 2).

Dispensação:

- A BNAFAR consolida posições de estoque, movimentações e dispensações realizadas pelos
  estabelecimentos de saúde (página BNAFAR, lida em 2026-09-13).
- Pela FAQ, estados, Distrito Federal e municípios enviam os dados à BNAFAR por
  sistemas como Hórus, e-SUS AF e o serviço web de envio, entre outros, e os dados da
  Farmácia Popular são incorporados diretamente pelo Ministério da Saúde
  (FAQ BNAFAR, atualizada em 16/10/2025).
- O portal BNAFAR abriu uma página de login, e o "Rol de dados" exigiu autenticação;
  nenhuma fonte pública de eventos de dispensação foi confirmada
  (relatório de 2026-09-12, Parte 2 e §3.6).

## Datas e geografia

- O arquivo de medicamentos se chama `AMufaamm`: `uf` é a Unidade da Federação, `aa` o
  ano e `mm` o mês da competência (Informe SIASUS 2019-07, p. 5).
- As colunas `ano`, `uf` e `mes` vêm do nome do arquivo (`AMRR2401.dbc` → RR, 2024,
  mês 1) (`tests/unit/sources/datasus_ftp/test_filenames_golden.py`;
  `src/omnisus/sources/datasus_ftp/staging.py`).
- `ap_mvm` é a data de processamento ou movimento e `ap_cmp` a data de atendimento ao
  paciente ou competência, ambas AAAAMM (Informe SIASUS 2019-07, p. 7).
- `ap_dtinic` e `ap_dtfim` são as datas de início e de fim da validade da APAC, e
  `ap_tpapac` indica APAC inicial, de continuidade ou única
  (Informe SIASUS 2019-07, p. 7).
- `ap_munpcn` é UF + município de residência do paciente, e `ap_ufmun` UF + município
  do estabelecimento (Informe SIASUS 2019-07, p. 7).
- A consulta de estoque aceita os filtros `codigo_uf`, `codigo_municipio`,
  `codigo_cnes`, `anomes_posicao_estoque` e `data_posicao_estoque`, entre outros
  (`src/omnisus/sources/medicamentos/horus.py`, `FILTERS`).
- No registro de estoque observado, `data_posicao_estoque` era 2026-09-10
  (relatório de 2026-09-12, Parte 2).
- Os recursos da Farmácia Popular lidos pelo relatório têm competências esparsas:
  `sntpbih` trazia 202312, 202412, 202512 e 202607, e `pfpbben` 11 competências de
  201612 a 202607 (relatório de 2026-09-12, Parte 2).

## Cobertura e modalidade

- `sia_apac_medicamentos`: arquivos mensais por UF, de janeiro de 2008 em diante, no
  diretório `/dissemin/publicos/SIASUS/200801_/Dados`, sem diretório preliminar; veja o
  [catálogo de datasets](../datasets.md).
- Estoque BNAFAR/Hórus: uma página HTTP por chamada, até 1.000 registros, guardada com
  bytes e procedência e nunca publicada no lake; não há importador histórico nem
  nacional.
- Farmácia Popular / MGDI: fonte identificada, sem importador.
- Dispensação BNAFAR/RNDS: sem acesso público de leitura confirmado.

## Armadilhas

- As informações dos arquivos de APAC referem-se a atendimentos ambulatoriais
  (Informe SIASUS 2019-07, p. 5), e o layout do arquivo de medicamentos não tem campo
  de quantidade de medicamento (p. 7). Não leia linhas como doses nem como
  dispensações.
- Somar `ap_vl_ap` soma o valor total aprovado das APAC, não quantidades
  (Informe SIASUS 2019-07, p. 5 e p. 7).
- Contar linhas conta registros: o documento diz que a APAC gera um registro por código
  de procedimento realizado (Informe SIASUS 2019-07, p. 5), e o CNS do paciente
  (`ap_cnspcn`) é um campo à parte (p. 7).
- A APAC tem validade e pode ser de continuidade, com o número da APAC anterior em
  `ap_apacant` (Informe SIASUS 2019-07, p. 7).
- Estoque não é dispensação: a API pública de dados abertos tem só dois caminhos sobre
  medicamento, estoque BNAFAR/Hórus e entregas a DSEI, e nenhum de dispensação
  (relatório de 2026-09-12, Parte 2).
- Na BNAFAR, estoque, saídas e dispensação são registros diferentes: REPE para posição
  de estoque, RESMPE para saída por movimentação ou perda e REDFM para dispensação
  (FAQ BNAFAR, atualizada em 16/10/2025).
- Uma página de estoque vazia não demonstra ausência de estoque, e uma página curta não
  demonstra completude (`notebooks/medicamentos.py`, parte B;
  `src/omnisus/sources/medicamentos/horus.py`, `StockPage`).
- O endpoint de estoque não tem contrato documentado de snapshot ou de completude
  (`src/omnisus/sources/medicamentos/horus.py`, docstring do módulo).
- `offset` é o número da página, não `page * limit`
  (`src/omnisus/sources/medicamentos/horus.py`, `fetch_stock_page`).
- O caminho `/saude-indigena/sesai-assistencia-farmaceutica` cita "dispensação" no
  resumo do Swagger, mas o dicionário oficial define `Qtd Entregue` como quantidade
  entregue, sem data, município ou paciente (relatório de 2026-09-12, Parte 2).
- Os indicadores da Farmácia Popular são contagens agregadas de pessoas atendidas, não
  eventos de dispensação (relatório de 2026-09-12, Parte 2).
- O SI-BNAFAR é uma API para municípios e estados enviarem dados à BNAFAR
  (FAQ BNAFAR, atualizada em 16/10/2025); não é um endpoint de leitura para
  pesquisadores (relatório de 2026-09-12, Parte 2).

### Em aberto

- Quantas linhas uma APAC gera: o documento diz que a APAC gera um registro por código
  de procedimento, principal ou secundário, e, na frase seguinte, que nos arquivos de
  APAC o procedimento se refere ao principal (Informe SIASUS 2019-07, p. 5). Compare o
  número de linhas com o de valores distintos de `ap_autoriz` antes de contar APAC.
- Se a mesma APAC reaparece em meses seguintes: o documento prevê APAC de continuidade e
  período de validade (p. 7), mas não diz se cada mês publica a APAC de novo. Não some
  meses sem conferir `ap_autoriz` e `ap_tpapac`.
- A cobertura do estoque BNAFAR/Hórus: a leitura de uma página comprova aquela resposta,
  não a cobertura histórica ou nacional (`horus.py`, docstring do módulo).
- Uma fonte de dispensação para pesquisa: o relatório aponta como caminho realista uma
  extração fornecida pelo gestor ou pedida por LAI (relatório de 2026-09-12, Parte 2).

## Como usar

```python
import omnisus as sus
from omnisus.sources.medicamentos import fetch_stock_page

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = sus.available("sia_apac_medicamentos", years=[2024], ufs=["RR"], months=[1], refresh=True)
sus.import_dataset(
    "sia_apac_medicamentos", scopes=escopos, target=alvo, policy="skip_same", run_id="apac-am-rr-2024-01"
)
pagina = fetch_stock_page(filters={"codigo_uf": "14"}, limit=20)
print(pagina.sha256, len(pagina.records))
```

Passo a passo com a APAC em seis etapas, a página de estoque e o que não é público:
[notebooks/medicamentos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py).

## Fontes

- Disseminação de Dados em Saúde, Sistema de Informações Ambulatoriais do SUS
  (SIASUS), Informe Técnico (`Informe_Tecnico_SIASUS_2019_07.pdf`), Ministério da
  Saúde / Secretaria Executiva / DATASUS / CGGOV:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Doc/Informe_Tecnico_SIASUS_2019_07.pdf>
  — consultado em 2026-09-10; SHA-256
  `70fe69dbd4cf0827452e3c265d8d83ebeabe145f63a7e054e57c7848d070c8dc`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Relatório "SINAN além de Chagas e fontes públicas de dispensação", revisado em
  2026-09-12, Parte 2 e §3.6:
  <https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-12-sinan-e-dispensacao.md>.
- Página BNAFAR do Ministério da Saúde:
  <https://www.gov.br/saude/pt-br/composicao/sectics/daf/bnafar> — lida em 2026-09-13.
- FAQ BNAFAR, atualizada em 16/10/2025:
  <https://www.gov.br/saude/pt-br/composicao/sectics/daf/bnafar/faq/faq> — lida em
  2026-09-13.
- Catálogo MGDI Programa Farmácia Popular do Brasil:
  <https://dadosabertos.saude.gov.br/dataset/mgdi-programa-farmacia-popular-do-brasil>
  — lido em 2026-09-13.
- Especificação Swagger da API de dados abertos:
  <https://apidadosabertos.saude.gov.br/static/swagger.json> — lida pelo relatório em
  2026-09-11 e 2026-09-12 (Parte 2); não relida nesta revisão.
- Wiki do SIA/SUS: <https://wiki.saude.gov.br/sia/index.php/P%C3%A1gina_principal> —
  lida em 2026-09-13; diz que o SIA foi instituído pela Portaria GM/MS n.º 896 de 29 de
  junho de 1990.
- Notícia da Conitec sobre a SABEIS:
  <https://www.gov.br/conitec/pt-br/assuntos/noticias/2026/fevereiro/sabeis-libera-acesso-publico-a-dados-do-sus/>
  — respondeu HTTP 401 em 2026-09-13; nenhuma afirmação desta página depende dela.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).

## Detalhes técnicos

### APAC no lake

A APAC de medicamentos usa o mesmo parser, dicionário, validação, manifesto e
publicação das demais bases do FTP; não há outro importador para SIA-AM. Guarde um
`run_id` antes da execução e consulte o manifesto se o commit tiver resultado
desconhecido:

```python
with sus.LakeReader(alvo) as leitor:
    publicacoes = leitor.publications(run_id="apac-am-rr-2024-01")
```

Um arquivo que o DATASUS não publica aparece como `skipped`; ausência não é publicação.
Ao ampliar períodos, respeite alterações de layout e da tabela SIGTAP por competência.

### Cliente de estoque BNAFAR/Hórus

`fetch_stock_page` consulta `https://apidadosabertos.saude.gov.br/daf/estoque-medicamentos-bnafar-horus`.
Os filtros aceitos são exatamente `codigo_uf`, `codigo_municipio`, `codigo_cnes`,
`anomes_posicao_estoque`, `data_posicao_estoque`, `codigo_catmat`,
`sigla_programa_saude`, `tipo_produto` e `sigla_sistema_origem`, e ao menos um é
obrigatório. Use strings para preservar zeros dos identificadores. `limit` vai de 1 a
1.000 e `page` é enviado como `offset`, o número da página.

O cliente limita os bytes da resposta (4 MiB por padrão), usa tempo limite de 30
segundos, rejeita envelopes inesperados e propaga erros HTTP. Não pagina
automaticamente, não repete tentativas e não grava no lake: falta contrato de snapshot
e completude para substituir um recorte sem risco. Repetir um `offset` pode observar uma
base alterada. `StockPage.provenance()` guarda URL com parâmetros, horário UTC,
SHA-256 dos bytes recebidos, página, limite e número de linhas; preserve `raw` com a
procedência:

```python
from pathlib import Path
import json

Path("estoque-resposta.json").write_bytes(pagina.raw)
Path("estoque-procedencia.json").write_text(json.dumps(pagina.provenance(), indent=2))
```

Não se presume que o servidor aplicou corretamente cada filtro sem validação posterior.
Programas, apresentações, unidades de fornecimento e lotes precisam de interpretação
antes de qualquer agregação.

Os testes HTTP usam transporte simulado: offset por página, preservação dos bytes e
identificadores, resposta vazia, alteração de envelope, limite de bytes, erros HTTP e
parâmetros inválidos. Uma leitura real pequena complementa esses testes, mas não valida
a ingestão integral do estoque nem dispensações.

### Próximo contrato para dispensação

Antes de desenhar staging e publicação para dispensação é preciso identificar um recurso
oficial de leitura (ou uma exportação fornecida pelo gestor), sua edição, abrangência,
unidade observacional, terminologia do medicamento e regras de completude. Não preencher
essa lacuna com estoque, aquisições ou indicadores agregados apresentados como
dispensação.

### Notebook

```bash
uv run --locked --extra notebooks marimo edit notebooks/medicamentos.py
```

O notebook tem três partes: A, a APAC de Roraima, janeiro de 2024, nas seis etapas do
guia (o que a APAC registra, descobrir, baixar e ler, conferir, analisar, citar e
guardar); B, uma página de estoque BNAFAR/Hórus guardada com procedência em
`resultados/estoque/<sha256>/`, sem escrita no lake; e C, o que não existe
publicamente. As APAC vão para o lake de pesquisa compartilhado por `sus.load`, cuja
política padrão (`skip_same`) impede duplicar um arquivo já publicado.
