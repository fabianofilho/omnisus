# IBGE · população municipal (`ibge_populacao`)

## Em uma frase

População residente por município, importada de uma edição explícita (censo 2010,
censo 2022 ou a estimativa mais recente) pela API de dados agregados do IBGE, a API que
alimenta o SIDRA.

## O que um registro representa

- A visão `ibge_populacao` tem uma linha por município e ano, com `codigo_ibge`, `ano`
  e `populacao`, e declara a chave (`codigo_ibge`, `ano`)
  (`src/omnisus/data/dicionarios/ibge_populacao.yaml`).
- Cada linha vem da tabela canônica `ibge_population`, onde cada importação é uma
  publicação com seu próprio `publication_id`
  (`src/omnisus/sources/ibge/importers/pop.py`, `import_pop_year`).
- No censo 2010, o valor é a variável 93, "População residente", em Pessoas, do
  agregado 202, "População residente, por sexo e situação do domicílio"
  (metadados do agregado 202, `variaveis`).
- O agregado 202 se divide por Sexo e por Situação do domicílio, cada um com a
  categoria Total de código 0 (metadados do agregado 202, `classificacoes`), e a
  biblioteca lê o Total das duas (`src/omnisus/sources/ibge/products.py`,
  `resolve_product`).
- No censo 2022, o valor é a variável 93, "População residente", em Pessoas, do
  agregado 4714, que não tem classificações (metadados do agregado 4714).
- Na estimativa, o valor é a variável 9324, "População residente estimada", em
  Pessoas, do agregado 6579, da pesquisa Estimativas de População, sem classificações
  (metadados do agregado 6579).
- Os três agregados oferecem o nível territorial N6 (metadados dos agregados 202, 4714
  e 6579, `nivelTerritorial`), que a biblioteca exige como nível de município
  (`src/omnisus/sources/ibge/parse.py`, `municipal_codes`).

## Datas e geografia

- O censo 2010 teve como data de referência a noite de 31 de julho para 1º de agosto
  de 2010 (Metodologia do Censo Demográfico 2010, p. 44).
- As estimativas de população residente para o TCU têm data de referência em 1º de
  julho do ano de referência (Estimativas para o TCU, p. 1 e p. 9).
- A biblioteca grava a data de referência no manifesto: 1º de julho do ano para a
  estimativa e 1º de agosto do ano para o censo
  (`src/omnisus/sources/ibge/products.py`, `resolve_product`).
- `ano` é o ano de referência da edição
  (`src/omnisus/data/dicionarios/ibge_populacao.yaml`, rótulo de `ano`).
- `codigo_ibge` tem 7 dígitos, o primeiro de 1 a 5
  (`src/omnisus/sources/ibge/parse.py`, `municipal_codes`;
  `src/omnisus/data/dicionarios/ibge_populacao.yaml`).
- Para juntar com óbitos do SIM, o notebook compara os 6 primeiros dígitos dos dois
  códigos (`notebooks/ibge_populacao.py`, consulta `obitos_por_100_mil`).
- A lista de municípios de uma edição vem do endpoint de localidades do agregado
  (`src/omnisus/sources/ibge/fetch.py`, `fetch_pop_by_year`), que só recebe o
  agregado e o nível (documentação da API de agregados, "Localidades por agregado").
- Como esse endpoint não recebe período, a biblioteca só aceita a edição mais recente
  de cada agregado (`src/omnisus/sources/ibge/fetch.py`, `fetch_pop_by_year`).
- Na linha de 1992, a nota diz que as estimativas foram realizadas segundo as
  situações político-administrativas vigentes em 1º de julho dos respectivos anos de
  referência (Estimativas para o TCU, p. 8). As notas de 2012 e 2008 (p. 7) e de 2004
  (p. 8) registram municípios instalados a partir do ano seguinte ao de referência.

## Cobertura e modalidade

Não há arquivos por UF nem inventário: a população do IBGE usa um importador próprio,
fora do [catálogo de datasets](../datasets.md), que cobre o FTP do DATASUS. Cada
chamada pede um produto e um ano:

