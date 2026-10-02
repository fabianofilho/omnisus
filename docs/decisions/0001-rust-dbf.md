# 0001 — Rust DBF Crate Decision

**Date:** 2026-05-02
**Status:** Implemented — package `native/omnisus-dbf`, a default dependency since October 2026

This ADR records the May 2026 measurements and roadmap decision. Its benchmark
numbers and proposed v0.2.0 work are historical, not current performance
guarantees or a release commitment. A separate optional extension is now implemented
in `native/omnisus-dbf`; Python remains available. See
[Architecture](../architecture.md) for the implemented pipeline and the
[validation report](https://github.com/raphaelfh/omnisus/blob/main/evidence/rust-dbf-validation.md) for measured results.

## October 2026: default dependency

`omnisus-dbf` 0.2.0 is on PyPI with abi3 wheels for Linux x86_64, macOS arm64/x86_64
and Windows x86_64, each tested on CPython 3.12–3.14 by `native.yml`. `omnisus`
depends on it on those platforms through an environment marker, so no install needs
a Rust toolchain; other platforms keep the Python decoders. The `auto` backend
picks Rust when the module is installed.

## September 2026 implementation

The implementation keeps a small PyO3/Arrow package in this repository and a
single shared staging writer. It decodes C/N bytes directly rather than using
`dbase::FieldValue`, whose f64 numeric representation and empty-string behavior
do not preserve the existing contract. Reader batches may have different null
schemas, reconciled by the existing IPC spool. Unsupported metadata falls back
only before iteration; corruption and late failures never trigger a retry.

The source-publication identity remains semantic so installing an equivalent
backend does not invalidate `skip_same`. The measurements below remain an
unchanged historical record.

## Context

The design included a profile-then-Rust gate: if DBF parse
dominates >40% of the wall-clock for the DBC→DBF→Polars pipeline,
implement a small Rust extension package (`omnisus-dbf`) using PyO3 +
the `dbase` crate to deliver Arrow batches directly.

`dbfread2` is the only Python-native step in the pipeline; everything
else (DBC decompress, Polars materialize, Parquet sink, DuckLake INSERT)
runs through Rust/C++ already.

## Profile data

Captured against `tests/fixtures/dbc/sinasc_rr_2022_mini.dbc`
(626 KB DBC, 13 091 records — the largest fixture in the repo).
Run on Apple Silicon, Python 3.13, 5 iterations averaged.

| Stage | Time/iter | Share of parse pipeline |
|---|--:|--:|
| `datasus_dbc.decompress_bytes` (Rust) | 16.3 ms | 6.0% |
| `dbfread2.DBF` parse (pure Python) | **229.5 ms** | **84.2%** ⚠ |
| `pl.DataFrame` materialize | 26.8 ms | 9.9% |
| **Total parse pipeline** | **272.6 ms** | 100% |

Full-pipeline benchmark (parse + Polars `sink_parquet` + DuckLake `INSERT`):

| Benchmark | Median | Min | Max |
|---|--:|--:|--:|
| `bench_dbf_parse_sim` | 94.1 ms | 89.8 ms | 97.1 ms |
| `bench_full_pipeline_sim` | 135.5 ms | 135.0 ms | 151.1 ms |

Note: SIM RR 2023 fixture is small (~3 300 records); the SINASC fixture
is the bigger one used for the share-of-time measurement.

## Decision

**Option B applies — but Rust crate is deferred to v0.2.0.**

DBF parse at **84% of the parse pipeline** clearly exceeds the 40% gate
threshold. A PyO3-bound Rust DBF reader (over the `dbase` crate) producing
`pa.RecordBatch` directly should give an estimated 5–10× speedup on the
parse step, which would shrink the parse pipeline from ~270 ms to ~70 ms
on this fixture (~3.5–4× total). For SIM nacional (~30 M records) the
absolute saving compounds: minutes → seconds.

We *defer* the Rust work to v0.2.0 for these reasons:

1. **v0.1.0 is end-to-end functional** with `dbfread2`. The parse pipeline
   is fast enough that real-world wall-clock is dominated by FTP fetch
   for the typical (uf, year) scope. The benefit is largest at full
   national scale, which v0.1.0 doesn't claim to optimize.
2. **A Rust crate is its own package** (a separate, pip-installable
   `omnisus-dbf`, plugged in via try-import). It fits cleanly into the
   v0.x roadmap without coupling to v0.1.0's API.
3. **Real bottleneck verification at scale** — before investing in Rust, we
   want to measure on a SIM SP nacional (`~3 GB DBC`) to confirm the share
   stays >40% under realistic load. This benchmark needs the full lake
   path (not just parse) to be representative.

## Consequences

- **For v0.1.0:** ship with `dbfread2`. Pipeline works end-to-end. No
  blockers.
- **For v0.2.0+:** open follow-up to create `omnisus-dbf` separate
  package. PyO3 + `dbase` crate, ~300 LOC target. Drop-in via try-import
  in `omnisus.sources.datasus_ftp.parse`:

  ```python
  try:
      from omnisus_dbf import dbf_bytes_to_arrow
  except ImportError:
      dbf_bytes_to_arrow = None  # fall back to dbfread2 path
  ```

- **Profile cadence:** re-run this benchmark after each major Polars/
  DuckLake bump. If `dbfread2` ships an FFI-backed parser, re-evaluate
  whether the Rust crate is still needed.

## References

- [`dbase` crate (Rust)](https://github.com/srenauld/dbase)
- [PyO3 user guide](https://pyo3.rs)
- [`dbfread2` GitHub](https://github.com/ninyawee/dbfread2)
