# Reprocessing and maintenance

## Choose a replay policy

FTP imports retain `append` as their default. Choose another policy explicitly
when a scope has already been published through the managed importer:

| Policy | Existing managed scope | Absent scope |
|---|---|---|
| `append` | Append another publication; duplicates remain possible | Publish |
| `skip_same` | Skip only when all active publications have the same source SHA-256 and parser version; otherwise fail | Publish |
| `error_if_exists` | Fail without changing data | Publish |
| `replace` | Validate staging, delete the exact source scope, insert and replace its active manifest in one transaction | Publish |

```python
import omnisus as odb

report = odb.import_dataset(
    "sim_obitos",
    scopes=[odb.ScopeKey(uf="RR", ano=2023)],
    policy="skip_same",
    run_id="sim-rr-2023-review-01",
)
print(report.run_id, report.rows, report.failed)
```

```bash
omnisus import sim_obitos --year 2023 --ufs RR --policy skip_same --run-id sim-rr-2023-review-01
```

Source identity combines the compressed DBC SHA-256 with an explicit staging
parser version and the SHA-256 of what the import reads from the dictionary (its
`encoding` and `x-identity`). Editing labels, code maps or claims does not change it;
a parser algorithm change must bump that version. `skip_same` first compares the server listing (path, size and
server time of each file) and the parser version with the active publication; if
nothing changed, it skips the scope without downloading. Any difference downloads
the file and compares its SHA-256. It does not remove duplicates already created
by `append`.
`replace` requires nonempty staging with every row belonging to the exact scope.
For monthly data this includes UF, year and month, even when the physical table
partition omits UF. Event rows are never deduplicated with `DISTINCT`.

Rows created by older importers or direct SQL have no trustworthy source
manifest. Policies other than `append` reject such scopes. Inventory or rebuild
them explicitly in a separate target before switching; a later append cannot
retroactively certify the old rows. Manifest row counts detect some external
changes but do not audit arbitrary edits that preserve counts. External SQL
writes remain outside the managed contract. IBGE has a separate publication
model described in its [source documentation](../sources/ibge_populacao.md).

## Quando um ano passa de preliminar a final

For a dataset with a `prelim_dir` (SIM, SINASC, SINAN), DATASUS eventually
moves a year from the preliminary directory to the final one under the same
name. Nothing in the lake changes by itself: `outdated(dataset, lake=lake)`
compares the files recorded on each active publication with what the server
lists today and returns only the scopes that differ.

```python
import omnisus as odb

with odb.Lake.local() as lake:
    moved = odb.outdated("sim_obitos", lake=lake)
    odb.import_dataset(
        "sim_obitos", scopes=moved,
        policy="replace", run_id="sim-final-2026",
    )
```

`outdated` is read-only; pass its result to `import_dataset` with
`policy="replace"` and an explicit `run_id`, the same contract as any other
replacement. A scope the server no longer lists at all is a withdrawal, a
different fact, and `outdated` does not return it.

## When DATASUS moves or republishes files

`outdated` also catches a row whose directory moved outright — not just a
year that went from preliminary to final — and a same-name republish (another
size or server mtime at the same path). Compare with `refresh=True` so the
listing isn't served from cache:

```python
import omnisus as odb

with odb.Lake.local() as lake:
    stale = odb.outdated("sinasc_nascidos_vivos", lake=lake, refresh=True)
odb.import_dataset("sinasc_nascidos_vivos", scopes=stale, policy="replace", run_id="sinasc-1996-move")
```

A scope whose recorded source URI differs from where the server lists the file
today is reported even when its bytes did not change, because provenance must name
where the bytes are. Publications without a recorded source are always reported,
since nothing shows they match the server.

## Inspect an interrupted run

```python
import omnisus as odb

try:
    report = odb.import_dataset(
        "sim_obitos", scopes=[odb.ScopeKey(uf="RR", ano=2023)], run_id="sim-rr-2023-review-01"
    )
except odb.ImportAbortedError as exc:
    print(exc.report.rows, exc.unresolved)  # determined outcomes; positions to inspect
    raise
```

Choose and retain `run_id` before starting an import. A failed COMMIT can have
succeeded in the catalog despite the missing acknowledgement. After closing the
unusable handle, reopen the lake and inspect the durable manifest:

```python
with odb.LakeReader() as reader:
    published = {p["scope"] for p in reader.publications(run_id="sim-rr-2023-review-01")}
    failed_attempts = reader.attempts(run_id="sim-rr-2023-review-01")
```

Publications include publication, run and batch IDs, the decoded `scope`,
source hash, parser version, row count and active status. A scope absent from
`published` did not commit under that run ID, because data and manifest commit
in one transaction; choose run IDs you never reuse, or that inference is void.
Superseded manifests remain for inspection.
The failure table records known failures separately after data rollback at the
end of a completed run; a crash or unknown transaction outcome can prevent that
log from being written. Its absence is not evidence of success.

