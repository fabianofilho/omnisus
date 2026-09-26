# Architecture

The current implementation combines a DATASUS FTP registry, source-specific
importers, and a shared DuckLake writer. The decisions behind it are in the
[ADRs](decisions/0001-rust-dbf.md).

## Registry and importers

A dataset row may declare `prelim_dir` alongside its `ftp_dir` — DATASUS
publishes some families (SIM, SINASC, SINAN) as final and preliminary files
under the same names in two directories, and the layout does not change at
that boundary. `directories()` returns every directory a row is published in;
`available_releases()` reads all of them and reports which release (`final`
or `prelim`) each scope came from, raising if the server lists the same scope
in both. Every FTP-imported row carries the reserved `_source_release` column
next to `_source_ano`/`ano`/`uf`/`mes`, and `Lake.publications()` exposes the
same fact as `release`. `outdated(dataset, lake=lake)` compares the files
recorded on each active publication with what the server lists today — by
path, and by size or server mtime when recorded — and returns the scopes
that differ, to be re-imported with `policy="replace"`.

National datasets (the SINAN agravos `sinan_chagas`, `sinan_hanseniase` and
`sinan_tuberculose`, and the SIM subsets `sim_obitos_fetais`, `sim_obitos_externos`,
`sim_obitos_infantis` and `sim_obitos_maternos`) use
`ScopeKey(uf=None, ano=year)` and a reserved `_source_ano` publication column.
They preserve original geography and dates instead of assigning an artificial
UF. Source identity is declared per row in the dictionary's `x-identity` block
(`year_column`, and optionally `code_column`/`code`) and checked once, by the
*mode* of those columns over the whole file, before the shared transaction —
not a per-record rule, so records that carry an off-year or mismatched code
are preserved rather than dropped. State scopes keep their existing manifest
identity. National and state publications cannot share a table. FTP
publication manifests also retain the acquired source URI; older rows have
unknown (NULL) URIs. See [the Chagas contract](sources/sinan_chagas.md).

- **`Dataset`** is an immutable, keyword-only DATASUS FTP registry row. It holds
  identity, FTP location, cadence, partitioning, coverage and a dictionary path.
  The registry covers SIM (with CID-9 and the national subsets), SINASC, SIH,
  SIA/APAC, the CNES file groups and SINAN (Chagas, Hanseníase, Tuberculose);
  [datasets](datasets.md) lists every row. Callers can also construct a `Dataset`
  with their own dictionary.
- **Importers** orchestrate fetching, parsing and writing. IBGE population and
  CNES master data use dedicated HTTP importers; they are not FTP registry rows.
  `import_dataset` refreshes the `aux_cnes` view after every
  `cnes_estabelecimentos` import (`_AFTER_IMPORT`), whichever caller started it.

## DATASUS data flow

```text
bounded concurrent FTP fetches -> one parse/write consumer
  -> dbc.decompress_bytes (Python, or optional Rust) -> complete DBF bytes
  -> Python dbfread2 or optional Rust reader -> bounded Arrow batches -> temporary IPC spool
  -> reconcile batch schemas -> temporary Parquet (Snappy)
  -> managed transaction: schema + scope policy + data + manifest -> COMMIT
```

The parser checks DBF payload length and parsed record counts against the DBF
header before publishing staging. Both DBC decoders reject a declared DBF header
shorter than 33 bytes (`InvalidDbcError`), the size below which those checks
cannot read the header. Batches contain at most 100,000 records and
are spooled to disk; the runner does not concatenate every batch into a scope
DataFrame. A second pass writes the reconciled schema to Parquet. The legacy
LazyFrame parser remains available but materializes its result for compatibility.

