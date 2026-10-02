# Changelog

## Unreleased

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
