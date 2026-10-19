# SINAN · violência interpessoal e autoprovocada (`sinan_violencia`)

## Em uma frase

Notificações de violência interpessoal e autoprovocada do Sistema de Informação de
Agravos de Notificação (SINAN), que o DATASUS publica em um arquivo nacional por ano:
2009 a 2024 no diretório final e 2025 no preliminar (listagem de 2026-10-19).

## O que um registro representa

- Uma linha é uma notificação, não uma pessoa.
- O código do agravo é `Y09` em todas as linhas de `VIOLBR09` (39.976) e `VIOLBR23`
  (588.388), contagem de 2026-10-19.

## Datas e geografia

- `NU_ANO` (ano da notificação) é 2023 em todas as 588.388 linhas de `VIOLBR23` e 2009
  em todas as 39.976 de `VIOLBR09`. Os outros anos não foram medidos.
- `SG_UF_NOT`/`ID_MUNICIP` descrevem onde se notificou; `SG_UF`/`ID_MN_RESI`, a
  residência; `SG_UF_OCOR`/`ID_MN_OCOR`, o local da ocorrência.

## Cobertura e modalidade

- `FINAIS`: `VIOLBR09` a `VIOLBR24`; `PRELIM`: `VIOLBR25`. Um ano está em um só
  diretório, e `_source_release` diz qual.
- Registros por arquivo, lidos do cabeçalho em 2026-10-19: `VIOLBR18` 350.354,
  `VIOLBR19` 405.497, `VIOLBR20` 326.503, `VIOLBR21` 373.262, `VIOLBR22` 442.680,
  `VIOLBR23` 588.388, `VIOLBR24` 616.548 e `VIOLBR25` 688.329.
- `VIOLBR09` e `VIOLBR23` têm os mesmos 159 campos. Os outros anos não foram medidos.

## Armadilhas

- Importar um ano pede memória: em um teste de 2026-10-19, `VIOLBR23` levou o
  processo a 6,4 GB de memória residente. Importe um ano por vez.
- A idade (`nu_idade_n`) não é interpretada: nenhuma fonte de violência foi auditada
  para a regra de idade (sem `x-analytics.validated_sources`).

## Como usar

```python
import omnisus as sus

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
print(sus.available_releases("sinan_violencia", refresh=True))  # ano -> final ou prelim
escopos = sus.available("sinan_violencia", years=[2023])
relatorio = sus.import_dataset(
    "sinan_violencia", scopes=escopos, target=alvo, policy="skip_same", run_id="viol-2023"
)
```

## Dicionário

Os 159 campos de `src/omnisus/data/dicionarios/sinan_violencia.yaml` são um inventário
físico observado em `VIOLBR23.dbc`, não uma auditoria semântica. Só os campos da
notificação individual trazem rótulos, copiados de `scripts/metadados/sinan_bloco_comum.yaml`;
os campos do agravo não foram cruzados com o PDF.

## Fontes

- Dicionário de Dados, SINAN NET, Versão 5.0, Violências
  (`DIC_DADOS_NET_Violencias_v5.pdf`), Ministério da Saúde:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/via/DIC_DADOS_NET_Violencias_v5.pdf>
  (consultado em 2026-10-19; 471.910 bytes; SHA-256
  `06decac411eea652657d3efb162e3dd85453ba2f01ff0b8491bd2ddec77e6b10`). Os mesmos bytes
  estão em `Docs_TAB_SINAN/Documentação/AGRAVOS/VIOLEN_DIC_DADOS.pdf`, dentro de
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DOCS/Docs_TAB_SINAN.zip> (SHA-256
  `037e5d59597cb400c4b06c5d7a94b1d2f1daf9b59228120709816e547471a81a`).
- Dicionário de Dados, SINAN NET, Versão 5.0, Notificação Individual:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/NINDIV/DIC_DADOS_Notificacao_Individual_v5.pdf>
  (SHA-256 `b3e0561c7a2d0a83d717286e07d01ca75b0d4499a38d3b3ba2b602a4fc983004`).
- `VIOLBR23.dbc`: <ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS/VIOLBR23.dbc>
  (SHA-256 `45c042dab40de3fb57a544b606eaa23893d6818e76c0f3ea9006a2c2b664f635`).
- [Bases e argumentos](../datasets.md#sinan), página gerada do registro da biblioteca.