Staging lowercases column names and trims the spaces some descriptors pad them
with (`PSRR2401` spells `TIPPRE` plus two spaces). It then adds the partition
columns (`ano`, `uf`, `mes`, and `_source_ano`/`_source_release` for national
files). A file column with a partition's name (ER's own `ANO` and `MES`) is
replaced only if it holds the scope's value in every row, compared as trimmed
text or, for `ano` and `mes`, as a number; otherwise the file is refused. A file
column named `_source_ano` or `_source_release` is always refused.
This is not a constant-memory pipeline: decompression still creates the complete
DBF. Before receipt, each scope reserves its files' listed sizes from a
configurable byte budget and retains them through queueing and consumption.
Cancellation shuts down FTP sockets and waits for the worker before releasing
its reservation. A DNS/connect stage without an available socket can still
require its timeout to finish.

New columns widen the lake table; absent columns become NULL through
`INSERT BY NAME`. Existing types must match or allow a lossless widening within
the same signed-integer, unsigned-integer or floating-point family. Incompatible
families and decimal changes fail before insertion. The staging parser also
rejects incompatible values before Arrow inference can erase information.
Previously coerced values require an explicit source rebuild to recover.

### Optional native package

`native/omnisus-dbf` builds a separate `omnisus_dbf` Python extension using
PyO3 and Arrow, providing both the DBF reader and the DBC decompressor. The main
package keeps its pure-Python wheel. Set `OMNISUS_DBF_BACKEND=rust` to require
native DBF decoding, `python` to use dbfread2, or `auto` to use Rust when
installed and the DBF metadata is supported. `OMNISUS_DBC_BACKEND` selects the
DBC backend the same way (`rust`, `python` or `auto`). The default for both is
`auto`, so installing the extension enables them automatically.

The native reader supports C/N fields and the DBF layouts covered by the committed
fixtures. It preserves empty strings, strict encodings and int64 precision.
Other field types use Python in auto mode. Auto fallback is allowed only for an
absent optional package or unsupported metadata before iteration; an installed
but broken module, corrupt data or a late decoding error is surfaced.

Both adapters deliver closable RecordBatch iterators to the same staging writer.
Lowercasing, partitions, null/schema reconciliation, IPC spooling and atomic
Parquet replacement remain in Python. Rust owns its input buffer and each Arrow
batch owns its exported data; the initial DBF copy is included in resource
measurements. This does not make DBC decompression incremental.

`dbc-staging-v1:<dictionary hash>` identifies output semantics rather than the
execution language. Backend and native package version are logged separately.
Changing between equivalent backends therefore preserves `skip_same`; a change
in decoding semantics requires a new parser contract version.

`Lake.ingest` remains append. FTP imports use `Lake.publish_scope`, with `append`
as the default and explicit `skip_same`, `error_if_exists` and `replace` policies.
Scope, source hash, parser/dictionary version, run and batch IDs commit with the
data in `_omnisus_publications`, and each file's URI, size and server time in
`_omnisus_sources`. Before downloading, `skip_same` skips a scope whose one
managed publication recorded the same listed files (path, size, server time)
under the current parser version; any difference downloads and compares SHA-256.
A file rewritten with the same size in the same minute is the accepted blind
spot; `replace` re-imports it. Replacement validates a nonempty complete scope
and its schema before deleting exactly its UF/year/month, regardless of physical
partitioning. Legacy rows without a trustworthy manifest require inventory or
rebuild before managed replay. See [reprocessing](guides/reprocessing-and-maintenance.md).

## Transaction boundaries and recovery

`Lake.ingest` opens a managed transaction when called directly and returns after
commit. Inside `with lake.transaction() as receipt:`, multiple ingests share the
transaction. Their `ImportResult.snapshot_id` values stay `None` until the
context commits. The receipt then records `committed=True` and, when available,
the committed snapshot ID. A successful commit can still have no snapshot ID
if the transaction made no snapshot change or the follow-up lookup failed.

