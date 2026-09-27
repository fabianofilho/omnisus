# Getting Started

Install the package, choose where the lake lives, import a scope and query it.

## 1. Install

Python 3.12 or newer is required. CI runs the test suite on Python 3.13 (Linux and
Windows) and checks that the built wheel installs on 3.12, 3.13 and 3.14.

```bash
python -m pip install "omnisus @ git+https://github.com/raphaelfh/omnisus"
```

### Optional Rust decoder

Each release attaches native wheels of `omnisus-dbf` for Linux x86_64, macOS (arm64,
x86_64) and Windows x86_64:

```bash
python -m pip install omnisus omnisus-dbf \
  --find-links https://github.com/raphaelfh/omnisus/releases/expanded_assets/v0.1.0
```

DBF decoding and DBC decompression default to `auto`: Rust when installed, otherwise
Python. `OMNISUS_DBF_BACKEND` and `OMNISUS_DBC_BACKEND` take `rust`, `python` or
`auto`. `auto` falls back only for an absent extension or unsupported DBF metadata;
corrupt files always fail.

### From a checkout

For development, notebooks and documentation, use the committed lock:

```bash
git clone https://github.com/raphaelfh/omnisus.git
cd omnisus
uv sync --locked --all-extras
```

Opening a lake loads the DuckDB `ducklake` extension; if it is not cached, the
environment needs access to DuckDB's extension repository.

## 2. Where the lake lives

The lake is two things in one folder: the catalog (`omnisus-catalog.sqlite`) and the
storage with the Parquet files (`omnisus.ducklake/`). By default the folder is
`data/raw/` under the working directory. To keep it elsewhere, say so once, at the top
of the notebook; every call without `target` then uses it:

```python
import omnisus as sus

sus.set_lake_dir("~/omnisus")
```

Scripts can set `OMNISUS_DATA_DIR` instead, and CLI commands take `--target`.
`omnisus init` creates the lake and seeds auxiliary tables (UF, municipios, CID-10,
ocupações and países).

### On Colab: keep the lake on Google Drive

Deleting a Colab runtime erases `/content`. Put the lake on Drive and it stays:

```python
from google.colab import drive
drive.mount("/content/drive")

import omnisus as sus
sus.set_lake_dir("/content/drive/MyDrive/omnisus")

dados = sus.load("sim_obitos", years=[2023], ufs=["RR"])
```

Before closing the notebook, run `drive.flush_and_unmount()` so every file reaches
Drive. Write to the lake from one notebook at a time; two sessions writing at once are
not protected.

## 3. Import some data

```bash
omnisus inventory sim_obitos --refresh
omnisus import sim_obitos --plan inventory --year 2023 --ufs RR
```

If the listing has no matching scope, choose one it actually lists. Imports
append data by default: repeating a scope inserts it again. Use `--policy skip_same`
to skip a previously managed publication with the same source and parser version.
Local handles enforce a cooperative single-writer lock.
See [inventory and import results](inventory.md) for skipped scopes, failures
and interrupted imports.

## 4. Query

After the scope has imported successfully:

```bash
omnisus query "SELECT count(*) FROM lake.sim_obitos WHERE ano=2023 AND uf='RR'"
```

Or in Python:

```python
import omnisus as sus

report = sus.import_research(
    "sim_obitos",
    scopes=sus.available("sim_obitos", years=[2023], ufs=["RR"]),
    run_id="sim-rr-2023-01",
)
with sus.LakeReader() as reader:
    snapshot_id = sus.latest_snapshot_id(reader)
    citacao = sus.cite(reader, dataset="sim_obitos", snapshot_id=snapshot_id, run_id="sim-rr-2023-01")
    df = reader.connect().sql(
        "SELECT count(*) AS obitos FROM lake.sim_obitos WHERE ano=2023 AND uf='RR'"
    ).pl()
print(citacao.text)
```

`import_research` skips a scope that is already published with the same source
and parser (`skip_same`). Repeating `import_dataset` without a policy appends
again. Pin `snapshot_id` on a second `LakeReader` if another import may run
after you print the count. Every explicit lake target must start with
`ducklake:`, for example `ducklake:./data/raw/omnisus.ducklake`. A `LakeReader` takes no
writer lock; open `Lake.local` only to write.

## 5. Bigger imports

```bash
omnisus import sim_obitos --plan inventory --years 2020-2024 --ufs SP,RJ,MG
omnisus import sinasc_nascidos_vivos --plan inventory --years 2020-2024
```

A completed FTP import reports every requested position. The CLI exits 1 for
failed scopes or interrupted imports. Inspect an unknown commit before retrying;
see [the transaction contract](inventory.md#transactions-and-interrupted-imports).
The separate [IBGE population importer](../sources/ibge_populacao.md) requires an explicit
product and edition and returns a list of results. For example:

```bash
omnisus import ibge_populacao --year 2022 --census
```

Historical estimates without a verified territorial universe are unavailable.

## Cloud target

Commands that operate on a lake accept `--target/-t`; inventory does not use a
lake. PostgreSQL catalog targets use this form:

```bash
omnisus import sim_obitos --year 2023 --ufs RR \
  --target "ducklake:postgresql://user:pwd@host/db?storage=s3://bucket/lake"
```

The DuckDB connection needs the appropriate catalog and object-storage
credentials. The parser extracts exactly one `storage` parameter and preserves
other PostgreSQL query parameters, including `sslmode`. Percent-encode embedded
query characters in the storage value, or use `Lake.cloud(catalog=...,
storage=...)` in Python to pass the values separately. When the catalog cannot
be opened, `Lake.cloud`/`Lake.local` raise `CatalogAttachError`: `.stage` tells
whether the ducklake extension (`install`), the catalog (`attach`) or the
compression option (`set_option`) failed, and a remote catalog's error never
includes the connection string.
Acceptance tests validate local catalogs; cloud concurrency still requires
external writer coordination. See [reprocessing and maintenance](reprocessing-and-maintenance.md).
