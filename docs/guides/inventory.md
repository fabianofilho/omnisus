# Knowing what exists

DATASUS publishes different date ranges for different datasets and states, and
the ranges move. Guessing produces two failure modes: asking for files that were
never published, and silently missing files that were.

Two functions answer the question, at two levels of interpretation.

## `available` — what can I import?

Closed-world. Reads one directory listing and decodes each filename through the
registry, so you get back exactly the scopes this package can import.

```python
import omnisus as sus

sus.available("sim_obitos")                      # matching scopes in the cached/fresh listing
sus.available("sim_obitos", years=range(2020, 2025))
sus.available("sim_obitos", years=[2024], ufs=["SP"])  # same selectors as scopes_for()
sus.available("sih_aih_reduzida", years=[2024], ufs=["SP"], months=[1, 2])
```

`ufs` and `months` select among what the listing has; a national row such as
`sinan_chagas` has neither and raises if you pass them.

Names belonging to other datasets in the same directory are skipped, not raised
on — `SIASUS/200801_/Dados` holds 14 of our 44 datasets side by side.

## `browse` — what is actually there?

Open-world. No decoding, so it reaches data this package does not model (other
SINAN agravos, CIHA, PCE), and any path you like.

```python
sus.browse("/dissemin/publicos/SINAN", depth=2)
```

Recursion is bounded by `depth`, and the walk is sequential. A subdirectory that
cannot be listed is logged and skipped rather than truncating the walk.

## From the command line

```bash
omnisus inventory sim_obitos
omnisus inventory --path /dissemin/publicos/SINAN --depth 2
```

## `available_releases` — which directory is each scope in?

Some datasets (SIM, SINASC, SINAN) publish preliminary files beside the final
ones under the same names, in a second directory declared as the row's
`prelim_dir`. `available_releases(dataset)` reads every directory the row
declares and returns, per scope, which one (`final` or `prelim`) it came from;
`available()` still returns just the scopes, with no release information. The
CLI table shows the same fact in a `Release` column:

```bash
omnisus inventory sim_obitos
```

A scope listed in both directories is a server inconsistency and raises,
rather than being resolved by preference.

## Building the lake from what exists

The point of all this. `--plan inventory` asks the server first and imports only
what it lists:

```bash
omnisus import sim_obitos --plan inventory --years 1996-2024 --ufs RR,AC
```

In Python the same thing is composition — no flag, just a different function
filling `scopes`:

```python
sus.import_dataset("sim_obitos", scopes=sus.available("sim_obitos", years=range(1996, 2025)))
```

The alternative is to plan blindly and let tolerance absorb the gaps:

```python
sus.import_dataset(
    "sim_obitos", scopes=sus.scopes_for("sim_obitos", years=range(2020, 2025), ufs=["RR"])
)
```

Both work. Inventory planning costs one directory listing and avoids opening a
connection per nonexistent file; blind planning costs nothing up front and
reports the gaps as `skipped`.

## Caching

Listings are cached for 24 hours under `OMNISUS_CACHE_DIR` (or the XDG cache
directory). The cache is never authoritative: a miss, a stale entry or an
unreadable file all fall through to the network, and a cache that cannot be
written never discards a listing that already succeeded.

`--plan inventory` always refreshes. A 23-hour-old listing would silently omit a
month DATASUS published this morning, and the run is about to use the network
anyway. Pass `--refresh` to force it for browsing too.

## Reading the report

A normally completed DATASUS-FTP import returns an `ImportReport`.
`import_ibge_populacao` instead returns `list[ImportResult]`, and `import_cnes_master`
returns an integer count:

```python
report = sus.import_dataset("sim_obitos", scopes=sus.available("sim_obitos"))

report.rows          # rows ingested
report.ok            # scopes imported
report.skipped       # outside coverage, missing upstream, or identical managed publication
report.failed        # download, parsing or write failures; inspect each reason
```

Inspect `report.failed`; never the report's truthiness. `omnisus import`
exits 1 for a completed FTP report with failures or for `ImportAbortedError`.
Skipped scopes alone do not fail the run. Invalid arguments and other exceptions
can also produce a non-zero exit status.

## Transactions and interrupted imports

An import commits in batches of scopes. If a transaction fails in a way that leaves
its outcome unknown, the runner raises `ImportAbortedError` with the outcomes it could
determine; do not retry the whole import. What to do next is in
[Inspect an interrupted run](reprocessing-and-maintenance.md#inspect-an-interrupted-run),
and the transaction model in
[Architecture](../architecture.md#transaction-boundaries-and-recovery).