- `census`: 2010 e 2022 (`src/omnisus/sources/ibge/products.py`, `CENSUS_YEARS`).
- `estimate`: só o período mais recente do agregado 6579
  (`src/omnisus/sources/ibge/fetch.py`); 2007, 2010, 2022 e 2023 são recusados antes
  de qualquer consulta (`src/omnisus/sources/ibge/products.py`,
  `ESTIMATE_UNAVAILABLE_YEARS`). Os metadados do agregado 6579 declaram periodicidade
  anual de 2001 a 2026 (lidos em 2026-09-13).

## Armadilhas

- As estimativas para o TCU não formam uma série temporal consistente, por novas
  informações, mudanças de método e mudanças na divisão político-administrativa
  (Estimativas para o TCU, p. 9).
- O documento dá o exemplo de São Paulo, com 12.396.372 habitantes em 2021 e
  11.895.578 em 2024, valores que não são estatisticamente comparáveis
  (Estimativas para o TCU, p. 9).
- Não houve estimativa para o TCU publicada em 2022 nem em 2023
  (Estimativas para o TCU, p. 1).
- Na linha de 2010, a nota registra que os coeficientes do FPE e do FPM para o
  exercício de 2011 usaram os primeiros resultados do Censo 2010
  (Estimativas para o TCU, p. 7).
- Em 2007, os dados vieram da Contagem da População em 5.435 municípios, com data de
  referência em 1º de abril de 2007, e de estimativas nos demais
  (Estimativas para o TCU, p. 8).
- A biblioteca não troca uma estimativa ausente pelo censo: pedir `estimate` para 2007,
  2010, 2022 ou 2023 gera erro (`src/omnisus/sources/ibge/products.py`,
  `resolve_product`).
- Censo e estimativa têm datas de referência diferentes: a noite de 31 de julho para
  1º de agosto no censo 2010 (Metodologia do Censo Demográfico 2010, p. 44) e 1º de
  julho na estimativa (Estimativas para o TCU, p. 9).
- Algumas populações municipais das estimativas para o TCU vêm de decisão judicial,
  como Jacareacanga (PA) (Estimativas para o TCU, p. 1–7).
- As populações dos estados publicadas pelo IBGE podem não corresponder à soma dos
  seus municípios quando há decisão judicial (Estimativas para o TCU, p. 5).
- Uma edição pode trazer municípios instalados depois do ano de referência, com o
  município de origem sem a população alocada a eles
  (Estimativas para o TCU, p. 7, nota de 2012).
- O universo de municípios é o que o agregado lista hoje, não uma lista histórica
  verificada do ano (`src/omnisus/sources/ibge/fetch.py`, `fetch_pop_by_year`).
- Cada importação é uma nova publicação, e a visão `ibge_populacao` falha quando um
  município e ano têm duas publicações
  (`src/omnisus/sources/ibge/importers/pop.py`, `import_pop_year`).

### Em aberto

- A data de referência do censo 2022: a biblioteca grava 2022-08-01 com a nota "noite
  de 31/07/2022 para 01/08/2022" (`src/omnisus/sources/ibge/products.py`), mas a
  página do IBGE citada no código devolveu HTTP 403 em 2026-09-13 e não foi conferida
  nesta revisão.
