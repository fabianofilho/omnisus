# omnisus-dbf

Optional DBF → Arrow reader and DBC decompressor for `omnisus`.
The main package keeps its Python build backend and does not require Rust.
`omnisus` installs it from PyPI on Linux x86_64, macOS and Windows x86_64. To build
one locally:

```sh
python -m pip install maturin==1.12.6
maturin build --release --locked --manifest-path native/omnisus-dbf/Cargo.toml
python -m pip install native/omnisus-dbf/target/wheels/omnisus_dbf-*.whl
```

```python
from omnisus_dbf import open_reader

reader = open_reader(dbf_bytes, encoding="latin-1", batch_rows=100_000)
try:
    for batch in reader:
        consume(batch)
finally:
    reader.close()
```

```python
from omnisus_dbf import decompress_dbc

dbf_bytes = decompress_dbc(dbc_bytes)  # raises InvalidDbcError on bad input
```

`decompress_dbc` releases the GIL and returns the same bytes as the pure-Python
decoder in `omnisus.sources.datasus_ftp.dbc`. Both reject a declared DBF
header shorter than 33 bytes with the same message.

The reader owns a copy of the input bytes. Parsing and Arrow builders release the
GIL; the official `arrow-pyarrow` bridge exports each batch with owned buffers.
Returned batches remain valid after `close()` or reader destruction. Closing is
idempotent, as is exhaustion. A decoding or conversion error closes the reader.
No Python object is created per record.

API version 2 supports DBF versions 0x03 and 0x30, C/N fields, and strict latin-1,
cp1252, ASCII and UTF-8. Python codec aliases are resolved at open. Character
padding strips only trailing spaces and NUL bytes. Numeric fields attempt exact
int64 before float64, accept Python numeric underscores and decimal comma, and
preserve null-only batches as Arrow null. Integer overflow and mixed integer /
float families fail; the Python staging layer reconciles schemas across batches.
Deleted records do not appear in output. The SIA ABO FoxPro extension header is
skipped after the first real descriptor terminator. Missing descriptor repair is
the responsibility of the shared Python integrity layer before opening a reader.

`UnsupportedDbfError` identifies unsupported formats during synchronous preflight
only. Corruption raises `InvalidDbfError`; content errors retain ValueError,
TypeError, or UnicodeDecodeError categories. Automatic backend fallback belongs
to the main package and is only allowed before iteration begins.
API version 2 adds `decompress_dbc`.

## Reproducible development

Versions were checked against upstream Cargo metadata: arrow-pyarrow 59.2.0
requires PyO3 0.29 and Arrow 59.2; both are pinned exactly. Cargo.lock also pins
transitive dependencies (including arrow-buffer 59.3.0). Upstream Arrow declares
minimum Rust 1.85 and PyO3 declares 1.83. This package declares and tests Rust
1.98.1, including its transitive lockfile; a lower minimum has not been validated.
Maturin 1.12.6 is pinned in the isolated build backend.

Sources: [Arrow bridge](https://docs.rs/arrow-pyarrow/59.2.0/arrow_pyarrow/),
[PyO3](https://docs.rs/crate/pyo3/0.29.0), and
[Maturin mixed layout](https://www.maturin.rs/project_layout.html).

```sh
cargo test --locked --manifest-path native/omnisus-dbf/Cargo.toml
cargo clippy --locked --all-targets --manifest-path native/omnisus-dbf/Cargo.toml -- -D warnings
cargo fmt --manifest-path native/omnisus-dbf/Cargo.toml -- --check
python -m pytest native/omnisus-dbf/tests/test_bindings.py
```

Default Cargo features enable Python linking for Rust tests. `extension-module`
is enabled only by Maturin, avoiding Python symbol linker conflicts in tests.
Use `--no-default-features` for pure Rust checks and fuzzing without Python.
Wheels use the stable ABI (abi3, CPython 3.12 and later) on Linux x86_64, Windows
x86_64 and macOS arm64/x86_64. Free-threaded CPython is not supported.

The package version has one source, Cargo.toml; API_VERSION is independent.
Future native release tags use `dbf-v*`. Build/test wheels and sdist first, then
publish those same artifacts only through a separately authorized release.
Do not add a root-package dependency extra until the native version exists in
the package index. Building an sdist requires Rust; installing a supported wheel
does not.
