# API reference

Every signature, parameter table and accepted value below is rendered from the
docstrings of the version named in the header, so it changes with the code. In
Python, `help(sus.load)` shows the same text for the version you have installed.
Which `years`, `ufs` and `months` each dataset takes is in
[Bases e argumentos](datasets.md). To install, follow the
[installation guide](guides/getting-started.md).

## For researchers

Four calls cover an analysis from download to citation:

```python
import omnisus as sus

dados = sus.load("sim_obitos", years=[2023], ufs=["RR"])        # rows, codes as published
dados = sus.label("sim_obitos", dados, columns=["sexo", "racacor"])  # + sexo_rotulo, racacor_rotulo
sus.check_columns("sim_obitos", dados)                           # can I trust each column?
with sus.LakeReader() as lake:
    print(sus.cite(lake, dataset="sim_obitos").text)             # files, SHA-256, snapshot
```

- `load` downloads what DATASUS publishes into the lake ([where it
  lives](guides/getting-started.md#2-where-the-lake-lives)) and returns the rows. A second call
  downloads nothing. When the files are validated sources it also adds harmonised
  categories (`idade_anos_completos`, `sexo_categoria`, `<date>_data`); otherwise it
  warns which were left out (see [ADR 0003](decisions/0003-harmonised-categories-only-for-validated-sources.md)).
- `label` puts the dictionary's label next to each code; a code the dictionary does
  not know gets no label.
- `check_columns` reports, per column, empties, unlabelled codes and date ranges.

::: omnisus.load
::: omnisus.label
::: omnisus.check_columns
::: omnisus.cite

## Discovery

Ask the server what exists before deciding what to import.

::: omnisus.available
::: omnisus.available_releases
::: omnisus.browse
::: omnisus.FtpEntry

## Releases

Some datasets publish final and preliminary files under the same names in two
directories (a row's `prelim_dir`). `available_releases` reports which
directory each scope came from; `outdated` compares the files a lake has
published against what the server lists today — by path, and by size or
server mtime when recorded — and returns the scopes that differ (a moved
directory, or a same-name republish), to be re-imported with
`import_dataset(..., policy="replace")`. See
[reprocessing and maintenance](guides/reprocessing-and-maintenance.md).

::: omnisus.outdated

## Planning

Planning is composition: build a list of scopes any way you like and hand it
to `import_dataset`. There is no planner flag on the Python API.

::: omnisus.scopes_for
::: omnisus.ALL_UFS

## Importing

The FTP importers return `ImportReport`; inspect `report.failed`, `report.skipped`
and `report.ok`. `import_ibge_populacao` returns `list[ImportResult]`, while
`import_cnes_master` returns the number of records written.

`import_research` is the researcher door: it requires `run_id` and defaults to
`policy="skip_same"`. It refuses `append`. `import_dataset` remains the operator
API and still appends unless a policy is set.

`ImportAbortedError` interrupts an FTP run when it cannot safely continue.
Inspect its `report` for determined outcomes and `unresolved` for
`(input_index, ScopeKey)` pairs before retrying. Imports append data unless an
explicit replay `policy` is selected. FTP imports accept `append` (default),
`skip_same`, `error_if_exists` and `replace`. See
[reprocessing and maintenance](guides/reprocessing-and-maintenance.md) for legacy
scope restrictions, run IDs and byte budgets.

Every import function also runs from inside a notebook cell, where an event loop
is already running. Importing `cnes_estabelecimentos` by any function refreshes the
`aux_cnes` view.

::: omnisus.import_dataset
::: omnisus.import_research
::: omnisus.import_ibge_populacao
::: omnisus.import_cnes_master
::: omnisus.import_sigtap
::: omnisus.available_sigtap

## Vocabularies

The bootstrap tables (`aux_uf`, `aux_municipios`, `aux_cid10`, `aux_ocupacoes`,
`aux_paises`) come from DATASUS's `SIM/CID10/TABELAS`; the CBO 2002 codes in
`aux_ocupacoes` come from `CBO2002.CNV` in `SIM/CID10/TAB/OBITOS_CID10_TAB.zip`. Each
file is hashed in the source registry. Nothing joins at import: `reference_join_sql` writes the `LEFT JOIN` a
field's dictionary declares. See [vocabularies](sources/vocabularios.md).

::: omnisus.reference_join_sql

## Dictionaries, labels and harmonised categories

Each dataset ships a dictionary: fields, labels, code maps and audited analytical
rules. `display_row` is the per-row door to the same lookup as `label`.
`analytical_projection` returns the SQL behind `load`'s harmonised categories, for
queries you write yourself; take the schema and the sources from the snapshot you
query. See [consumption](dicionario/consumo.md).

::: omnisus.describe_dataset
::: omnisus.display_row
::: omnisus.analytical_projection
::: omnisus.SourceContext

## Results

`ImportResult.bytes_written` measures the temporary staging Parquet file, not
final lake storage growth. `snapshot_id=None` can mean an uncommitted result or
an unavailable snapshot ID; it does not alone establish whether a write committed.
Managed FTP results also carry `run_id`, `batch_id` and `publication_id`; IBGE
results carry their canonical `publication_id`.

::: omnisus.sources._base.ImportReport
::: omnisus.sources._base.ScopeOutcome
::: omnisus.sources._base.ImportResult
::: omnisus.sources._base.ScopeKey
::: omnisus.DeletionResult

## The lake

`Lake.local()` and `LakeReader()` without a target open the default lake, in the
folder set by `set_lake_dir` ([where the lake lives](guides/getting-started.md#2-where-the-lake-lives)).
Pass a target such as `ducklake:/path/omnisus.ducklake` for another lake.
Local handles enforce a cooperative writer lock for their lifetime.
Use `Lake.transaction()` for managed writes; raw SQL
transaction control is outside this contract. Managed transactions cannot nest.

To read, open a `LakeReader` on the same target: it attaches the catalog
read-only, takes no lock, creates nothing and sets no option, so it runs
alongside an import. Pass `snapshot_id` to pin the session; without it every
statement reads the latest committed snapshot.

```python
import omnisus as sus

with sus.LakeReader() as reader:
    latest = reader.snapshots()[-1]["snapshot_id"]
    rows = reader.connect().execute("SELECT count(*) FROM lake.sim_obitos").fetchone()

with sus.LakeReader(snapshot_id=latest) as reader:
    ...  # every statement here sees exactly that snapshot
```

```python
import omnisus as sus
import polars as pl

with sus.Lake.local() as lake:
    with lake.transaction() as receipt:
        result = lake.ingest("example", pl.DataFrame({"id": [1]}).lazy())
        assert result.snapshot_id is None
    assert receipt.committed
    print(receipt.snapshot_id, result.rows)
```

The receipt's `snapshot_id` may remain `None` after a successful commit when no new snapshot was created or the lookup was unavailable.
See [Architecture](architecture.md) for rollback and recovery boundaries.

`Lake.publications(run_id=...)` reads the durable source-publication manifest;
each row carries `scope`, the `ScopeKey` the package wrote (`None` for a shape
this version does not write), alongside the raw `scope_json`.
`Lake.attempts(run_id=...)` reads separately recorded known failures.
`Lake.ingest_parquet` appends a staging file directly. `Lake.publish_scope` adds
scope validation, source identity and replay policy to that write.
`Lake.delete_scope(table, scope)` removes one source scope and retires every
publication within it in the same transaction; a yearly scope on a monthly
table covers all its months. `import_ibge_populacao` and `import_cnes_master` do not
take part in this manifest — see their docstrings for how each reconciles.

`Lake.optimize(table)` merges adjacent files. `Lake.expire_snapshots` and
`Lake.cleanup_files` take `older_than` as a timezone-aware datetime and default
to `dry_run=True`. Each returns a list of result dictionaries.

::: omnisus.set_lake_dir
::: omnisus.Lake
::: omnisus.LakeReader

## Research citations and joins

`import_research` and `cite` are above. `cite` reads the publication manifest (or
`ibge_population_manifest`) and returns Portuguese text matching the
[reproducibility guide](pesquisa/reprodutibilidade.md). `latest_snapshot_id`
is the newest catalog snapshot. Municipality helpers take the leftmost 6 or 7
digits; they do not pad and they do not rewrite stored columns.

::: omnisus.Citation
::: omnisus.citation_from_publications
::: omnisus.latest_snapshot_id
::: omnisus.municipality_join_key
::: omnisus.municipality_join_key_sql

## Registry

`datasets()` lists every curated FTP dataset; `products()` covers every importer
family except SIGTAP: the FTP datasets and the two families outside the registry
(`ibge_populacao`, `cnes_master`). It states, per family, the scope fields, accepted
policies, how an interrupted run is reconciled and whether `available()` applies. Year rules for IBGE remain in
`omnisus.sources.ibge.products` (`CENSUS_YEARS`, `ESTIMATE_UNAVAILABLE_YEARS`);
an estimate is importable only as its latest edition, so there is no floor year.

::: omnisus.Dataset
::: omnisus.resolve
::: omnisus.datasets
::: omnisus.products
::: omnisus.Product

## Errors

Lake transaction errors are imported from `omnisus.lake`. A
`CommitOutcomeUnknown` means the COMMIT raised and the handle is unusable;
inspect the catalog before retrying. The FTP runner wraps transaction state
failures in the top-level `ImportAbortedError` with partial progress.
`CatalogAttachError` means the catalog could not be opened at all: `.stage`
says which statement failed, and for a remote catalog the message never
carries the connection string.

::: omnisus.ImportAbortedError
::: omnisus.CatalogAttachError
::: omnisus.lake.TransactionStateError
::: omnisus.lake.CommitOutcomeUnknown
::: omnisus.FtpPathNotFound
::: omnisus.FtpUnavailable