- Se os valores do agregado 6579 são os mesmos das estimativas para o TCU que o
  DATASUS descreve, incluindo as populações judiciais: a nota técnica trata dos
  arquivos do TCU (p. 1), e a página de produto do IBGE devolveu HTTP 403 em
  2026-09-13. Confira um município com população judicial antes de supor.

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
resultados = odb.import_ibge_populacao(years=[2022], census=True, target=alvo)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT ano, count(*) AS municipios, sum(populacao) FROM lake.ibge_populacao GROUP BY ano").pl())
```

Rodar a importação duas vezes para a mesma edição faz a visão `ibge_populacao` falhar,
porque o município e ano passam a ter duas publicações.

Passo a passo com análise e procedência, que consulta o manifesto antes de importar:
[notebooks/ibge_populacao.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py).

## Fontes

- População Residente Estimativas para o TCU (IBGE), Nota Técnica
  (`Pop_Residente_TCU_ate_2023.pdf`), MS/SVSA/DAENT/CGIAE, publicada pelo DATASUS:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/IBGE/DOC/Pop_Residente_TCU_ate_2023.pdf>
  — consultado em 2026-09-10; SHA-256
  `ae71f4736dcebed703ac4b50b7b1b496d4dded1c3f726e57005ec5f216b6d817`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Metodologia do Censo Demográfico 2010, IBGE, Série Relatórios Metodológicos,
  volume 41:
  <https://ftp.ibge.gov.br/Censos/Censo_Demografico_2010/metodologia/metodologia_censo_dem_2010.pdf>
  — lido em 2026-09-13 (seção 1.3, p. 44); SHA-256 do arquivo lido
  `a6243c8a1f3c5ac54c54431d07148feb163fb2563b225c29bdfb026d7627ad84`.
- [Documentação da API de dados agregados do IBGE](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3),
  versão 3.0.0 — lido em 2026-09-13.
- Metadados dos agregados
  [202](https://servicodados.ibge.gov.br/api/v3/agregados/202/metadados),
  [4714](https://servicodados.ibge.gov.br/api/v3/agregados/4714/metadados) e
  [6579](https://servicodados.ibge.gov.br/api/v3/agregados/6579/metadados) — lidos em
  2026-09-13.
- [Estimativas de população, página do produto](https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativasde-populacao.html)
  — devolveu HTTP 403 em 2026-09-13; não lido nesta revisão.
- [Censo Demográfico 2022, períodos de referência](https://www.ibge.gov.br/Estatisticas/Sociais/Populacao/22827-censo-demografico-2022.html?edicao=41815)
  — devolveu HTTP 403 em 2026-09-13; não lido nesta revisão.

## Detalhes técnicos

### Importador

O importador HTTP/SIDRA é separado e exige `years` e `census`:

```python
import omnisus as odb