`ImportAbortedError.report` contains determined outcomes and `unresolved` lists
input positions needing inspection. Repeated input positions are preserved.
A skip that depends on an uncommitted publication shares that batch's outcome;
it cannot remain successful after rollback. Reconcile publications before
retrying an unknown commit, rather than appending the entire run again.

## Remove a scope

`Lake.delete_scope(table, scope)` deletes the rows of one source scope and
retires every publication within it (`active = false`) in one managed
transaction, so data and manifest never disagree. A yearly scope on a monthly
table removes all twelve months and retires each month's publication. Rows that
never had a publication are removed as well; when `rows_deleted` exceeds the
retired publications' row sum, unmanaged rows were present.

```python
with odb.Lake.local() as lake:
    result = lake.delete_scope("sih_aih_reduzida", odb.ScopeKey(uf="RR", ano=2023))
    print(result.rows_deleted, result.publications_retired)
```

Retired publications stay in the manifest for inspection; they are not
distinguished from ones superseded by `replace`.

## Migrate a legacy lake

Rows written before publications existed have no manifest and are never
certified in place. Migrate by rebuilding, so provenance exists from the first
import:

1. Choose a new target. Do not point it at the old catalog or storage.
2. Import each dataset with `available()` as the plan and an explicit `run_id`;
   `policy="skip_same"` makes reruns idempotent.
3. Verify `publications()` covers every scope you expect, and compare row counts
   with the old lake where that matters to you.
4. Switch consumers to the new target string. Keep the old lake read-only
   until nothing reads it, then delete it.

The old lake is not modified at any step.

## Coordinate writers and bound downloads

A local `Lake` handle acquires a cooperative lock on the canonical catalog path
before opening DuckDB and holds it until close. Concurrent handles fail with
`WriterBusyError` from `omnisus.lake.locking`. The sidecar `.writer.lock` file
remains after close; its presence alone does not mean a writer is active. Do not
delete it while handles may be running. This protocol also covers maintenance.
External SQL clients, network filesystems and cloud catalogs require external
coordination; distributed recovery has not been validated.

`import_dataset` and `import_research` accept `max_payload_bytes` (default 512 MiB)
and `max_inflight_bytes` (default 1 GiB). CLI equivalents are
`--max-payload-bytes` and `--max-inflight-bytes`, in bytes. The budget must be at
least the payload cap. Before downloading, a scope reserves the sum of its files'
listed sizes (every part of a split month at once) and holds it while the
payloads are queued and consumed; other scopes wait until the budget has room.
A scope with a file listed above the payload cap, or with a total above the
budget, fails with `fetch_failed` without a download, and the reason names the
bytes needed and the limit to raise. A file exceeding the cap still fails during
receipt. Cancellation closes sockets and waits for the worker before releasing
the reservation; a DNS/connect phase without a socket can still take until its
timeout.

These limits cover compressed payloads, not total process memory. Decompression
still materializes the whole DBF. Parsing spools bounded batches to temporary
disk and writes reconciled Parquet in a second pass. Provide enough temporary
disk for DBF, Arrow spool and Parquet.

The reproducible benchmark is `scripts/benchmark_resources.py`. On the measured
132,440-row amplified fixture with 100,000-row batches, peak RSS changed from
1328.5 to 758.0 MiB, elapsed time from 3.705 to 6.571 seconds, and sampled peak
temporary disk from 61.9 to 112.5 MiB. Row order/hash and schema matched. This is
one run per mode on repeated fixture records; it does not establish national
throughput or a universal memory bound. Disk sampling every 5 ms is a lower bound.
The amplified case feeds repeated DBF records directly and bypasses DBC
decompression; its elapsed times do not measure the complete DBC pipeline. A
separate 3,311-row real DBC case exercises decompression in the same benchmark.
The repository's `evidence/benchmark-d6-default.json` records the environment,
corpus hashes and full results.

## Compact, expire history and clean files

These are separate operations:

1. `lake.optimize(table)` merges adjacent files while retaining snapshots.
2. `lake.expire_snapshots(older_than=cutoff)` simulates removing older history.
3. `lake.cleanup_files(older_than=cutoff)` simulates deletion of obsolete files
   eligible under DuckLake's retention rules. It does not expire snapshots.

```python
from datetime import UTC, datetime

cutoff = datetime(2026, 8, 1, tzinfo=UTC)
with odb.Lake.local() as lake:
    compacted = lake.optimize("sim_obitos")
    history_preview = lake.expire_snapshots(older_than=cutoff)
    files_preview = lake.cleanup_files(older_than=cutoff)
```

The new expiration and cleanup APIs default to `dry_run=True`. Pass
`dry_run=False` to execute after selecting a retention cutoff suitable for the
history you need. Cutoffs must include a timezone. Returned dictionaries expose
DuckLake's operation results.

```bash
omnisus lake optimize sim_obitos
omnisus lake expire-snapshots --before 2026-08-01T00:00:00+00:00 --dry-run
omnisus lake cleanup-files --before 2026-08-01T00:00:00+00:00 --dry-run
```

Use `--execute` instead of `--dry-run` to apply expiration or cleanup. Failures
exit nonzero.
