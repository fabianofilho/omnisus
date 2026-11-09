# CPF em nome de pessoa jurídica no tbEstabelecimento: 2026-11-09

O import do FTP só guarda nome de linha com `TP_PFPJ` 3 (pessoa jurídica). A revisão do #150
pediu medir se alguma dessas linhas traz um CPF, o de empresário individual por exemplo, na
razão social ou no nome fantasia. Esta medição não imprime nenhum nome nem CPF.

## Arquivo lido

| Arquivo | SHA-256 |
| --- | --- |
| `ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_202312.ZIP` (MDTM 2024-01-12T21:27) | `b7933bb5af98e594d3b39652d28c1129b03844c2715594138cb264cc8d51bd42` |

Membro `tbEstabelecimento202312.csv`, lido com `csv` em `latin-1`, separador `;`.

## Método

Um CPF é uma sequência de 11 dígitos, com ou sem pontos e traço, sem dígito colado antes ou
depois, cujos dois dígitos verificadores batem (módulo 11) e que não é um só dígito
repetido. A mesma regra está em `omnisus.sources.cnes.importers.master._contains_cpf`.

## Contagem

| | Linhas |
| --- | ---: |
| Total | 509.875 |
| `TP_PFPJ` 3 | 354.732 |
| `TP_PFPJ` 1 | 155.143 |
| Outro valor | 0 |
| `TP_PFPJ` 3 com CPF válido em algum nome | 546 |

Ocorrências: 541 em `NO_RAZAO_SOCIAL` e 21 em `NO_FANTASIA` (uma linha pode ter as duas),
todas só com dígitos.

Por `CO_NATUREZA_JUR` das 546 linhas:

| CO_NATUREZA_JUR | Linhas com CPF | Linhas `TP_PFPJ` 3 dessa natureza |
| --- | ---: | ---: |
| `2135` (empresário individual) | 486 | 23.976 |
| `2062` (sociedade empresária limitada) | 57 | 148.478 |
| `2305` | 3 | 2.931 |

## Efeito no import

`read_base` sobre este arquivo: 354.186 registros com nome; 155.689 códigos sem nome
público (155.143 de pessoa física e 546 com CPF no nome); nenhum `TP_PFPJ` desconhecido e
nenhuma linha sem nome.
