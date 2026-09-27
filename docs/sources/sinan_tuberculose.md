# SINAN · tuberculose (`sinan_tuberculose`)

## Em uma frase

Notificações de tuberculose do Sistema de Informação de Agravos de Notificação (SINAN),
com diagnóstico, exames e situação de encerramento, que o DATASUS publica em um arquivo
nacional por ano: 2001 a 2019 no diretório final e 2020 a 2025 no preliminar
(listagem de 2026-09-22).

## O que um registro representa

- Uma linha é uma notificação: os campos da notificação individual seguem o Dicionário
  Notificação Individual v5, e os do agravo seguem o Dicionário de Dados de Tuberculose
  (`DICI_DADOS_NET_Tuberculose_23_07_2020.pdf`, campos 31 a 66).
- O código de transferência aparece em dois campos, mas as páginas citadas não afirmam
  que ele abre uma nova notificação: `TRATAMENTO` 5 = Transferência (Tipo de Entrada,
  p. 1) e `SITUA_ENCE` 5 = Transferência (Situação de Encerramento; preenchida com essa
  opção, habilita o campo 63 "Se transferência", pp. 19–20).
- O código do agravo é `A169` na maioria das linhas; em `TUBEBR20` 1.513 das 86.160
  linhas trazem `A16.` (contagem de 2026-09-22).

## Datas e geografia

- O ano do arquivo segue o diagnóstico: em `TUBEBR20`, `DT_DIAG` cai em 2020 nas 86.160
  linhas, enquanto `NU_ANO` (ano da notificação) é 2020 em 82.778 e vai até 2026 nas
  demais. Nenhum documento oficial afirma a regra; é observação dos arquivos. O mesmo vale
  para `TUBEBR01` (`DT_DIAG` em 2001 nas 87.265 linhas;
  `evidence/2026-09-22-tubebr01/README.md`) e para `TUBEBR25` (`DT_DIAG` em 2025
  nas 112.482 linhas; `evidence/2026-09-12-sinan-e-dispensacao.md`).
- `SG_UF_NOT`/`ID_MUNICIP` descrevem onde se notificou; `SG_UF`/`ID_MN_RESI`, a residência;
  `SG_UF_AT`/`ID_MUNIC_A`, a unidade de acompanhamento atual.

## Cobertura e modalidade

- `FINAIS`: `TUBEBR01` a `TUBEBR19`; `PRELIM`: `TUBEBR20` a `TUBEBR25`. Um ano está em um
  só diretório, e `_source_release` diz qual.
- O ano do arquivo é o ano de `DT_DIAG`: medido em 2026-09-22 em todos os registros de
  `TUBEBR01` (87.265), `TUBEBR20` (86.160) e `TUBEBR25` (112.482), com os SHA-256
  `bd9071632d7e…`, `9ecf487348b6…` e `b5aa111e8dcd…`. Nenhum documento oficial o afirma, e
  os outros anos não foram medidos.
- Dois leiautes: 2001–2018 têm 97 campos e 2019–2025 têm 94. Os três a mais
  (`EXTRAPUL_O`, `AGRAVOUTDE`, `OUTRAS_DES`) são texto livre e entram no lake como vêm.

## Armadilhas

- `TUBEBR01` (2001) veio migrado do Sinan Windows: `MIGRADO_W` = 1 em 87.211 das 87.265
  linhas, e 32 campos codificados trazem `0`, código que a página de cada um não lista
  (`CS_RACA` em 72.165 linhas). Os demais arquivos de 2002–2018 não foram medidos;
  deles só se sabe que têm o mesmo leiaute de 97 campos.
- `DOENCA_TRA` não é decodificado: o arquivo de definição do TabWin a marca "variável
  utilizada até versão Sinan 4.2" e no arquivo completo `TUBEBR20` ela traz 0 a 6
  (7 registros com 6).
- `POP_SAUDE` e `POP_IMIG` trazem `3` (304 e 51 linhas no recorte de 3.000 de
  `TUBEBR20`), código fora da lista 1, 2, 9 do dicionário (pp. 2–3).
- `SITUA_ENCE` tem dois caracteres no arquivo; 10 = Abandono Primário (pp. 19–20).
- A idade (`nu_idade_n`) só é interpretada para o `TUBEBR20` preliminar auditado
  (`x-analytics.validated_sources`).

## Como usar

```python
import omnisus as sus

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
print(sus.available_releases("sinan_tuberculose", refresh=True))  # ano -> final ou prelim
escopos = sus.available("sinan_tuberculose", years=[2020])
relatorio = sus.import_dataset(
    "sinan_tuberculose", scopes=escopos, target=alvo, policy="skip_same", run_id="tb-2020"
)
```

Passo a passo com os agravos do SINAN:
[notebooks/sinan.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinan.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py).

## Fontes

- Dicionário de Dados – SINAN NET – Versão 5.0, Tuberculose
  (`DICI_DADOS_NET_Tuberculose_23_07_2020.pdf`), Ministério da Saúde:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/Tuberculose/DICI_DADOS_NET_Tuberculose_23_07_2020.pdf>
  — consultado em 2026-09-22; 328.708 bytes; SHA-256
  `0e0aac57f975343917552225cfd920c88f096f99cba46968c5bca6f46c291b08`. Registro:
  `sinan-0e0aac57f975`.
- Dicionário de Dados – SINAN NET – Versão 5.0, Notificação Individual:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/NINDIV/DIC_DADOS_Notificacao_Individual_v5.pdf>
  — SHA-256 `b3e0561c7a2d0a83d717286e07d01ca75b0d4499a38d3b3ba2b602a4fc983004`.
- `TAB_SINANNET.zip`, `TuberculNET5_0.def`:
  <ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/AUXILIAR/TAB_SINANNET.zip> — SHA-256
  `cad66ee387810de6f7b00560d8e827f2970d016cf363787523691d4f5454c8be`.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).
