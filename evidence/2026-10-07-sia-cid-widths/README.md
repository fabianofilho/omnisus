# SIA: the CID-10 fields are C(4) in every file read, and what aux_cid10 does not hold

`census.csv` has one row per file read: server time, size, SHA-256, records, layout
number and the DBF field descriptors (`NAME TYPE WIDTH.DECIMALS`, in file order).
`census.py` wrote it from the listings of 2026-10-07:

    uv run --locked python evidence/2026-10-07-sia-cid-widths/census.py CACHE_DIR \
        evidence/2026-10-07-sia-cid-widths/census.csv

The files were downloaded again on 2026-10-11 into an empty cache, and all 831 had the
SHA-256 recorded here.

| Series | Directory | Files | Records |
| --- | --- | ---: | ---: |
| PA of RR | `SIASUS/199407_200712/Dados` | 162 | 1,261,118 |
| PA of RR | `SIASUS/200801_/Dados` | 223 | 6,871,461 |
| AQ of AL | `SIASUS/200801_/Dados` | 223 | 719,061 |
| AR of AL | `SIASUS/200801_/Dados` | 223 | 48,911 |

One file per month the server lists for the series. AL is read for AQ and AR because it
lists both in every month from 2008-01; RR lists no AR. One UF per series: the census
does not show every UF's file.

## Widths

| Series | CID fields | Width | Months the field exists |
| --- | --- | --- | --- |
| PA | `PA_CIDPRI`, `PA_CIDSEC` | C(4) | 1999-07 to 2026-07 |
| PA | `PA_CIDCAS` | C(4) | 2008-01 to 2026-07 |
| AQ | `AP_CIDPRI`, `AP_CIDSEC`, `AP_CIDCAS`, `AQ_CID10`, `AQ_CIDINI1-3` | C(4) | 2008-01 to 2026-07 |
| AR | `AP_CIDPRI`, `AP_CIDSEC`, `AP_CIDCAS`, `AR_CID10`, `AR_CIDINI1-3`, `AR_CIDTR1-3` | C(4) | 2008-01 to 2026-07 |

No CID field changes width. Before 1999-07 the PA has no CID field.

## Values without a row in aux_cid10

`values.py` reads every cached file with the dictionary of its era and writes
`values.csv`: for each CID field, the filled values and every value with no row in
`aux_cid10.codigo` of the packaged bootstrap, with the label `DBF/S_CID.DBF` gives it.

    uv run --locked python evidence/2026-10-07-sia-cid-widths/values.py CACHE_DIR \
        TAB_SIA.zip evidence/2026-10-07-sia-cid-widths/values.csv

`TAB_SIA.zip` is the registered archive (`sia-tab-e5812b51d802`); the script checks its
SHA-256, and the SHA-256 of every cached file against `census.csv`. Its member
`DBF/S_CID.DBF` (SHA-256
`75c21da77e39144bfcb570dc5c4354882a404372d8d52f67cbd2f9d8beceab5c`, 14,705 records, key
`CD_COD` C(4)) is read in place and not packaged. `values.py` reads its text as latin-1,
so "NÃO" shows as "NÇO": the byte `0xC7` is "Ã" in CP850 and "Ç" in latin-1.

On 2026-10-12 the script was run again against `aux_cid10` 2.1.0 (`aux_cid10.parquet`
SHA-256 `4eb308b01474e26309912e6cbe8952f5ef391dc5f860b35d6765ed029ba045cf`), and
`values.csv` came out byte for byte the same.

- **2008 on.** Apart from `0000` ("CID NAO INFORMADO" in S_CID), only the PA has values
  without a row: `N182`, `N185` (S_CID: "CID NÃO IDENTIFICADO"), `N184` (not in S_CID),
  `M881` and `Q350` (each with its own label in S_CID). AQ and AR have none.
- **1994-2007.** The PA writes `0` (one character), which S_CID calls "CID NÃO
  IDENTIFICADO": 469,967 of 674,744 filled `pa_cidpri` and 618,123 of 629,457
  `pa_cidsec`. `pa_cidpri` also has `0000` (132,431). Both fields write three-character
  categories padded with zero (`C610`, `C560`, `C800`...), which S_CID also calls "CID
  NÃO IDENTIFICADO", except `C330`, which is not in S_CID. `Q350` appears once in
  `pa_cidpri` and `2` once in `pa_cidsec`.

These counts are what `sia_producao_ambulatorial`, `sia_apac_quimioterapia` and
`sia_apac_radioterapia` declaring `aux_cid10` rests on (#82);
`sia_producao_ambulatorial_1994_2007` does not declare it yet.
