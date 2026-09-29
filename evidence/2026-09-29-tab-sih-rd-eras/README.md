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
- These are the bytes packaged in `src/omnisus/data/dicionarios/sources/cnv/sih_199201_199712/`
  (`vinculos.json` records the same SHA-256).

So one map per field serves 1992-01 to 2007-12, and the `/field/codes` claims of
`sih_aih_reduzida_1992_2007` cite the three packages. `gerar_decode_cnv.py` writes one
source per claim; the entries for the second and third package were added by hand, and
the script keeps a claim whose map has not changed.