odb.import_ibge_populacao(years=[2022], census=True, target="ducklake:population.ducklake")
```

Ele devolve `list[ImportResult]`, fora do inventário do FTP e do `ImportReport`. Não
aceita `run_id` nem `policy` e nunca aparece em `Lake.publications()`: cada edição é
sua própria publicação, identificada pelo `publication_id` em
`ibge_population_manifest`. Uma execução interrompida se reconcilia por esse manifesto,
não pelo run ID.

### Edições aceitas

| Produto | Agregado / variável | Edição aceita |
|---|---|---|
| `census` | 202 / 93 | 2010; Sexo Total `2[0]`, Situação do domicílio Total `1[0]` |
| `census` | 4714 / 93 | 2022; sem classificações |
| `estimate` | 6579 / 9324 | Período mais recente devolvido pela API do agregado (2026 na verificação de 2026-09-10) |

A implementação busca e valida os metadados, os períodos e as localidades municipais do
agregado. Exige que a edição pedida seja o período mais recente daquele agregado, o que
torna o universo de localidades aplicável a essa edição. O endpoint de localidades
documentado não tem filtro de período. **Estimativas históricas, incluindo 2024, estão
por isso explicitamente indisponíveis nesta versão**; elas exigem um universo
territorial daquele ano, obtido de fonte independente e arquivado. Passar `periodo` ao
endpoint de localidades não estabelece esse contrato. A lista territorial atual nunca
é apresentada como lista histórica verificada. Nenhuma contagem nacional fixa de
municípios é presumida. Uma extensão futura pode aceitar artefatos de edição revisados
com os códigos exatos, o ano, a URL oficial e o hash.

A Contagem da População de 2007 e a publicação territorial de 2023 são outros produtos
e não são aceitas aqui. Uma estimativa ausente nunca vira silenciosamente um número do
censo. Períodos ausentes no produto escolhido geram um erro explícito de
indisponibilidade.

A [documentação oficial da API](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3)
descreve os endpoints de metadados, períodos, localidades e população. Os metadados de
[202](https://servicodados.ibge.gov.br/api/v3/agregados/202/metadados),
[4714](https://servicodados.ibge.gov.br/api/v3/agregados/4714/metadados) e
[6579](https://servicodados.ibge.gov.br/api/v3/agregados/6579/metadados) estabelecem os
contratos de variável e de categoria Total.

### Validação e procedência

Antes de qualquer escrita, o importador valida exatamente uma variável e um resultado
Total, a unidade Pessoas, o nível N6, códigos de sete dígitos, o ano exato, municípios
únicos, valores inteiros não negativos e a igualdade exata do conjunto com o universo
verificado. Resultados vazios, municípios ausentes ou a mais e todos os símbolos
estatísticos (incluindo `...`, `-` e `X`) fazem a carga inteira falhar; os símbolos não
são descartados nem convertidos em zero. A revisão do período é lida de novo depois da
coleta, e uma mudança aborta a carga. Essa conferência não é garantia de snapshot no
servidor.

`ibge_population` é a tabela canônica: `codigo_ibge`, `ano`, `populacao` (UInt64),
`product`, `publication_id`. É particionada por `ano`. Cada acréscimo tem um novo UUID
de publicação. `ibge_population_manifest` guarda o mesmo UUID, produto, fonte,
agregado, variável, SHA-256 do corpo original da resposta de população, URL, instante
UTC da coleta, período e revisão da fonte, contagens esperada, aceita e rejeitada,
versão do parser e evidência em JSON. A evidência inclui as URLs das requisições e os
hashes dos corpos de todos os documentos de controle, de metadados e de períodos, e os
códigos exatos do universo. Os hashes de corpo HTTP descrevem os bytes de conteúdo que
o HTTPX expõe (depois de qualquer decodificação de conteúdo HTTP). Os bytes brutos da
população são resumidos por hash, não arquivados. Dados, manifesto e criação da visão
de compatibilidade são gravados numa única transação; uma escrita que falha ou é
cancelada preserva as publicações anteriores.

`ibge_populacao` é uma visão de compatibilidade que expõe as três colunas antigas. Ler
`populacao` falha quando há mais de uma publicação para um município e ano; nesse caso,
selecione um `publication_id` explícito na tabela canônica. A tabela canônica preserva
o histórico de acréscimos sem deduplicar. Uma tabela `ibge_populacao` legada ou uma
visão não reconhecida causam erro de migração e ficam intactas. Essas conferências não
inventariam nem certificam dados arbitrários inseridos por SQL direto.

### Referências temporais separadas

O manifesto grava `population_reference_date` como DATE, com
`population_reference_source_url` e uma nota que preserva sua interpretação:

| Produto / edição | Data gravada | Formulação oficial da referência |
|---|---|---|
| Estimativa | 1º de julho do ano pedido | 1º de julho do ano calendário |
| Censo 2010 | 2010-08-01 | Noite de 31 de julho para 1º de agosto de 2010 |
| Censo 2022 | 2022-08-01 | Noite de 31 de julho para 1º de agosto de 2022 |

Nas datas do censo, 1º de agosto é a convenção de armazenamento para o limite da
meia-noite, não uma afirmação de que a coleta ocorreu nesse dia. A nota preserva a
formulação da noite entre duas datas; nenhum fuso UTC é atribuído a essa referência
local do censo. A referência da estimativa segue a
[definição oficial do produto](https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativasde-populacao.html).
As referências do censo seguem a
[metodologia de 2010](https://ftp.ibge.gov.br/Censos/Censo_Demografico_2010/metodologia/metodologia_censo_dem_2010.pdf)
e os [períodos de referência de 2022](https://www.ibge.gov.br/Estatisticas/Sociais/Populacao/22827-censo-demografico-2022.html?edicao=41815).

`territorial_reference_date` e `publication_date` são campos DATE anuláveis e ficam
explicitamente NULL: os metadados e períodos do agregado escolhido não estabelecem essas
datas para a resposta. `temporal_metadata_note` registra essa incerteza.
`source_revision` preserva o texto `modificacao` do período; `revision` continua como
seu alias de compatibilidade. `collected_at` é o instante UTC da coleta. Nem a revisão
nem a coleta substituem as datas de referência da população, do território ou da
publicação. A versão do parser do manifesto para este contrato é `ibge-population-v2`;
manifestos de publicações anteriores continuam como registros históricos.
