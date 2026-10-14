# Vocabulários: municípios, CID-10, ocupações, países e SIGTAP

## Em uma frase

Tabelas de referência publicadas pelo próprio DATASUS, com o SHA-256 de cada arquivo de
origem, para você juntar aos microdados quando quiser. Nada é juntado na importação.

## O que vem pronto

`omnisus init` (ou `omnisus lake update-auxiliares`) carrega cinco tabelas do zip
empacotado. Todas vêm de `ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/TABELAS/`,
exceto a CBO 2002 e os blocos da CID-10, que vêm de `CBO2002.CNV` e `CID10-grup_d.cnv` em
`SIM/CID10/TAB/OBITOS_CID10_TAB.zip`. O
`manifest.json` do zip lista as linhas e o SHA-256 de cada fonte, e cada fonte está em
`src/omnisus/data/dicionarios/sources/registry.json`.

| Tabela | Fonte | Linhas | Chave |
| --- | --- | ---: | --- |
| `aux_uf` | `TABUF.DBF` | 27 | `codigo_ibge` (2 dígitos) |
| `aux_municipios` | `CADMUN.DBF` | 5.652 | `codigo_ibge` (7 dígitos); `codigo_6` também é único |
| `aux_cid10` | `CID10.DBF` + `CIDCAP10.DBF` + `CID10-grup_d.cnv` | 14.257 | `codigo` sem ponto (`B571`) |
| `aux_ocupacoes` | `CBO2002.CNV` + `TABOCUP.DBF` | 2.458 + 3.564 | `(esquema, codigo)` só em `cbo2002` |
| `aux_paises` | `TABPAIS.DBF` | 264 | nenhuma: 3 códigos têm dois nomes |

## Juntar um campo à sua tabela

O dicionário de cada base declara a referência do campo (`foreignKeys`). Peça o SQL da
junção em vez de escrevê-lo:

```python
import omnisus as sus

join = sus.reference_join_sql("sim_obitos", "causabas", alias="d")
sql = f"SELECT d.causabas, ref_causabas.descricao FROM lake.sim_obitos AS d {join}"
```

O resultado é um `LEFT JOIN` para `ref_<campo>`. Onde a referência depende do ano, o
dicionário traz a condição (`x-join-rule`) e o SQL já a inclui: `ocup` do SIM só junta à
CBO 2002 a partir de 2006.

Um teste junta cada referência declarada sobre os arquivos reais de exemplo e registra o
que não resolve (`tests/unit/test_references.py`).

## Armadilhas

- **Municípios com 6 dígitos.** SIM, SINASC, SIH e CNES gravam o código sem o dígito
  verificador; as referências apontam para `aux_municipios.codigo_6`.
- **CADMUN é de 2011** (data do arquivo no servidor). Municípios instalados depois não
  estão lá: no exemplo do SIM de Roraima de 2023, `codmunnatu` `150475` (Mojuí dos
  Campos, PA) não resolve.
- **Coordenadas nulas em 91 municípios.** O CADMUN grava 0 e 0 nas linhas de ignorado
  (27), transferidos (60) e em 4 ativos; o lake guarda nulo, porque 0°, 0° fica no
  Atlântico.
- **Nomes de UF sem acento** (`RONDONIA`), como o `TABUF.DBF` grava. A região da UF não
  vem: o DATASUS não a publica nesses arquivos.
- **Ocupação antes de 2006.** De 1996 a 2005 o SIM grava cinco caracteres, os três
  dígitos da `TABOCUP` seguidos de `00`. A `TABOCUP` lista vários títulos por código
  (383 códigos, 3.564 títulos), e o `OCUPA.CNV` do TabWin tem os mesmos títulos. Não há
  tabela oficial com um rótulo por código, então não há junção para esses anos; os
  títulos estão em `aux_ocupacoes` com `esquema = 'tabocup'`.
- **Campos com vários CID-10.** `linhaa`–`linhad` do SIM (`*J189*A419`) e `codanomal` do
  SINASC (`Q248Q659Q789`) não são um código só e não declaram referência.
- **`0000` no SIH.** `diag_secun`, `cid_asso` e `cid_morte` gravam `0000` quando não há
  causa; não é um código CID-10.
