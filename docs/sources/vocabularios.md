# Vocabulários: municípios, CID-10, ocupações, países e SIGTAP

## Em uma frase

Tabelas de referência publicadas pelo próprio DATASUS, com o SHA-256 de cada arquivo de
origem, para você juntar aos microdados quando quiser. Nada é juntado na importação.

## O que vem pronto

`omnisus init` (ou `omnisus lake update-auxiliares`) carrega cinco tabelas do zip
empacotado. Todas vêm de `ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/TABELAS/`,
exceto a CBO 2002, que vem de `CBO2002.CNV` em `SIM/CID10/TAB/OBITOS_CID10_TAB.zip`. O
`manifest.json` do zip lista as linhas e o SHA-256 de cada fonte, e cada fonte está em
`src/omnisus/data/dicionarios/sources/registry.json`.

| Tabela | Fonte | Linhas | Chave |
| --- | --- | ---: | --- |
| `aux_uf` | `TABUF.DBF` | 27 | `codigo_ibge` (2 dígitos) |
| `aux_municipios` | `CADMUN.DBF` | 5.652 | `codigo_ibge` (7 dígitos); `codigo_6` também é único |
| `aux_cid10` | `CID10.DBF` + `CIDCAP10.DBF` | 14.257 | `codigo` sem ponto (`B571`) |
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
- **Descrições abreviadas.** `aux_cid10.descricao` é o texto de `CID10.DBF`, que
  abrevia (`Form aguda doenc de Chagas s/compr cardiaco`).

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
