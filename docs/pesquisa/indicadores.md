# Indicadores

Esta página mostra como montar uma taxa com as bases do lake e o que conferir antes.
As definições oficiais citadas vêm do livro da RIPSA *Indicadores básicos para a saúde
no Brasil: conceitos e aplicações*, 2ª edição, 2008 (abreviado aqui como RIPSA 2008;
veja [Fontes](#fontes)). Quando a página diz "este guia", o cálculo ou o cuidado é
nosso, não uma definição oficial.

## Numerador e denominador

- A RIPSA define a taxa bruta de mortalidade como o número total de óbitos por mil
  habitantes na população residente, num espaço geográfico e ano
  (RIPSA 2008, p. 84).
- O método de cálculo divide o número total de óbitos de residentes pela população
  total residente e multiplica por 1.000 (RIPSA 2008, p. 84).
- Na mesma ficha, a RIPSA recomenda usar no numerador os óbitos informados ao SIM
  quando forem ao menos 80% dos óbitos estimados por métodos demográficos, e o número
  estimado quando forem menos (RIPSA 2008, p. 84).
- Um uso listado da população total é prover o denominador de taxas de base
  populacional (RIPSA 2008, p. 58).
- Nem todo denominador vem do IBGE: a proporção de nascidos vivos de baixo peso divide
  os nascidos vivos de mães residentes com menos de 2.500 g pelo total de nascidos vivos
  de mães residentes, vezes 100 (RIPSA 2008, p. 218).
- O exemplo abaixo, **óbitos por 100 mil habitantes**, é um cálculo deste guia: usa o
  numerador e o denominador da taxa bruta, multiplica por 100.000 em vez de 1.000 e não
  aplica a regra dos 80% nem padronização por idade. Para chegar à escala da RIPSA,
  divida por 100.

Numerador e denominador precisam falar do mesmo lugar e do mesmo período. As duas
seções seguintes mostram onde isso costuma falhar.

## Residência, ocorrência e notificação

Cada base guarda mais de um município por registro, e cada um responde a uma pergunta
diferente. As fichas lidas da RIPSA contam eventos de residentes: óbitos de residentes
na taxa bruta de mortalidade (RIPSA 2008, p. 84) e nascidos vivos de mães residentes na
proporção de baixo peso ao nascer (RIPSA 2008, p. 218).

| Base | Residência | Outro município | Fonte |
| --- | --- | --- | --- |
| [SIM](../sources/sim_obitos.md#datas-e-geografia) | `codmunres`, declarado com 7 caracteres | `codmunocor`, onde ocorreu o óbito, 8 caracteres | Estrutura do SIM 2025, p. 3 |
| [SINASC](../sources/sinasc_nascidos_vivos.md#datas-e-geografia) | `codmunres`, residência da mãe, 7 caracteres | `codmunnasc`, onde ocorreu o nascimento, 7 caracteres | Estrutura do SINASC para CD, p. 1 |
| [SIH](../sources/sih_aih_reduzida.md#datas-e-geografia) | `munic_res`, residência do paciente, 6 caracteres | `munic_mov`, município do estabelecimento, 6 caracteres | Informe SIH 2016-03, p. 1–2 |
| [SINAN](../sources/sinan_chagas.md#datas-e-geografia) | `id_mn_resi`, residência na notificação, 6 caracteres | `id_municip`, município da unidade que notificou | Dicionário Notificação Individual v5, p. 2 e p. 6 |

As fontes da tabela são as citadas nos perfis. Os tamanhos são os que os documentos
declaram, não os que os arquivos trazem; a seção
[Conferir o código do município](#conferir-o-codigo-do-municipio-antes-de-juntar) mostra
uma diferença real.

## População do IBGE

- A biblioteca importa uma edição explícita: `census` para 2010 e 2022, ou `estimate`
  (`src/omnisus/sources/ibge/products.py`, `CENSUS_YEARS` e `resolve_product`).
- Uma estimativa só é aceita no período mais recente do agregado 6579
  (`src/omnisus/sources/ibge/fetch.py`, `fetch_pop_by_year`), e os anos
  `ESTIMATE_UNAVAILABLE_YEARS = (2007, 2010, 2022, 2023)` são recusados antes de
  qualquer consulta (`src/omnisus/sources/ibge/products.py`).
- A biblioteca não troca uma estimativa ausente pelo censo: pedir `estimate` para um
  desses anos gera erro ([perfil da população](../sources/ibge_populacao.md#armadilhas)).
- O censo 2010 teve como referência a noite de 31 de julho para 1º de agosto de 2010
  (Metodologia do Censo Demográfico 2010, p. 44), e as estimativas para o TCU têm
  referência em 1º de julho (Estimativas para o TCU, p. 1 e p. 9), como registra o
  [perfil](../sources/ibge_populacao.md#datas-e-geografia).
- Para o censo 2022, a biblioteca grava 2022-08-01 com a nota "noite de 31/07/2022 para
  01/08/2022" (`src/omnisus/sources/ibge/products.py`); a página do IBGE não foi
  conferida e a questão está em aberto no
  [perfil](../sources/ibge_populacao.md#em-aberto).
- A RIPSA ajusta as populações ao meio do ano, 1º de julho, e usa nos anos censitários a
  data de referência de cada censo (RIPSA 2008, p. 58).
- As estimativas para o TCU não formam uma série temporal consistente
  (Estimativas para o TCU, p. 9).
- Cada importação é uma nova publicação, e a visão `ibge_populacao` falha quando um
  município e ano têm duas publicações
  (`src/omnisus/sources/ibge/importers/pop.py`, `import_pop_year`). Por isso o
  notebook consulta `ibge_population_manifest` antes de importar
  (`notebooks/ibge_populacao.py`): mantenha uma edição por município e ano.

## Conferir o código do município antes de juntar

O IBGE usa 7 dígitos (`src/omnisus/data/dicionarios/ibge_populacao.yaml`, padrão de
`codigo_ibge`); os códigos das bases do DATASUS podem vir com 6: o SIH e o SINAN os
declaram com 6 caracteres (tabela acima), e o `codmunres` do SIM de Roraima 2022 veio
com 6 na validação
([relatório, §4.1](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)).
O notebook da população conta os dígitos dos dois lados antes de juntar
(`notebooks/ibge_populacao.py`, consultas `digitos_codigo_ibge` e
`digitos_codmunres_sim`):

```sql
SELECT length(codigo_ibge) AS digitos, count(*) AS municipios
FROM lake.ibge_populacao WHERE ano = ? GROUP BY ALL
```

```sql
SELECT length(trim(CAST(codmunres AS VARCHAR))) AS digitos, count(*) AS obitos
FROM lake.sim_obitos WHERE ano = ? GROUP BY ALL
```

Na validação de 2026-09-13, com o censo 2022 e o SIM de Roraima 2022
([relatório, §4.1](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)):

| Consulta | Dígitos | Contagem |
| --- | --- | --- |
| `digitos_codigo_ibge` | 7 | 5570 municípios |
| `digitos_codmunres_sim` | 6 | 3246 óbitos |

O documento do SIM declara `codmunres` com 7 caracteres (Estrutura do SIM 2025, p. 3),
mas os 3246 registros tinham 6. Por isso a junção compara os 6 primeiros dígitos, com
`sus.municipality_join_key` / `sus.municipality_join_key_sql` — a importação não
ajusta o comprimento dos códigos
([perfil do SIM](../sources/sim_obitos.md#datas-e-geografia)); confira os seus dados,
ano a ano, antes de supor o mesmo formato.

## Exemplo completo: óbitos por 100 mil habitantes, RR 2022

A consulta `obitos_por_100_mil` do notebook da população
(`notebooks/ibge_populacao.py`). Os parâmetros são, em ordem, o ano dos óbitos,
o ano da população e o código IBGE da UF (`'14'` para Roraima):

```python
import omnisus as sus

mun_obito = sus.municipality_join_key_sql("codmunres")
mun_pop = sus.municipality_join_key_sql("codigo_ibge")
sql = f"""
WITH obitos AS (
    SELECT {mun_obito} AS municipio,
           count(*) AS obitos
    FROM lake.sim_obitos WHERE ano = ? GROUP BY ALL
), populacao AS (
    SELECT {mun_pop} AS municipio, populacao
    FROM lake.ibge_populacao WHERE ano = ? AND left(codigo_ibge, 2) = ?
)
SELECT municipio, obitos, populacao,
       round(100000.0 * obitos / populacao, 1) AS obitos_por_100_mil
FROM populacao JOIN obitos USING (municipio)
ORDER BY municipio
"""
```

`municipality_join_key_sql("codmunres")` gera
`left(trim(CAST("codmunres" AS VARCHAR)), 6)`. Em Python,
`sus.municipality_join_key("1400100")` devolve `"140010"`. Não complete 6
dígitos para 7: isso inventaria o dígito verificador.

Para ler o resultado com um snapshot fixo, com `sql` guardando a consulta acima:

```python
import omnisus as sus

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
with sus.LakeReader(alvo) as leitor:
    snapshot_id = leitor.snapshots()[-1]["snapshot_id"]
with sus.LakeReader(alvo, snapshot_id=snapshot_id) as leitor:
    taxa = leitor.connect().execute(sql, [2022, 2022, "14"]).pl()
```

### Cuidados

- **Só entram os arquivos do SIM que estão no lake.** A consulta filtra os óbitos pelo
  ano e agrupa pelo município de residência, sem filtrar a UF do arquivo; a restrição a
  Roraima vem da população. Não está estabelecido se um arquivo `DOUFAAAA` reúne
  óbitos de residentes na UF ou óbitos ocorridos nela
  ([perfil do SIM, Em aberto](../sources/sim_obitos.md#em-aberto)). Cuidado deste guia:
  se óbitos de residentes de Roraima estiverem nos arquivos de outras UFs, eles só
  entram na taxa quando esses arquivos forem importados. A consulta
  `residencia_e_ocorrencia` do notebook do SIM compara as UFs de residência e de
  ocorrência (`notebooks/sim_obitos.py`).
- **O ano vem do nome do arquivo.** As colunas `ano` e `uf` do SIM vêm de `DORR2022.dbc`,
  não de `dtobito` ([perfil do SIM](../sources/sim_obitos.md#datas-e-geografia)). Na
  validação, nenhum registro com data interpretável caiu fora de 2022
  ([relatório, §4.2](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)).
- **Óbitos fetais.** Os 3246 registros de Roraima 2022 tinham `tipobito = '2'`, não
  fetal ([relatório, §4.2](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md));
  confira `tipobito` nos seus dados antes de comparar com outra taxa.
- **Data de referência e ano calendário.** O numerador da taxa bruta conta os óbitos
  do ano considerado (RIPSA 2008, p. 84); a população do censo refere-se a uma única data, gravada pela biblioteca como
  2022-08-01 e ainda não conferida na página do IBGE
  ([perfil da população, Em aberto](../sources/ibge_populacao.md#em-aberto)). A RIPSA
  usa a data de referência do censo nos anos censitários (RIPSA 2008, p. 58). Cuidado
  deste guia: declare no estudo qual edição e qual data de referência usou.
- **Poucos eventos.** A RIPSA aponta flutuações em áreas com poucos eventos e
  recomenda médias trienais (RIPSA 2008, p. 84). Na tabela abaixo, 5 dos 15 municípios
  têm menos de 60 óbitos.
- **Taxa bruta não compara populações diferentes.** A taxa bruta é influenciada pela
  estrutura da população por idade e sexo, e comparações entre populações de
  composição distinta exigem padronização (RIPSA 2008, p. 84). Esta consulta não
  padroniza.
- **Sub-registro.** A consulta usa os óbitos informados, sem a verificação dos 80%
  descrita pela RIPSA (RIPSA 2008, p. 84).

### Resultado

Roraima, 2022: SIM `DORR2022.dbc` (3246 óbitos) e censo 2022 (agregado 4714), na
validação de 2026-09-13
([relatório, §2 e §4.1](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)).

| municipio | obitos | populacao | obitos_por_100_mil |
| --- | --- | --- | --- |
| 140002 | 92 | 13927 | 660,6 |
| 140005 | 178 | 21096 | 843,8 |
| 140010 | 2163 | 413486 | 523,1 |
| 140015 | 77 | 13923 | 553,0 |
| 140017 | 86 | 18682 | 460,3 |
| 140020 | 98 | 20957 | 467,6 |
| 140023 | 37 | 10656 | 347,2 |
| 140028 | 27 | 10023 | 269,4 |
| 140030 | 89 | 18095 | 491,8 |
| 140040 | 56 | 13986 | 400,4 |
| 140045 | 92 | 19305 | 476,6 |
| 140047 | 129 | 32647 | 395,1 |
| 140050 | 30 | 8858 | 338,7 |
| 140060 | 24 | 7315 | 328,1 |
| 140070 | 68 | 13751 | 494,5 |

## Fontes

- Rede Interagencial de Informações para a Saúde (RIPSA). *Indicadores básicos para a
  saúde no Brasil: conceitos e aplicações*, 2ª ed., 2008:
  <http://tabnet.datasus.gov.br/tabdata/livroidb/2ed/indicadores.pdf> — baixado em
  2026-09-13; 1.775.528 bytes; SHA-256
  `c382ed400e1e686007c64230c35fe7c41c129a4cb876db274ec81e451cfef8d0`. Lidas as fichas
  "População total" (A.1, p. 58), "Taxa bruta de mortalidade" (A.10, p. 84) e
  "Proporção de nascidos vivos de baixo peso ao nascer" (D.16, p. 218); os números de
  página são os impressos.
- Os documentos do DATASUS e do IBGE citados nas seções de município e de população
  (Estrutura do SIM 2025, Estrutura do SINASC para CD, Informe SIH 2016-03, Dicionário
  Notificação Individual v5, Metodologia do Censo Demográfico 2010, Estimativas para o
  TCU) estão listados, com endereço e SHA-256, na seção Fontes de cada perfil:
  [SIM](../sources/sim_obitos.md#fontes),
  [SINASC](../sources/sinasc_nascidos_vivos.md#fontes),
  [SIH](../sources/sih_aih_reduzida.md#fontes),
  [SINAN Chagas](../sources/sinan_chagas.md#fontes) e
  [população IBGE](../sources/ibge_populacao.md#fontes).
- Validação de ponta a ponta dos notebooks, 2026-09-13:
  [evidence/2026-09-13-guia-pesquisador-validacao.md](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md).