The FTP runner defaults to six concurrent fetches and batches of 24 consumed
scopes per transaction. Set `batch_size=1` on `import_dataset` for per-scope
transactions. Fetch failures are reported independently. So is a scope rejected
before it writes (decoding, DBF integrity, identity): it is `ingest_failed` and
the batch goes on, because the transaction holds nothing of it. A write failure
rolls back the current batch, marks its attempted writes failed, and allows later
scopes to continue. Previously committed batches remain.
Results preserve input order, including repeated scope values; batching follows
fetch completion order.

A transaction state failure stops the runner with `ImportAbortedError`.
`error.report` contains determined outcomes; `error.unresolved` contains
`(input_index, ScopeKey)` pairs requiring inspection. A failed COMMIT raises
`CommitOutcomeUnknown` in the lake API and invalidates the handle. Inspect the
catalog before retrying unresolved writes: a raised COMMIT does not prove that
nothing was committed.

Supply a `run_id` before an import and reopen the lake to query
`Lake.publications(run_id=...)` after an unknown commit. A skip that depends on
an uncommitted publication shares its commit outcome. Determined failures from
completed runs are recorded separately after rollback and can be read with
`Lake.attempts`; they do not claim a failed transaction wrote data.

Local handles acquire a cooperative process lock on the canonical catalog path
before opening DuckDB. A second handle fails immediately; close releases the
lock, including after construction errors. The lock covers maintenance too, but
external SQL clients and noncooperating writers do not participate. The lock file
is retained to avoid splitting ownership across different inodes. Network
filesystems and cloud writers need external exclusivity.

Managed transactions
cannot nest, and the FTP runner rejects an already active transaction. Raw SQL
`BEGIN`/`COMMIT` through `Lake.connect()` is outside this contract. SQLite and
Postgres catalog targets are accepted; the presence of a Postgres target does
not establish concurrent-writer recovery guarantees for these importers.

IBGE population validates an explicit product and edition against its metadata,
periods and territorial universe. Canonical data and provenance commit together,
and each returned `ImportResult` carries the publication ID. It does not use the
FTP report/recovery loop. Historical estimates without edition-specific universes
are rejected. See the [IBGE source contract](sources/ibge_populacao.md).

CNES master data is
fetched and validated before its table upsert and `aux_cnes` refresh commit in
one transaction, and the importer returns a row count. After a
`cnes_estabelecimentos` FTP import, `import_dataset` refreshes the view through
`_AFTER_IMPORT`, for every caller, in a separate operation. Auxiliary
bootstrap tables are replaced individually unless the caller supplies an outer
managed transaction.

`aux_cnes` selects a whole row from the latest CNES-ST competence, preserves its
NULLs and rejects conflicting ties. Identical ties collapse in the view. The
master's current name is enrichment collected separately, not a historical name.

## Maintenance

`Lake.optimize` calls DuckLake's adjacent-file merge. Snapshot expiration and
physical old-file cleanup are separate operations with timezone-aware cutoffs
and simulation by default. PostgreSQL target parsing extracts only
`storage` and forwards other connection parameters unchanged; SQL identifiers
and literals are quoted centrally.

## Runtime and layout

Python 3.12 or newer is required. The DuckDB connection factory installs and
loads the `ducklake` extension when opening a lake; an environment without the
extension cached needs access to the extension repository. Dependency versions
are declared in `pyproject.toml`.

```text
src/omnisus/
| __init__.py   - the public API (odb.*)
| lake/         - catalog targets, connections, managed transactions, writes
| sources/      - per-family fetch and parse
| | datasus_ftp/ - registry, inventory, bounded import runner
| | ibge/       - population HTTP importer
| | cnes/       - CNES-specific importers
| | sigtap/     - SIGTAP procedures by competência
| | medicamentos/ - read-only Hórus stock observation
| transforms/   - Polars helpers and Frictionless dictionary loader
| data/         - YAML schemas and auxiliares-bootstrap.zip
| cli/          - Typer entry point
| metadata.py   - offline metadata from the packaged dictionaries
| products.py   - what the package can import
| research.py   - citation and research imports
```
