# RD 1992-2007: 19 DBF layouts

`census.csv` has one row per `RD*.dbc` file read from
`ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/199201_200712/Dados/`, listed on
2026-10-01: server time, size, SHA-256, records, layout number and the DBF field
descriptors (`NAME TYPE WIDTH.DECIMALS`, in file order). `census.py` wrote it; since the
run it checks a download's size before it caches the file, not after, which the CSV does
not depend on:

    uv run --locked python evidence/2026-10-01-rd-1992-2007-layouts/census.py CACHE_DIR \
        evidence/2026-10-01-rd-1992-2007-layouts/census.csv

- 260 files, all dated 2013-10-31 on the server, 11,124,112 records.
- One file per month from 1992-01 to 2007-12 (192 months, 269,854 records): `RDRR`, or
  `RDAP` in the 17 months the server lists no `RDRR` (1995-07 to 1996-01, 1997-05,
  1997-06, 1997-10, 1997-11, 1999-12 and 2000-01 to 2000-05).
- 19 distinct descriptor lists (layouts), numbered by the first month that has them. Each
  covers one run of consecutive months.
- At each of the 34 months on either side of a layout change, `RDSP` and `RDMG` have the
  same layout as the `RDRR` or `RDAP` file of that month: the changes are not one UF's.

| Layout | Months | Files | Fields | Adds | Drops | Changes type |
| ---: | --- | ---: | ---: | --- | --- | --- |
| 1 | 1992-01 to 1993-12 | 26 | 35 | (first) | | |
| 2 | 1994-01 to 1994-11 | 15 | 39 | CEP MUNIC_RES VAL_RN US_RN | | |
| 3 | 1994-12 | 3 | 39 | VAL_SANG | VAL_SANGUE | |
| 4 | 1995-01 to 1995-12 | 16 | 41 | VAL_SANGUE NUM_PROC SEMIPLEN | VAL_SANG | |
| 5 | 1996-01 to 1996-07 | 11 | 41 | | | NUM_PROC C to N |
| 6 | 1996-08 to 1996-12 | 9 | 41 | | | NUM_PROC N to C |
| 7 | 1997-01 to 1997-12 | 16 | 42 | DIAG_SEC | | |
| 8 | 1998-01 to 1998-12 | 16 | 41 | VAL_SADTSR VAL_TRANSP DIAG_SECUN GESTAO NACIONAL MARCA_UTI CAR_INT | US_SH US_SP US_SADT US_RN US_ORTP US_SANGUE DIAG_SEC SEMIPLEN | |
| 9 | 1999-01 to 1999-12 | 16 | 52 | UTI_MES_IN UTI_MES_AN UTI_MES_AL VAL_UTI TOT_PT_SP NUM_FILHOS INSTRU CID_NOTIF CONTRACEP1 CONTRACEP2 GESTRISCO | | |
| 10 | 2000-01 to 2000-12 | 16 | 60 | UTI_MES_TO UTI_INT_IN UTI_INT_AN UTI_INT_AL UTI_INT_TO VAL_OBSANG VAL_PED1AC CPF_AUT HOMONIMO | UTI_TOTAL | |
| 11 | 2001-01 to 2001-12 | 16 | 60 | INSC_PN SEQ_AIH5 | COD_ARQ CONT | |
| 12 | 2002-01 to 2002-07 | 11 | 65 | COD_ARQ CONT CBOR CNAER VINCPREV | | |
| 13 | 2002-08 to 2003-07 | 16 | 68 | GESTOR_COD GESTOR_CPF GESTOR_DT | | |
| 14 | 2003-08 to 2004-06 | 15 | 69 | CNES | | |
| 15 | 2004-07 | 3 | 68 | CGC_MANT COD_SEG | CBOR CNAER VINCPREV | INSC_PN SEQ_AIH5 C to N |
| 16 | 2004-08 to 2004-12 | 9 | 67 | | CGC_MANT | |
| 17 | 2005-01 to 2005-12 | 16 | 69 | DIAR_ACOM VAL_ACOMP | | |
| 18 | 2006-01 to 2006-03 | 7 | 70 | IND_VDRL | | |
| 19 | 2006-04 to 2007-12 | 23 | 75 | PROC_SOLIC RUBRICA CBOR CNAER VINCPREV INFEHOSP CID_ASSO CID_MORTE | COD_ARQ CONT COD_SEG | INSC_PN SEQ_AIH5 N to C |

"Adds" and "Drops" compare with the layout above. Layouts also change field widths (for
example `N_AIH` C10 to C13 in layout 18) and order; `fields` has every descriptor.

Layout 19 is the 75 fields `sih_aih_reduzida_1992_2007` was first written from
(`RDRR0712.dbc`). Fourteen columns of the other layouts are not among them:

| Column | DBF type | Months |
| --- | --- | --- |
| `UTI_TOTAL` | N2.0 | 1992-01 to 1999-12 |
| `US_SH`, `US_SP`, `US_SADT`, `US_ORTP`, `US_SANGUE` | N9.2 | 1992-01 to 1997-12 |
| `COD_ARQ` | C1.0 | 1992-01 to 2000-12, 2002-01 to 2006-03 |
| `CONT` | N7.0 | 1992-01 to 2000-12, 2002-01 to 2006-03 |
| `US_RN` | N9.2 | 1994-01 to 1997-12 |
| `VAL_SANG` | N13.2 | 1994-12 (that month has no `VAL_SANGUE`) |
| `SEMIPLEN` | C1.0 | 1995-01 to 1997-12 |
| `DIAG_SEC` | C6.0 | 1997-01 to 1997-12 |
| `CGC_MANT` | C14.0 | 2004-07 |
| `COD_SEG` | C8.0 | 2004-07 to 2006-03 |

Each has the same type in every layout that has it. Of the 89 fields, only `NUM_PROC`,
`INSC_PN` and `SEQ_AIH5` change type (C or N) between layouts.

The `RD.DEF` of the three era packages (`evidence/2026-09-29-tab-sih-rd-eras/`) binds
`SEMIPLEN` ("Gestão (95-97)") to `GESTAO.CNV` at position 1 and `DIAG_SEC` to CID-9
tables; none of them names the other twelve columns.

The fixtures `tests/fixtures/dbc/sih_rd_rr_1994_12_mini.dbc`, `sih_rd_rr_1997_09_mini.dbc`
and `sih_rd_rr_2007_12_mini.dbc` are `RDRR9412`, `RDRR9709` and `RDRR0712`, with the SHA-256
of their rows here (layouts 3, 7 and 19). `sih_rd_rr_2004_07_excerpt.dbc` is records 481 to
571 (0-based) of `RDRR0407` (layout 15) under that file's header: the longest run of records
with no CPF in `CPF_AUT` or `GESTOR_CPF`. Together they hold every field of the 19 layouts.
`tests/unit/transforms/test_sih_rd_1992_2007_fields.py` reads `census.csv` to check that,
and that the dictionary declares exactly these 89 fields.
