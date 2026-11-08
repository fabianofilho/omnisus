# Changelog

## Unreleased

### API

- `read(dataset, years=..., ufs=..., months=...)` returns the rows `load` returns for
  the same arguments, harmonised categories included, from what the lake already has,
  without connecting to DATASUS: it works while the server is down, when `load` raises
  `FtpUnavailable`. It warns naming the requested scopes the lake lacks and raises
  `LookupError` when it has none of them. `read(table)` without `years` is unchanged
  (#92).
- `WriterBusyError`, `CommitOutcomeUnknown`, `CENSUS_YEARS` and
  `ESTIMATE_UNAVAILABLE_YEARS` are exported from `omnisus`, so a caller that imports
  only `omnisus.__all__` can catch the writer's errors and build the IBGE year selector.
  `Product.name` documents that it is also the relation the importer writes in the lake
  (#102).
- `publications()` and `reference_join_sql()` take `snapshot_id: int | None = None`:
  one attach reads the manifest and the `aux_*` vocabulary at snapshot `N` with
  `AT (VERSION => N)`, which wins over `LakeReader(snapshot_id=...)`. A snapshot from
  before the first import returns `[]`. `None` keeps the SQL and the rows of 0.2.3. The
  data table is pinned by the caller's `FROM` (#101).

- `cite()` and `citation_from_publications()` with `accessed=None` print as the access
  date the UTC day of each row's `published_at` (when the publication was written to the
  lake) or, for IBGE, of `collected_at` (when the HTTP request was made), instead of the
  day the citation is generated: a file imported on 2026-10-18 and cited a week later
  stays "acessado em 2026-10-18". A value with an offset is converted to UTC first.
  `accessed=` still sets one date for every row. A row with neither column prints
  "(data de acesso desconhecida)"; a value that is not an ISO date raises `ValueError`.
- `cite(snapshot_id=N)` reads the publications, and the IBGE manifest, as they were at
  snapshot N: after a `replace`, citing an older snapshot keeps that snapshot's date and
  run. Without `snapshot_id`, a `LakeReader(snapshot_id=M)` cites M instead of the
  newest snapshot. A snapshot the lake does not have raises
  `duckdb.InvalidInputException`.

### Dictionaries

- `sih_aih_reduzida` (2.13.0) declares `fonte_orc`, which RD files publish from 2025-03
  (layout 6, `evidence/2026-10-06-rd-2008-layouts`), with the labels of `CNV/fonterem.CNV`
  of `TAB_SIH.zip`, now packaged, which `RD2008.DEF` binds to `FONTE_ORC`. `00`, the only
  value of the RDRR2503 excerpt, is not a key of the table and stays unlabeled (issue
  `fonte_orc-00-sem-fonte`). `check_columns` no longer reports the field as "not in
  dictionary" (#86).
- `etnia` of `sih_aih_reduzida` (2.14.0) and `sih_aih_rejeitada` (1.3.0) takes its labels
  from `CNV/etnia.cnv` of `TAB_SIH.zip`, now packaged, which `RD2008.DEF` and `RJ2008.DEF`
  bind to `ETNIA`. The table names `0001`-`0264` and opens with the range `0000-9999`,
  "NÃO INFORMADO", expanded as decided in #7: every other 4-digit code, `0000` included,
  takes that label only through the range (issue `etnia-nao-informado-pela-faixa`). In
  the RR and SP fixtures `0000` marks a non-indigenous patient (`raca_cor` 01-04), not an
  unknown ethnicity, as the SIH page and that issue say: count indigenous patients by
  `raca_cor`. 15 labels hold U+00AD, a soft hyphen, and a text search misses them
  (issue `etnia-hifen-suave`). The RD dictionary grows by 314 KB and the RJ one by 294 KB.
- The CID-10 fields of `sia_producao_ambulatorial` (1.2.0), `sia_apac_quimioterapia`
  (0.2.0) and `sia_apac_radioterapia` (1.1.0), 20 fields, declare a reference to
  `aux_cid10`, so `reference_join_sql` works for them. `0000` is "CID NAO INFORMADO" in
  `S_CID.DBF` of `TAB_SIA.zip` and finds no row. The census of the CID field widths and
  of the values without a row is in `evidence/2026-10-07-sia-cid-widths/`.
- `pa_cidpri` and `pa_cidsec` of `sia_producao_ambulatorial_1994_2007` (1.1.0) declare
  `aux_cid10` too (#82). Codes stay as published, so the values the PA of that era
  writes with no row in `aux_cid10` stay unlabelled: `0` (in both fields of every row
  with `pa_docorig` 'B' in PARR0712) and three-character categories padded with zero
  (`C610`), which `S_CID.DBF` calls "CID NÃO IDENTIFICADO", and `0000`. `C610` is not
  mapped to `C61`. No DEF of 1994-2007 is archived, so the fields come from the RR census instead.
- The CID-10 fields of six more SIA datasets declare `aux_cid10`: `sia_apac_laudos_diversos`
  (0.2.0), `sia_apac_medicamentos` (0.2.0), `sia_apac_nefrologia` (1.1.0) and
  `sia_apac_tratamento_dialitico` (0.2.0) (`ap_cidpri`, `ap_cidsec`, `ap_cidcas`),
  `sia_atencao_domiciliar` (1.2.0) (`cidpri`, `cidassoc`, `pa_cid`) and
  `sia_psicossocial` (0.3.0) (`cidpri`, `cidassoc`), 17 fields. Each is a field the
  dataset's DEF in `TAB_SIA.zip` relates to `S_CID.DBF`, and C(4) in the fixtures of
  `tests/unit/test_references.py` (AD of RR and SP, PS of RR and SP, AM and ATD of RR,
  AN of PA, SAD of MA); no field-width census was run for them. Their only value
  without a row there is `0000`.
- `sih_aih_reduzida` (2.14.1): RDRR2501 publishes `etnia` `X389` (2 rows) and `X401` (3), not
  digits, so outside the `0000-9999` range of `etnia.cnv` and unlabeled; the open issue
  `etnia-x389-x401-sem-fonte` says so, and the excerpt `sih_rd_rr_2025_01_excerpt` (the two
  `X389` rows, `GESTOR_CPF` blanked) pins it (#7).
- `vinculos.json` lists in `sem_cnv`, with the reason, the SIH fields `RD2008.DEF` and
  `RJ2008.DEF` bind to CNV members not packaged yet: `nat_jur` and `cnaer` of
  `sih_aih_reduzida` and `sih_aih_rejeitada`, and `gestor_cod` of `sih_aih_rejeitada`
  (#7, decision 4). No dictionary changes.
- `vinculos.json` lists in `sem_cnv` the other fields `RD2008.DEF` and `RJ2008.DEF` bind
  to a CNV with no map: 21 of `sih_aih_reduzida` and 20 of `sih_aih_rejeitada`. Each reason
  cites the DEF lines and why the binding gives no map: a grouping of the code (CID chapter
  and group, year and month of a date, region and UF of the municipality), a start other
  than 1 (`dias_perm`, `n_aih`), lines that put a field name where the start column goes
  (`faec_tp`, `proc_rea`) or a member not packaged (`uf_zi` and the rest). One test, which
  replaces the #130 one, fails when either DEF binds a field with no map and no reason, or
  when a reason's DEF, lines, members, member count, start columns or labels differ from the
  packaged DEF; `cod_idade` of `sih_aih_rejeitada` is left to #6 (#137). No dictionary
  changes.

### Packaging

- `ipykernel` leaves the required dependencies, where 0.2.3 put it without a changelog
  entry, for the new `colab` extra: a library-only install (a server reading the lake with
  `LakeReader`) no longer pulls the Jupyter kernel and its ~25 dependencies. The Colab
  notebook installs `"omnisus[colab]==<version>"`; `uv pip install "omnisus[colab]"` does
  the same elsewhere (#100).

### Dictionaries

- `sih_aih_reduzida_1992_2007` (1.3.0) warns in the dictionary, not only in the docs,
  that `diag_princ` holds CID-9 (6 digits) from 1992-01 to 1997-12 and CID-10 from
  1998-01 to 2007-12 in the same column, so a filter such as `LIKE 'I21%'` over
  1992–2007 misses 1992–1997: open issue `diag-princ-cid9-ate-1997`, from the layout
  census in `evidence/2026-10-01-rd-1992-2007-layouts/` and the four RD fixtures.
  `cid_morte` and `cid_asso` get `cid-zero-a-esquerda`: RDRR0712 writes CID-10
  categories after a `0` (`0I64`), which do not join `aux_cid10`. Codes and labels do
  not change.
- `sia_apac_cirurgia_bariatrica` (0.2.0) is titled "SIASUS — APAC de Acompanhamento
  Pós-Cirurgia Bariátrica (ABO)": `TAB_SIA.zip` reads `ABO` files with
  `APAC_Pos_Cirurgia_Bariatica.def`, and every row of `ABOSP2401.dbc` has `ap_pripal`
  0301120056, post-surgery follow-up in SIGTAP. The dataset keeps its name; renaming it
  would change the API. It gains the labels that DEF binds for `ap_catend`
  (`CARAT_AT.CNV`), `ap_condic` (`TP_GESTAO.CNV`), `ap_motsai` (`MOTSAIPE.CNV`) and
  `ap_tpups` (`TP_ESTAB.CNV`), as `sia_apac_acompanhamento_bariatrica` already had.
  `ap_mn_ind` stays unlabelled: the DEF binds it to `MANT_IND.CNV` without the `CNV/`
  folder, which is not the packaged member; so do `ap_cid_c1`–`ap_cid_c5`, whose
  `CID_COM.CNV` is not archived.
- `docs/sources/sia.md` gives the Informe SIASUS 2019-07 bariatric follow-up layout
  (`ABUFMM.DBF`, 58 fields) to `AB`, whose header it matches, instead of `ABO`.

### Vocabularies

- `aux_cid10` (2.1.0) gains `bloco` and `bloco_descricao`: the CID-10 group of each code
  (`B50-B64`, "Doencas devidas a protozoários"), from `CID10-grup_d.cnv` in
  `SIM/CID10/TAB/OBITOS_CID10_TAB.zip`, the grouping the SIM DEF binds to `CAUSABAS`.
  Each block lies in one chapter. `O93` and `O930`–`O939`, a Brazilian extension, are in
  no group and have no block. `evidence/2026-10-11-blocos-cid10/` compares the groups
  with the WHO ICD-10 2019 and CBCD 2008 lists. Run `omnisus lake update-auxiliares` (or
  `Lake.bootstrap_auxiliares()`) to load the new columns (#103).

### Performance

- The age rule's SQL trims the 29 whitespace characters with one constant,
  `decode(unhex('…'))`, instead of 29 `chr()` calls joined by `||` in every trim.
  DuckDB binds the expressions again on every query, so a `load` with an age rule and an
  audit of `validar_fonte.py` plan in a fraction of the time (one SIM audit: 6 s to
  0.5 s). Values are the same; audit evidence written from now on records the new SQL
  text, older evidence keeps the `chr()` form.
- `describe_datasets()` reads the packaged dictionaries instead of calling
  `describe_dataset()` for each dataset (about 0.4 s to 3 ms per call). The table is the
  same; the consistency checks of `describe_dataset()` still run when it is called, and
  the tests call it for every dataset.
- Staging maps each batch's columns by name once, instead of rebuilding the list of
  column names for every field.
- `load_dicionario()` parses with libyaml (`yaml.CSafeLoader`) when PyYAML was built
  with it, as its wheels are, and with the pure-Python loader otherwise. The first load
  of `sih_aih_reduzida` in a process drops from about 0.7 s to 0.1 s, and a cold
  `describe_datasets()` from about 2.5 s to 0.4 s. The parsed dictionaries are the same.

### omnisus-dbf 0.2.2

- The native reader reads D (date) fields with the semantics of dbfread's `parseD`, so
  SINAN national files no longer fall back to the Python reader. `API_VERSION` stays 2
  (#149).

## v0.2.3 — 2026-10-08

**Upgrading from 0.2.2:** no parser version changed (the import still reads the same
`encoding` and `x-identity` of every dictionary), so a 0.2.2 lake keeps every scope;
`load` downloads nothing again.

### API

- `read(table)` returns a lake table or view, whole, as a polars DataFrame: the `aux_*`
  vocabularies, the `ibge_populacao` view, or every scope of a dataset already imported.
  A table the lake does not have raises `LookupError` naming what imports it.

### Dictionaries

- `sim_obitos` (2.6.0, rule 1.2.0) and `sih_aih_reduzida` (2.12.0, rule 1.3.0) gain
  harmonised categories in every UF for SIM 2020–2024 and SIH 2020-01 to 2025-02: the
  135 DO and 1,674 RD files were audited in one batch under the written acceptance rule
  that ADR 0003 now records, and none was blocked (evidence in
  `evidence/2026-10-07-validacao-sim_obitos-2020-2024/` and
  `evidence/2026-10-07-validacao-sih_aih_reduzida-2020-01-2025-02/`). The formulas do not
  change; a caller that passes the old `rule_version` now gets `ValueError`. The fields'
  `derivation.rule_version` follows, and so do the SIM subsets that copy them
  (`sim_obitos_infantis`, `sim_obitos_maternos`, `sim_obitos_externos` 1.1.1). SIH from
  2025-03 (layout 6) waits for #86 (#85).
- `scripts/metadados/validar_fonte.py` audits a batch (`--ufs`, `--inicio`, `--fim`,
  `--referencia`; no `--ufs` for a national dataset) with one server listing. The
  reference must be the file validated by hand, and the batch stops as soon as it fails.
  A dropped connection resumes without downloading again, except a failed audit or one
  made under another dictionary version. Each run writes one evidence folder, with no
  local path, and never replaces an existing one. Removed: `--uf`, `--year`, `--month`,
  the `reports/evidence` default and the per-scope `acceptance.json` (#85).
- `docs/datasets.md` shows the validated scopes as UFs and intervals
  ("27 UFs, 2020 a 2024") instead of one entry per scope (#85).
- `sih_aih_reduzida.diagsec9` no longer references `aux_cid10`: the 157 RD files read
  from 2014-01 to 2026-07 (one RR or AP file a month, plus SP and MG at each layout
  change) publish `DIAGSEC9` as C(1), so no row could join. Its
  `physical_type` claim is `conflicting` (IT_SIHSUS_1603, p. 4, says `char (4)`) and the
  field carries the issue `diagsec9-c1`. `reference_join_sql("sih_aih_reduzida",
  "diagsec9")` now raises. Lakes keep their scopes: the parser version does not read
  references (#67).

### Docs site

- The `sih_aih_reduzida` profile gives the `ident` labels the dictionary has, from
  `TAB_SIH.zip`, `RD2008.DEF` → `IDENT.CNV`: 1 = "Normal", 5 = "Longa permanência" and
  "Outras/ignorado" for any other code from 0 to 9, 3 included. It said 1 = AIH
  principal, 3 = AIH de continuação and 5 = AIH de longa permanência, the map without a
  source that the dictionary dropped on 2026-09-26.
- The `load` docstring and the API page say that `load` adds the harmonised categories
  the dataset's dictionary defines (`describe_dataset(base)["analytics"]`), not age, sex
  and dates for every validated source: of the nine datasets with validated scopes,
  `sim_obitos` and `sih_aih_reduzida` define all three and the other seven age only.
  The docstring points to `describe_datasets()` and "Bases e argumentos", and says that
  a dataset whose dictionary defines no category gets no warning (#65).
- The profiles call `docs/datasets.md` "Bases e argumentos", not "catálogo" (in
  CONTEXT.md the catalog is the lake's database), and every link to it lands on a
  section: "Onde fica no servidor" when the sentence names a server directory, "Outras
  fontes" for IBGE population, the system's section otherwise. The CNES profile no
  longer says the package skips the LT file: it imports it as `cnes_leitos` (#64).

### Notebooks

- New `bases.py` lists every DATASUS FTP dataset with `describe_datasets()`, offline,
  with a count per system, and takes any of them to the citation: it shows the exact
  `load` call for `BASE` (no `ufs` for a national dataset, `months` only for a monthly
  one), says when the scope is outside the declared coverage, and shows the dictionary
  fields and the link to the system's section of "Bases e argumentos". Then
  `available_releases` (it stops there when the server does not list the scope),
  `load`, `check_columns`, the row count and `cite`. It opens on `cnes_leitos`, RR,
  January 2024 (#55).
- The Colab notebook shows every dataset right after the install, in a section of its
  own (#55).
- The Colab notebook goes through the library end to end with Roraima: SIM 2022, SIH
  processed in January 2023 and the IBGE 2022 census. It covers `describe_dataset`, `available`,
  `load`, `check_columns`, `outdated`, `label`, the harmonised age and sex categories,
  CID-10 chapters of SIM and SIH, deaths per 100,000 through `import_ibge_populacao`,
  and `cite`. It writes no SQL: `read` brings `aux_cid10`, `aux_municipios`, `aux_uf`
  and `ibge_populacao` as polars DataFrames, and the joins are in polars.
  The Google Drive lake is behind `USAR_DRIVE`, so "Run all" works without mounting it,
  and a scope that is not a validated source skips the harmonised section instead of
  failing. `tests/integration/test_colab_e2e.py` (e2e) runs it against the server for
  RR and SP, and for the 27 UFs with `OMNISUS_E2E_UFS=ALL`.
- `sia.py` and `sinan.py` point to `describe_datasets()` and `bases.py` instead of
  listing the `BASE` values by hand; `sia.py` says it runs on any SIA table the
  package imports (#55).
- When the server lists no file of `BASE` for `UF`, `sia.py`, `sih_aih_reduzida.py`,
  `cnes_estabelecimentos.py`, `medicamentos.py`, `sim_obitos.py` and
  `sinasc_nascidos_vivos.py` say so at discovery, suggest another `UF` and stop before
  `load`, as `bases.py` does; `sinan.py` does the same when the server lists no file of
  `BASE`. Before, discovery failed with polars' `ColumnNotFoundError` (#79).

## v0.2.2 — 2026-10-06

**Upgrading from 0.2.1:** no parser version or dictionary changed, so a 0.2.1 lake
keeps every scope; `load` downloads nothing again.

### API

- `describe_datasets()` returns every DATASUS FTP dataset the package curates as one
  polars table, offline: name, `category` (the system, as `describe_dataset` reports
  it), title, geography, cadence, declared coverage with the month for monthly datasets
  (`"2014-08"`), prefix, final and preliminary directories, columns, labelled columns
  and the scopes whose audited file is a validated source of the harmonised categories
  (#54).

### Docs site

- "Bases e argumentos" moves to Pesquisa, right after "Comece aqui", and is rendered from
  `describe_datasets()`: one section per system (CNES, SIA, SIH, SIM, SINAN, SINASC)
  linking its profiles, coverage with the month for monthly datasets ("2014-08 em
  diante", not "2014 em diante") and "+ preliminar", how each dataset is published
  ("por UF, mensal", "Brasil, anual"), the harmonised categories each dictionary defines
  (age, sex, dates) with the scopes validated for them, and the server directories in a
  section of their own. Dictionary links point at the release tag. The build fails on a
  link to a missing heading (#54).

### CLI

- `omnisus doctor` prints the installed `omnisus-dbf` (version and API, also when the API
  is incompatible) and the backend `OMNISUS_DBF_BACKEND` and `OMNISUS_DBC_BACKEND`
  resolve to. For DBF it says that Rust reads C/N fields only, so under `auto` a file
  with other field types is read in Python. An invalid setting is named (#45).

### Notebooks

- `linkage.py` checks that SIM, SINASC and SIH RD are published for the chosen UF and
  year, and not in `PULAR`, before downloading anything; if one is missing it names it
  and stops instead of failing later with `KeyError` or an empty `pl.concat` (#44).
- `sinan.py` also runs with `BASE = "sinan_tuberculose"`, where the researcher guide and
  the tuberculose profile send readers; the default stays `sinan_chagas`. Step 5 counts
  notifications by type of entry (`tratamento`) and closing status (`situa_ence`), with
  dictionary labels, instead of stopping with `ValueError` in the branch written for
  hanseníase (#53).

### omnisus-dbf 0.2.1

- Metadata only, same code and `API_VERSION` 2 as 0.2.0: its PyPI page gets the SPDX
  license `MIT`, project URLs, author and the updated README (#43). `omnisus` accepts it
  through `omnisus-dbf>=0.2.0,<0.3`.

## v0.2.1 — 2026-10-02

**Upgrading from 0.2.0:** no parser version changed, so a 0.2.0 lake keeps every
scope; `load` downloads nothing again.

### Docs site

- The site is deployed by release tags (`v*`), not by every push to `main`, so it
  describes the omnisus installed from PyPI. Pull requests still build it.

### Packaging

- `omnisus-dbf` is capped below its next minor (`>=0.2.0,<0.3`): omnisus accepts one
  `API_VERSION`, and only a new minor of `omnisus-dbf` may change it.
- Releases tag the release PR's head and publish before merging, so `main` never pins
  a version PyPI does not have yet (RELEASE.md).

### Messages

- When `skip_same` refuses a scope already in the lake, the reason says whether the
  server file changed or the same file was imported by another parser version (another
  omnisus release or dictionary), and `load` says to run the same call again with
  `policy='replace'`.

### Install with uv

- README, the researcher guide and getting-started install with `uv add omnisus` or
  `uv pip install omnisus`, say how to upgrade, and keep `pip install omnisus` as the
  fallback. The Colab notebook runs `!uv pip install -q omnisus==<version>`; Colab ships
  uv and sets `UV_SYSTEM_PYTHON`.
- Notebook instructions open the PyPI version pinned in each notebook
  (`uvx marimo edit --sandbox`, `uvx marimo export html --sandbox`); the checkout path
  is for contributors.
- The reproducibility guide adds "Fixar o ambiente" (`uv.lock` or `uv pip freeze`) and
  says that `cite` prints the running omnisus version and today's date unless
  `accessed=` is given.
- `omnisus-dbf` metadata: SPDX license `MIT`, project URLs and author; its README builds
  with `uv build` and drops stale release notes. These reach PyPI with the next
  `dbf-v*` release.

### SIH

- `sih_aih_reduzida_1992_2007` declares the 14 fields that the older RD layouts publish
  and the 2007 file lacked: `uti_total`, `us_sh`, `us_sp`, `us_sadt`, `us_ortp`,
  `us_sangue`, `us_rn`, `cod_arq`, `cont`, `semiplen` (labelled from `GESTAO.CNV`),
  `diag_sec`, `val_sang`, `cgc_mant` and `cod_seg` (#30). A census of one file per
  month finds 19 DBF layouts in 1992-2007 (`evidence/2026-10-01-rd-1992-2007-layouts/`).
  `num_proc`, `insc_pn` and `seq_aih5` change between numeric and text across months;
  importing both kinds into one lake table fails until #40 is decided.

## v0.2.0 — 2026-10-01

**Upgrading from 0.1.0:** #19 changed how a publication's parser version is computed, so
`load` refuses every scope a 0.1.0 lake already holds. Run each `load` once with
`policy="replace"`; later calls download nothing again.

### Rust decoder by default

- `omnisus` depends on `omnisus-dbf` 0.2.0, now on PyPI, on Linux x86_64, macOS
  (arm64, x86_64) and Windows x86_64 (#38). The `auto` backend then reads DBF and
  decompresses DBC in Rust; other platforms keep the Python decoders, and no install
  needs a Rust toolchain. `OMNISUS_DBF_BACKEND=python` and `OMNISUS_DBC_BACKEND=python`
  still select Python. The `--find-links` install is gone.
- A `dbf-v*` tag publishes `omnisus-dbf` to PyPI after the full native matrix passes
  (#37).

### On PyPI

- `omnisus` is published to PyPI: `pip install omnisus`. The Colab notebook and the
  PEP 723 header of every marimo notebook install `omnisus==0.2.0` from PyPI instead
  of a git commit.

### Import alias (breaking for copied code)

- Docs, notebooks and examples use `import omnisus as sus` instead of `odb` (#21).
  Only the alias in examples changed; the API names are the same.

### SIH dictionaries

- RD: `regct` gets the `REGCT.CNV` map, conflicts between the CNVs and the older
  map are resolved in favour of the CNV (#5); `tpdisec1`–`tpdisec9` get
  `TP_DIAGSEC.CNV` (#14); `diagsec1`–`diagsec9` link to `aux_cid10` (#22).
- RD and RJ: `nacional`, `contracep1`, `contracep2` and RJ `st_mot_blo` get the
  TAB_SIH maps (#20).
- `sih_aih_reduzida_1992_2007` gets the maps of `TAB_SIH_199201-199712.zip`, checked
  against the three packages of the era (#23, #36).
- Each identical CNV is stored once, and the evidence of the three RD eras is
  generated instead of written by hand (#36).

### Dictionary versions

- `src/omnisus/data/dicionarios/versoes.json` locks each dictionary's `x-version`
  to its content; a changed dictionary needs a higher version (#35).
- A publication's `parser_version` hashes only what the import reads from the
  dictionary, so editing a label or a claim no longer forces `replace` on scopes
  already imported (#19).

### Docs and notebooks

- README and site for researchers, Colab notebook, generated dataset arguments (#4);
  notebooks use only the public API (#16); leaner `AGENTS.md` (#15).

## v0.1.0 — 2026-09-25

First release of `omnisus`.

### What the package does

- Imports DATASUS FTP datasets (SIM and its subsets, SINASC, SIH, SIA, CNES, SINAN
  Chagas, hanseníase and tuberculose), IBGE population editions, CNES establishment
  names, SIGTAP and Hórus stock into a DuckLake lake. [Datasets](docs/datasets.md) lists
  every registry row.
- Records each imported scope as a publication with its server files and their
  SHA-256; `odb.cite` turns a snapshot into a citation.
- `odb.load`, `odb.label` and `odb.check_columns` cover an analysis from download to
  labelled rows. Labels come from dictionaries whose claims cite official documents
  registered with URL and SHA-256.
- Decodes DBC and DBF in Python, or in Rust with the optional `omnisus-dbf` package.

### Renamed: `omnisus-db` is now `omnisus` (breaking)

- Distribution, import and CLI are `omnisus`: `import omnisus as odb`,
  `omnisus import ...`. The native package is `omnisus-dbf` (import `omnisus_dbf`),
  in `native/omnisus-dbf`. No `omnisus_db` alias is kept.
- The inventory cache moves from `<cache>/omnisus-db/inventory` to
  `<cache>/omnisus/inventory`; the old one is only a cache and is rebuilt.
- Citations say "Importado com omnisus <versão>".
- Environment variables (`OMNISUS_*`) and lake tables (`_omnisus_*`) keep their
  names: existing lakes open unchanged.

### Removed since `omnisus-db` v0.3.2

- **`cnes_profissionais` (CNES `PF`).** The file names each professional with CPF and
  CNS and answers no clinical question. Its registry row, dictionary, DEF and fixture
  are gone.
- **`omnisus.transforms.cns`.** It deciphered the patient CNS of SIA files and had no
  public consumer.
- `Lake.vacuum` and `omnisus lake vacuum`, already deprecated: use `cleanup_files` /
  `lake cleanup-files`. Also the uncalled `import_st_scope` and
  `lake.schema.canonical_type`/`ddl_for_field`.
- Runtime dependencies nothing imported: `pandera`, `obstore`, `pydantic`,
  `pydantic-settings`, `tomli-w`; `moto` and `pyfakefs` from `dev`. `frictionless`
  is now a `dev` dependency.
- Tutorials 01–05 (they repeated the per-base notebooks), the exploration and
  development notebooks, and the 2026-09-10 audit snapshot pages (`catalogo.md`,
  `campos.csv`, `cobertura.csv`, `fontes/registro.json`) with their generator.

### Changed

- Notebooks live in `notebooks/`, one per base plus `linkage.py`, and pin
  `marimo>=0.25.0,<0.26` like the `notebooks` extra.
- Evidence cited by dictionaries, tests and docs lives in `evidence/`.
- URLs point to `github.com/raphaelfh/omnisus` and `raphaelfh.github.io/omnisus`.
- Docs match the code: `skip_same` skips without downloading, `not_listed` versus
  `fetch_failed`, a second writer fails at once with `WriterBusyError`.
