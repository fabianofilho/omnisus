# SINAN · dengue (`sinan_dengue`)

## Em uma frase

Notificações de dengue do Sistema de Informação de Agravos de Notificação (SINAN), que o
DATASUS publica em um arquivo nacional por ano: 2000 a 2025 no diretório final e 2026 no
preliminar (listagem de 2026-10-19).

## O que um registro representa

- Uma linha é uma notificação, não uma pessoa nem um caso confirmado; a classificação
  final está em `CLASSI_FIN`.
- O código do agravo é `A90` em todas as linhas de `DENGBR07` (497.037), `DENGBR17`
  (239.395) e `DENGBR23` (1.645.956), contagem de 2026-10-19.

## Datas e geografia

- `NU_ANO` (ano da notificação) é o ano do arquivo na maioria das linhas, não em todas:
  em `DENGBR23`, 1.645.276 linhas trazem 2023 e 680 trazem 2024; em `DENGBR00`, 172.807
  trazem 2000, 43 trazem 1999 e 4 trazem 2001. A biblioteca confere o valor mais
  frequente (`x-identity`) e mantém as demais linhas como vieram.
- `SG_UF_NOT`/`ID_MUNICIP` descrevem onde se notificou; `SG_UF`/`ID_MN_RESI`, a
  residência.

## Cobertura e modalidade

- `FINAIS`: `DENGBR00` a `DENGBR25`; `PRELIM`: `DENGBR26`. Um ano está em um só
  diretório, e `_source_release` diz qual.
- Registros por arquivo, lidos do cabeçalho em 2026-10-19: `DENGBR18` 262.611,
  `DENGBR19` 1.546.252, `DENGBR20` 975.842, `DENGBR21` 540.049, `DENGBR22` 1.405.095,
  `DENGBR23` 1.645.956, `DENGBR24` 6.564.924, `DENGBR25` 1.643.215 e `DENGBR26`
  474.351.
- O leiaute muda ao longo da série: `DENGBR00` tem 107 campos, `DENGBR07` tem 67 e
  `DENGBR17` e `DENGBR23` têm 121. Os outros anos não foram medidos.

## Armadilhas

- `DENGBR00` a `DENGBR06` não têm a coluna `ID_AGRAVO`
  (`evidence/2026-09-12-sinan-e-dispensacao.md`, §3.3); nesses anos a identidade da
  fonte confere só o ano.
- Os anos epidêmicos são grandes. Em um teste de 2026-10-19, importar `DENGBR17`
  levou o processo a 2,8 GB de memória residente; `DENGBR24` tem 27 vezes mais
  registros. Importe um ano por vez.
- A idade (`nu_idade_n`) não é interpretada: nenhuma fonte de dengue foi auditada para a
  regra de idade (sem `x-analytics.validated_sources`).

## Como usar

```python
import omnisus as sus

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
print(sus.available_releases("sinan_dengue", refresh=True))  # ano -> final ou prelim
escopos = sus.available("sinan_dengue", years=[2017])
relatorio = sus.import_dataset(
    "sinan_dengue", scopes=escopos, target=alvo, policy="skip_same", run_id="dengue-2017"
)
```

## Dicionário

Os 121 campos de `src/omnisus/data/dicionarios/sinan_dengue.yaml` são um inventário
físico observado em `DENGBR23.dbc`, não uma auditoria semântica. Só os campos da
notificação individual trazem rótulos, copiados de `scripts/metadados/sinan_bloco_comum.yaml`;
os campos do agravo não foram cruzados com o PDF.

## Fontes

- Dicionário de dados do Sinan Online, dengue e chikungunya (`DIC_DADOS_ONLINE.pdf`),
  Ministério da Saúde:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/Dengue/DIC_DADOS_ONLINE.pdf>
  (consultado em 2026-10-19; 339.721 bytes; SHA-256
  `da262c3b9f20f242d01ee235e64c221dd97e6ad9a53d38cc94da9316bf98c4eb`). Os mesmos bytes
  estão em `Docs_TAB_SINAN/Documentação/AGRAVOS/DENGON_DIC_DADOS.pdf`, dentro de
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DOCS/Docs_TAB_SINAN.zip> (SHA-256
  `037e5d59597cb400c4b06c5d7a94b1d2f1daf9b59228120709816e547471a81a`).
- Dicionário de Dados, SINAN NET, Versão 5.0, Notificação Individual:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/NINDIV/DIC_DADOS_Notificacao_Individual_v5.pdf>
  (SHA-256 `b3e0561c7a2d0a83d717286e07d01ca75b0d4499a38d3b3ba2b602a4fc983004`).
- `DENGBR23.dbc`: <ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS/DENGBR23.dbc>
  (SHA-256 `c0e7f95ef832c09793adb21fe9a5b7bdfbb5b9a0bb6c8561ef31b7197cb1cf90`).
- [Bases e argumentos](../datasets.md#sinan), página gerada do registro da biblioteca.
