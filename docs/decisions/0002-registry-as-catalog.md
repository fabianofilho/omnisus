# 0002 — Registry as catalog, not gate; eras as rows, not fields

**Date:** 2026-09-09
**Status:** Decided

This ADR records the registry design decision. Examples of additional era rows
describe how to extend the catalog; they do not imply that those rows ship in
the current registry. See [Datasets](../datasets.md) for the implemented rows.

## Context

Dataset facts were spread across `datasets.py`, `inventory.py` and `fetch.py`,
with `monthly` stated twice and nothing cross-checking them. The SIA/APAC
family (7 datasets) was registered in all three but reachable from neither
the public API nor the CLI. Unifying the facts into one row was the obvious
fix, and it raised two design risks worth recording.

## Decision 1 — the registry is a catalog, not a gate

A single-source registry can become a lock: "the eleven keys in this dict are
the only things you may ingest." We reject that reading.

- The pipeline takes `Dataset` **values**: `import_scope(dataset: Dataset, ...)`.
- `REGISTRY` is a dict of pre-built values — convenience, not authority.
- An uncurated dataset is ingested by constructing a `Dataset(...)` and passing
  it through the same code path. There is no second, untyped mode.
- The row holds **identity and location only**. Behaviour goes in an importer
  module (the existing hybrid pattern), never a flag on the row.

## Decision 2 — era variants are separate rows

Live listing of `ftp.datasus.gov.br` shows era directories for three of four
families (`SIM/CID9` vs `CID10`, `SIASUS/199407_200712` vs `200801_`,
`SIHSUS/199201_200712` vs `200801_`). A single `ftp_dir: str` cannot reach
them.

We considered an `eras: tuple[Era, ...]` field and rejected it: one row implies
one dictionary, but CID9 and CID10 have different columns. The row would claim
a schema it does not have.

Instead, each supported era gets its own row with its own dictionary (for
example, `sim_obitos` and `sim_obitos_cid9`). A cross-era union is a deliberate act by the user, which is
correct: it surfaces a real schema break instead of hiding it.

Note (later): the CID-9 era is now registered as its own row, `sim_obitos_cid9`.

## Consequences

- `ftp_dir: str` survives; `since` becomes `coverage: (first, last | None)`.
- `cadence` (how DATASUS publishes) and `partition_by` (how we store) are
  separate fields. Deriving one from the other would let a storage change
  silently alter filename generation.
- `dictionary` is a field so an ad-hoc `Dataset` can point at a YAML outside
  the package. Uncurated does not mean schemaless: without a YAML the import
  fails fast rather than falling back to all-strings.
- Adding an era is the same operation as adding a dataset: one row, one YAML.
- The row's schema becomes semi-public (users may construct it). Changes are
  additive and keyword-only.
- Tier 3 tests (spec §6) validate each row's `ftp_dir` and `coverage` against
  the live server on a schedule, because centralizing facts centralizes the
  blast radius of a wrong one.

## Amendment 2026-09-12 — release directories share a row; names are readable

DATASUS publishes preliminary files beside the final ones under the same
names (SIM, SINASC, SINAN, e-SUS Notifica; verified live 2026-09-11/12) and
the layout does not change at that boundary. Decision 2 splits rows on
*schema*, so a publication status is not a new row: the row declares
`prelim_dir`, discovery reads both directories, every lake row carries
`_source_release`, and `outdated()` names the scopes whose release moved.
Eras with different columns in different directories still split.

Row names are `<sistema>_<conteúdo>` in full Portuguese words matching the
DATASUS file-type description. `ALIASES` and `get_config()` were removed;
there is no compatibility surface.

## Amendment 2026-09-21 — outdated() compares files, not only the release

`outdated()` now compares each active publication's recorded files with what
the server lists today (path, and size/mtime when recorded), not only the
release, so a moved directory or a same-name republish is reported too.

## Amendment 2026-11-16: an era inside one directory splits by `coverage`

Decision 2 splits rows on schema, and its first examples sit in different directories.
`SIHSUS/199201_200712/Dados` holds 19 DBF layouts of the RD, and the layout changes in
one month: `DIAG_PRINC` goes from CID-9 (C6) to CID-10 (C4), the dates from C6 to C8 and
`ANO_CMPT` from C2 to C4 at 1998-01 (issue #12, decision 1, from the census in
`evidence/2026-10-01-rd-1992-2007-layouts/`). The same rule applies to a directory: two
rows with the same `ftp_dir` and `prefix` and different `coverage`, each with its own
dictionary. The row `sih_aih_reduzida_1992_2007` became `sih_aih_reduzida_1992_1997` and
`sih_aih_reduzida_1998_2007`. The files are the same, and each table only has the columns
of its era (the single table was widened by 44 empty columns in 1992-1997).

Discovery did not cut the listing by `coverage`: `parse_name` read any name of the prefix,
and only the importer refused a scope outside the window. With two rows on one directory
that would list every month under both. `parse_name` now returns `None` for a scope outside
the row's `coverage`, so a name is a file of a row only inside its window, for every row
(`scopes_for`, `available`, `outdated` and the importer see the same months).

The old name is retired, not renamed in place: a dictionary's history stays in
`versoes.json` for good, so `scripts/metadados/travar_versoes.py` lists it in `RETIRED`
with its last locked version and refuses a YAML with that name again. A lake that
imported the old name keeps its `sih_aih_reduzida_1992_2007` table, which no row
writes to any more.
