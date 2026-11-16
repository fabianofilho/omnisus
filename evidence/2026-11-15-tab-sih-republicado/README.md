# TAB_SIH.zip republished on 2026-10-15: no packaged member changed (#154)

`TAB_SIH.zip` at `ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/`
was read on 2026-11-15: 6,083,658 bytes, server time `Fri, 16 Oct 2026 01:14:01 GMT`
(2026-10-15 22:14 in Brasília), SHA-256
`21e42384645a9386add9f3644264145f39fc00bbb602f305d87bd0793b7e476b`. It is
`sih-tab-21e42384645a` in `registry.json`, the third edition of this URL after
`sih-tab-714ed980d483` (2026-09-14) and `sih-tab-f05b32f32908` (2026-09-21). The hash is
the one raphaelfh/omnisus#154 relayed from the review of #140.

`members.csv` has one row per member (`census.py` wrote it from the zip: path, size,
SHA-256, the date stored in the zip) and, for each member the repository already holds a
hash of, that hash and its source. A member held under both older editions has two rows.

- 885 members: 797 `CNV/`, 81 `DBF/`, 3 `Docs/` and 4 at the root (`RD2008.DEF`,
  `RJ2008.DEF`, `SP2008.DEF`, `Motivo_de_Erro.DEF`).
- 882 of the 885 carry the date 2026-10-15 inside the zip, so the whole archive was
  rewritten that day; two are dated 2026-06-16 and one 2026-02-19.
- **35 recorded hashes compared, 35 equal.** 31 are the members `vinculos.json` packages
  from `sih-tab-f05b32f32908` (the four DEF files, 26 CNV and 1 DBF); 4 are the members listed in
  `evidence/2026-09-14-contrato-analitico/tab-sih-sources.json` for `sih-tab-714ed980d483`
  (`CNV/SEXO.CNV`, `CNV/IDADEBAS.CNV`, `CNV/IDADEDET.CNV`, `RD2008.DEF`). `CNV/SEXO.CNV` and
  `RD2008.DEF` are in both lists, so 33 distinct members were compared.

**What this settles.** Nothing `vinculos.json` packages or cites by hash changed in the
republication, so `vinculos.json` stays on `sih-tab-f05b32f32908` and no dictionary moves
to the new edition. The new edition is registered so a later pull request can cite it.

**What it does not settle.** The 852 members the repository holds no hash of were not
compared: `sih-tab-f05b32f32908` is no longer on the server and no copy of it was kept, so
a CNV or DBF that nothing packages yet may differ from the edition of 2026-09-21. Whoever
packages one of them cites it from the new edition and reads it again.