- **`0000` no SIA.** O `DBF/S_CID.DBF` do `TAB_SIA.zip` rotula o `0000` "CID NAO
  INFORMADO"; não é um código CID-10 e fica sem rótulo no lake. No censo (PA de RR, AQ e
  AR de AL, um arquivo por mês de 2008-01 a 2026-07) ele é a maior parte dos valores
  preenchidos: no PA, 5.384.529 de 6.871.461 em `pa_cidpri`, 6.838.396 de 6.871.461 em
  `pa_cidsec` e 6.690.279 de 6.709.796 em `pa_cidcas`; na AQ, 708.236 de 719.061 em
  `ap_cidsec` e 718.881 em `ap_cidcas`; na AR, 48.786 de 48.911 em `ap_cidsec` e 48.906
  em `ap_cidcas`. Uma junção com a `aux_cid10` deixa essas linhas sem nome de doença.
  `pa_cidcas` também fica em branco (161.665 linhas). `ap_cidpri` da AQ e da AR está
  preenchido em toda linha do censo e não tem `0000`; os campos `aq_*` e `ar_*` ficam em
  branco em parte das linhas e também não têm `0000`. A mesma tabela chama de "CID NÃO
  IDENTIFICADO" alguns códigos de 4 caracteres que o PA publica e que não estão na
  `aux_cid10`, como `N182` e `N185`. `M881` (5 linhas) e `Q350` (3) têm rótulo próprio
  no S_CID, mas também não têm linha na `aux_cid10` e ficam sem rótulo no lake
  (`evidence/2026-10-07-sia-cid-widths/values.csv`).
- **Descrições abreviadas.** `aux_cid10.descricao` é o texto de `CID10.DBF`, que
  abrevia (`Form aguda doenc de Chagas s/compr cardiaco`).

## CID-9 e CID-10 nos sistemas do SUS

A `aux_cid10` só serve aos meses gravados em CID-10. Um código da CID-9 tem só algarismos
(`4109`); um da CID-10 começa com letra (`I219`). O que os arquivos mostram:

| Sistema | CID-9 | CID-10 | Como aparece nos arquivos |
| --- | --- | --- | --- |
| SIM | `sim_obitos_cid9`, 1979–1995 | `sim_obitos`, 1996 em diante | Diretórios separados, `SIM/CID9/DORES` e `SIM/CID10/DORES`. Na CID-9, `causabas` tem 4 caracteres só de algarismos, com `X` no lugar do quarto quando o código é uma categoria (`436X`) |
| SIH, `RD` | `sih_aih_reduzida_1992_2007`, 1992-01 a 1997-12 | a mesma linha de 1998-01 a 2007-12; `sih_aih_reduzida` de 2008-01 em diante | Mesmo diretório, `SIHSUS/199201_200712`. `DIAG_PRINC` tem 6 caracteres até 1997-12 e 4 a partir de 1998-01; `DIAG_SEC` (6, só em 1997) dá lugar a `DIAG_SECUN` (4) |
| SIH, `RJ` e `SP` | — | `sih_aih_rejeitada` e `sih_servicos_profissionais`, 2008-01 em diante | Só há essas linhas a partir de 2008-01; nos exemplos de 2024-01, `diag_princ` e `sp_cidpri` têm letra |
| SIA, `PA` | nenhum código no exemplo de 2007-12 | `sia_producao_ambulatorial_1994_2007` (exemplo de 2007-12) e `sia_producao_ambulatorial` | `pa_cidpri` grava `0` (um caractere) no exemplo de 2007-12 e `0000` no de 2024-01 |
| SINASC | — | `sinasc_nascidos_vivos` (`codanomal`, exemplo de 2022) | `sinasc_1994_1995` não tem campo de CID |
| SINAN | — | `id_agravo` nos exemplos de 2020, 2023 e 2026 | um código por arquivo (`A169`, `B571`, `A309`) |

As evidências:

- **SIM.** As listagens `tests/fixtures/listings/sim_cid9_dores.txt.gz` (`DOR` + UF + 79 a
  95) e `sim_cid10_dores.txt.gz` (de `DOAC1996.dbc` em diante). No exemplo
  `DORRR95.DBC` (`tests/fixtures/dbc/sim_cid9_rr_1995_mini.dbc`), os 967 `causabas` têm
  4 caracteres, nenhum com letra além do `X` (236). O `Obito_1979_95_CID-09.DEF` do
  TabWin liga `CAUSABAS` a `CAUSACAP.CNV` e `CAUSABR.CNV`
  (`src/omnisus/data/dicionarios/sources/cnv/sim/`).
