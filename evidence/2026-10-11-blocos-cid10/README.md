# Blocos da CID-10 para a `aux_cid10` — 2026-10-11

A `aux_cid10` 2.1.0 ganha `bloco` e `bloco_descricao` (issue #103). Este registro diz de
onde vêm os blocos, que outras listas oficiais existem e onde elas divergem.

## O que o servidor do DATASUS publica

Listagem de `ftp.datasus.gov.br` em 2026-10-11:

- `/dissemin/publicos/SIM/CID10/TABELAS/`: `CADMUN.DBF`, `CADMUN.xls`, `CID10.DBF`,
  `CIDCAP10.DBF`, `Tabela-de-Municipios-informacoes.pdf`, `TABOCUP.DBF`, `TABPAIS.DBF`,
  `TABUF.DBF`. Nenhuma tabela de blocos.
- `/dissemin/publicos/SIM/CID10/DOCS/Docs_Tabs_CID10.zip` traz só `TABELAS/CID10.DBF` e
  `TABELAS/CIDCAP10.DBF`.
- `/dissemin/publicos/SIM/CID10/TAB/` tem `OBITOS_CID10_TAB.zip` (já no registro de fontes,
  `sim-tab-bb1c9f02668e`) e `CNVS_CID10_v2019.rar`. Os dois trazem `CID10-grup_d.cnv`,
  os mesmos bytes: em `OBITOS_CID10_TAB/tabdo/`, `tabinf/` e `tabmat/` do zip, e em
  `CNVS CID10 v2019/` do rar.
- `/dissemin/publicos/SIM/` tem `CID9` (1979–1995) e `CID10` (a partir de 1996), além de
  `PRELIM`. Não há pasta nem tabela da CID-11.

`CID10-grup_d.cnv` é uma tabela de conversão do TabWin com 243 grupos, cada um uma faixa
de categorias (`A00-A09`). O DEF de óbitos do zip a liga ao campo da causa básica:
`xCausa(AGRUP*), CAUSABAS, 1, CID10-grup_d.cnv`. O cabeçalho `243 3 L` diz que o TabWin
compara os três primeiros caracteres do código (TabWin.pdf, p. 90).

## Outras listas oficiais lidas

- **OMS, CID-10 versão 2019**: `https://icd.who.int/browse10/2019/en`, filhos de cada
  capítulo e de cada bloco pelo endpoint `JsonGetChildrenConcepts?ConceptId=<id>`. A
  hierarquia tem até três níveis (`C00-C97` ⊃ `C00-C75` ⊃ `C00-C14`).
- **CBCD/DATASUS, "Versão 2008"**: `http://www2.datasus.gov.br/cid10/V2008/downloads/CID10CSV.zip`,
  arquivo `CID-10-GRUPOS.CSV` (datado de 2007-10-01 no zip), 275 grupos com os
  aninhados.

`blocos.csv` tem uma linha por faixa de cada fonte: `fonte`, `faixa` e, nas faixas da
OMS que estão dentro de outra, `dentro_de`. Só as faixas, sem as descrições.

## Onde divergem

Faixas do CNV que não estão na lista da OMS, em nenhum nível:

- `A90-A99`: a OMS 2019 tirou `A90` e `A91` (dengue) e o bloco virou `A92-A99`; a
  `CID10.DBF` do DATASUS ainda tem `A90` e `A91`.
- `U04-U12`, `U80-U89`, `U92-U92` e `U99-U99`: a OMS 2019 tem `U00-U49` e `U82-U85`.

Faixas do CNV que não estão na CBCD 2008: `B95-B98`, `G10-G14` e `K55-K64` (a CBCD tem
`B95-B97`, `G10-G13` e `K55-K63`), `U04-U12` (a CBCD tem `U04-U04`) e `U92-U92`.

O CNV usa níveis diferentes da hierarquia da OMS conforme o capítulo: o mais fino em C,
W e X (`C00-C14`, `W00-W19`), o do meio em V (`V01-V99`) e o de cima em M e T
(`M00-M25`, `T20-T32`), onde a OMS tem sub-blocos.

`O93` e `O930` a `O939` ("Morte materna associada a ...") estão na `CID10.DBF`, mas
não estão em nenhum grupo do CNV, que vai de `O85-O92` a `O94-O99`, nem na OMS 2019 ou
na CBCD 2008, que têm os mesmos blocos. Na `aux_cid10` esses 11 códigos ficam sem bloco.

## Decisão

Os blocos vêm do CNV: é o agrupamento que o DATASUS usa para tabular o SIM e o único dos
três que acompanha os códigos da `CID10.DBF` de hoje. Cada código da `aux_cid10` cai em
no máximo um grupo, e cada grupo fica num só capítulo (`scripts/build_bootstrap_zip.py`
para se não for assim; `tests/unit/lake/test_bootstrap.py` confere). As descrições são
as do CNV, abreviadas como publicadas.

## SHA-256 do que foi lido

| Arquivo | SHA-256 |
| --- | --- |
| `SIM/CID10/TAB/OBITOS_CID10_TAB.zip` | `bb1c9f02668e46fe81f5ee73687abec771f616d63ff9a89460a4275e21eb5905` |
| `SIM/CID10/TAB/CNVS_CID10_v2019.rar` | `e8a7044f88bc7c3a8d7417670f849fb56a69dacecea533db3d555dce304f9d9a` |
| `CID10-grup_d.cnv` (nos dois arquivos acima) | `d105cf090e7f8e62250555c7a35c6bc2c16f8180779a30c60e63583d1b01f960` |
| `SIM/CID10/DOCS/Docs_Tabs_CID10.zip` | `e24f8cf45f5c5bae36a28cf33af97a367cbfa09966eb277c17c6782e87716ff2` |
| CBCD `CID10CSV.zip` | `84f23809275575f751255048064bbb244b0de33fd5987ab98df0f98e5f5d2c95` |
| `TabWin.pdf` (registro `tabwin-bb98cff14765`) | `bb98cff147652c55d78aa7ccf0bee213281bdacdaa28e87de684166e0b1aa173` |
| `blocos.csv` | `c580f2e354e324497b5142e647a8ac7268c851c56b368347109766fb47994e0f` |

Respostas do navegador da OMS para cada capítulo (`ConceptId=I` a `XXII`):

| Capítulo | SHA-256 |
| --- | --- |
| I | `184bb4ee0fcfc6f03b1a49ee947e462588371446b239355bb0a43fb65474c97f` |
| II | `53f764364c719a24d04c42789fcd52522e9160a7f691d37c6fd042124f54d9a5` |
| III | `0e61aa37d927205464b398c1f4c79fbf0a0cb7bb79a3426919c7221ba20946f7` |
| IV | `1648b62f3d34db8d76d896eb8e60fd7ae168e5ff547d0c396a2ad4debde48534` |
| V | `b484539fca2f1ce0ba08c03927f8db3a1176c7f1ba86742675c101ef6fa65f63` |
| VI | `0503341baf6c218ad9465469059b1e198a51cfad44e10b976554866d9e82db63` |
| VII | `bb79c25068461fbe3674dd926a953240e80f8190d2d8955dc92fb91e8d23dde2` |
| VIII | `d3e986186edcb352719cff5677f16e61664c339321da217fef9905c757010d16` |
| IX | `37ccd65bea8f07962813cbcf2efc7ebac84904ed6f8b20f3aaaa3cb70a736e10` |
| X | `fe918c196811e6f50595ed12998fbc9153269313caea9a08ea2ea1162153b90b` |
| XI | `d817c66f42dd3921ece3d8aadc64e65d831ae690b02798653c646e5299e9fa69` |
| XII | `dbbbace3bf1c4d299664c85942619ef0b1e85a62264a95056b380d2911c1ea8e` |
| XIII | `c659f64efb35bc0d5e0f39a2222f1884d0ba0f5ef9ac3f31918f056c6a670d90` |
| XIV | `ebfd4c23918a7adf8dd9429a95ed240fd685ee084750ab2eddaf0338f1da75fd` |
| XV | `a513e496d185f503f1c9ee1f438a5a07e515b5d3ddc6787bbe7c1e3a7e745714` |
| XVI | `26f89f61dff89921ff1489aa739557699d31eda49dadba73be5fad69f1416856` |
| XVII | `5920f6176bac167a9c81fc50fb891bee388afa879cb2ed5b25d46569cecc4d4d` |
| XVIII | `72c3b3f7b695403e2661e4b5be8b9bb85c8ea1a632090d4b8c4fd9937986d671` |
| XIX | `5dbc34ee855f44bdebb5b49a2a4234724068111cafbf356d71025bb04ff3d426` |
| XX | `7ca1a23e138f501f58c40925ea5380db96c32ce37502f0e280436aac95b22b8f` |
| XXI | `06912c8b58ae1e920a176225d511c90699857fbcff0bc1793440ef75be94a597` |
| XXII | `fcad2c4b48660daf91426fafae03f06f5a921079b0b1fe38a0a3cf152694254b` |
