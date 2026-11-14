# CO_STATUS do tb_municip.dbf da base territorial: 2026-10-31

O build da `aux_municipios` lê seis municípios do `tb_municip.dbf` e só os aceita se o
`CO_STATUS` estiver no enum do dicionário (`ATIVO`, `EXTIN`, `IGNOR`, `TRANS`). Este registro
conta os seis valores que a base grava e diz por que dois deles ficam de fora.

## Arquivos lidos

| Arquivo | SHA-256 |
| --- | --- |
| `territorio/tabelas/2026/06-base_territorial_jun26.zip` (registrado, `base-territorial-f6e06a674cf7`) | `f6e06a674cf7c83693df6a230b2068ea2e257c27970050ca320353e42688316a` |
| `tb_municip.dbf` desse zip (1.185.941 bytes) | `a99e4594fcfa824212536b589cf6ebe2adec9a9f3c18047b88fb836a6fce20f3` |

## Contagem

Lido com `dbfread2` em cp1252, coluna `CO_STATUS` dos 5.725 registros:

| CO_STATUS | Registros |
| --- | ---: |
| `ATIVO` | 5.571 |
| `REG ADM` | 63 |
| `TRANS` | 60 |
| `IGNR` | 27 |
| `EXTIN` | 2 |
| `IGNOR` | 2 |

O `SITUACAO` do `CADMUN.DBF` só tem `ATIVO`, `EXTIN`, `IGNOR` e `TRANS`: a base escreve
dois valores a mais (`REG ADM`, `IGNR`). Os seis municípios que entram na tabela são
`ATIVO`. `DT_INSTAL` é 2013 em cinco e 2009 em Nazária (`220672`).

## Os seis municípios (conferido em 2026-11-09)

Lidos do mesmo `tb_municip.dbf` (SHA-256 acima), com `dbfread2` em cp1252, seis dos 26 campos
de cada registro, sem mudança:

| CO_MUNICIP | DS_NOME | CO_STATUS | DT_INSTAL | NU_ALTITUD | NU_AREA |
| --- | --- | --- | --- | --- | --- |
| `150475` | Mojui Dos Campos | `ATIVO` | 2013 | 84 | 4988,236 |
| `220672` | Nazaria | `ATIVO` | 2009 | 72 | vazio |
| `421265` | Pescaria Brava | `ATIVO` | 2013 | 13 | vazio |
| `422000` | Balneario Rincao | `ATIVO` | 2013 | 44 | vazio |
| `431454` | Pinto Bandeira | `ATIVO` | 2013 | 638 | 104,821 |
| `500627` | Paraiso Das Aguas | `ATIVO` | 2013 | 608 | 5061,433 |

`area` é nula nos três de `NU_AREA` vazio. A tabela tem mais quatro nulos em `area`, vindos
do CADMUN: `220095`, `500390`, `510452` e `510454`. No `CADMUN.DBF` registrado
(`sim-tabelas-cadmun-1bdd0ac2bdae`, baixado de novo em 2026-11-14 com o mesmo SHA-256), o
campo `AREA` desses quatro registros é só espaços. As seis altitudes são inteiras; o build para
diante de uma que não seja. O build também só aceita o `CO_STATUS` do enum do dicionário
(`ATIVO`, `EXTIN`, `IGNOR`, `TRANS`): `REG ADM` e `IGNR`, que a base grava, o param.

## Os 26 campos de Nazária e Pinto Bandeira (conferido em 2026-11-14)

O teste do build transcreve estes dois registros inteiros (`NAZARIA` e `PINTO_BANDEIRA` em
`tests/unit/scripts/test_build_bootstrap_zip.py`). Lidos do mesmo `tb_municip.dbf` (zip
baixado de novo em 2026-11-14, mesmo SHA-256), com `dbfread2` em cp1252: os 26 campos batem,
um a um, com os dois literais do teste.

| Campo | `220672` | `431454` |
| --- | --- | --- |
| `CO_MUNICIP` | `220672` | `431454` |
| `CO_MUNICDV` | `2206720` | `4314548` |
| `CO_STATUS` | `ATIVO` | `ATIVO` |
| `CO_TIPO` | `ATIVO` | `ATIVO` |
| `DS_NOME` | `Nazaria` | `Pinto Bandeira` |
| `UF` | `PI` | `RS` |
| `MACRORREGI` | `2208` | `4310` |
| `DS_NOMEPAD` | `NAZARIA` | `PINTO BANDEIRA` |
| `DS_OBSERV` | `S` | `S` |
| `CO_REGIAO` | `2` | `4` |
| `CO_UF` | `22` | `43` |
| `CO_ALTER` | vazio | vazio |
| `CO_ALTERDV` | vazio | vazio |
| `IN_CAPITAL` | `N` | `N` |
| `IN_AMAZLEG` | `N` | `N` |
| `IN_SEMIAR` | vazio | vazio |
| `IN_FRONTZN` | `N` | `N` |
| `DT_INSTAL` | `2009` | `2013` |
| `DT_EXTIN` | vazio | vazio |
| `CO_SUCESS` | vazio | vazio |
| `NU_ORDEM` | vazio | vazio |
| `NU_ORDMAP` | vazio | vazio |
| `NU_LATITUD` | `-5,346925` | `-29,09777778` |
| `NU_LONGIT` | `-42,8140484695768` | `-51,45027778` |
| `NU_ALTITUD` | `72` | `638` |
| `NU_AREA` | vazio | `104,821` |