- **SIH, a troca de 1998.** O censo `evidence/2026-10-01-rd-1992-2007-layouts/census.csv`
  dá `DIAG_PRINC C6.0` em todos os arquivos de 1992-01 a 1997-12 e `C4.0` de 1998-01 em
  diante, em RR, SP e MG (`RDRR9712` e `RDRR9801`, por exemplo). Nos exemplos de 1994-12
  e 1997-09 (`sih_rd_rr_1994_12_mini.dbc`, `sih_rd_rr_1997_09_mini.dbc`), todo
  `diag_princ` tem 6 algarismos (`065099`), e `diag_sec` grava `000000` em 784 das 794
  linhas. Nos de 2004-07 e 2007-12, `diag_princ` tem letra em todas as linhas (`O800`).
  Os valores de 1998 a 2003 não foram lidos aqui.
- **SIH, o que o TabWin faz.** O `RD.DEF` dos três pacotes da era 1992–2007
  (`sources/cnv/sih_199201_199712/`, `sih_199801_200307/`, `sih_200308_200712/`) liga
  `DIAG_PRINC` às tabelas da CID-10 (`CID10CAP.CNV`, `CID10_3D.CNV`...) e às da CID-9
  (`CID9_CAP.CNV`, `CID9_3D.CNV`...), `DIAG_SEC` só às da CID-9 e `DIAG_SECUN` só às da
  CID-10. O DEF não separa as eras: quem separa é a largura do campo.
- **SIA.** No exemplo `PARR0712.dbc` (`sia_pa_rr_2007_12_mini.dbc`), `pa_cidpri` está
  preenchido em 15.945 linhas: 14.123 com `0` e as outras com letra (`M800`, `N180`);
  nenhuma tem um código só de algarismos com 3 ou 4 posições. No exemplo `PARR2401.dbc`
  (`sia_pa_rr_2024_01_mini.dbc`), 14.540 das 21.341 linhas gravam `0000`.
- **SINASC e SINAN.** `codanomal` tem códigos `Q` no exemplo de RR de 2022
  (`sinasc_rr_2022_mini.dbc`); o primeiro ano em que o campo aparece não foi lido aqui.
  O SINAN está em `tests/fixtures/dbc/sinan_*.dbc`.

O que isso muda na análise:

- **`diag_princ` de `sih_aih_reduzida_1992_2007` mistura as duas classificações.** De
  1992 a 1997 é CID-9 e de 1998 a 2007, CID-10, na mesma coluna. Filtre por `ano` ou
  pelo comprimento do código antes de juntar à `aux_cid10`; o repositório não traz
  tabela da CID-9 nem correspondência entre as duas. O dicionário diz o mesmo no issue
  aberto `diag-princ-cid9-ate-1997` do campo.
- **Categoria com zero à esquerda.** No exemplo do SIH de 2007-12, `cid_morte` grava
  `0I64`, `0I10`, `0B24` e `0D77`, e `cid_asso`, `0I10`: a categoria de 3 caracteres
  com um `0` antes, que não junta à `aux_cid10` (issue `cid-zero-a-esquerda` dos dois
  campos).

## SIGTAP por competência

Os procedimentos do SIGTAP não vêm no zip: cada competência é um arquivo do servidor, e
você importa as que precisa.

```python
sus.available_sigtap()[-3:]      # [(2026, 7), (2026, 8), (2026, 9)]
sus.import_sigtap(years=[2024], months=[1, 2])
```

Cada competência vira uma publicação nacional mensal de `aux_sigtap_procedimentos`
(`_source_ano`, `_source_mes`), com o SHA-256 e a data do zip no servidor. `cite()` nomeia
o zip; importar de novo o mesmo zip dá `skipped`/`unchanged`. O zip é lido pelo layout que
vem dentro dele, porque o layout muda: `vl_sh`, `vl_sa` e `vl_sp` têm 10 posições em
2008-01 e 12 em 2026-09, e `qt_tempo_permanencia` não existe nos layouts antigos. Os
valores ficam inteiros como publicados; o layout não declara casas decimais.

Fonte: `ftp://ftp2.datasus.gov.br/public/sistemas/tup/downloads/`, um
`TabelaUnificada_AAAAMM[_vNNNNNNNNNN].zip` por mês desde 2008-01.
