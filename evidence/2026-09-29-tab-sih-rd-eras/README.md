# RD 1992-2007: the three era packages bind the same CNV maps

`ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/` listed, on
2026-09-29, one TabWin package per era of the old RD layout (`199201_200712/Auxiliar/`
lists only the first, with the same SHA-256; the registry cites it there):

| Package | Bytes | Server date | SHA-256 |
| --- | ---: | --- | --- |
| `TAB_SIH_199201-199712.zip` | 2,926,349 | 2019-08-08 | `b433310785e08b5d2d0c5a438f495ac6b2af9a10d86d8741a3252bc268b1ff88` |
| `TAB_SIH_199801-200307.zip` | 2,928,165 | 2019-08-08 | `171271844c06ec66e2ed0c0abd2ef18f0d67c652e8d9b58d7f0f10d9bf269656` |
| `TAB_SIH_200308-200712.zip` | 3,113,570 | 2019-08-08 | `80582969071fdd2b9008e9121e3052e1705d8a0e9c456d153b13655c787966cd` |

`compare.csv` has one row per package and per `RD.DEF` line that binds `IDENT`, `SEXO`,
`MORTE`, `NATUREZA`, `GESTAO`, `INSTRU` or `VINCPREV` at position 1. `compare.py`, run
on the three zips, writes it with the repository's DEF and CNV parsers.

- The three `RD.DEF` differ as files, but each has the same ten lines for these fields
  (`NATUREZA` has four: `NATUREZA.CNV` twice, `NATUREZC.CNV` and `REGIME.CNV`).
- Each CNV has the same SHA-256 in the three packages, and so the same parsed map.
  `map_sha256` hashes that map (`cnv_map`) as canonical JSON, the parser's output
  before the dictionary writes it as `x-decode`.
- These are the bytes of the members `sih_199201_199712/*.CNV` of `vinculos.json`, which
  records the same SHA-256. `MORTES.CNV` and `VINCPREV.CNV` are packaged in that folder;
  the other five have the bytes of `TAB_SIH.zip`'s `CNV/` members and are stored once,
  under `sih/CNV/` (`mesmo_que`).

So one map per field serves 1992-01 to 2007-12, and the `/field/codes` claims of
`sih_aih_reduzida_1992_2007` cite the three packages. `vinculos.json` lists the three
`RD.DEF` as the dataset's `def`; `gerar_decode_cnv.py` verifies, in each package's own
`RD.DEF`, the line that binds the field to a CNV with the same SHA-256, and writes one
evidence entry per package. The two later `RD.DEF` are packaged next to the first:

| Member | Bytes | SHA-256 |
| --- | ---: | --- |
| `sih_199801_200307/RD.DEF` (from `TAB_SIH_199801-200307.zip`) | 27,540 | `d8c6626e72926e82d4bcccf232bc4b5cba7aa4d62aa3def6b3541c06d945f6c2` |
| `sih_200308_200712/RD.DEF` (from `TAB_SIH_200308-200712.zip`) | 27,462 | `e9831cc53c65ba90ac327a30dc6e64b40137d78b6fe7e295d55d0fab030d227d` |

The CNV of those packages are not packaged again: their members say `mesmo_que`.
