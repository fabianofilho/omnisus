# Release procedure

## Native package

`native/omnisus-dbf` provides the Rust DBF reader and DBC decompressor. It
builds independently of the main Hatchling package. Its version has one home
in `Cargo.toml`; Maturin exposes that version to Python. The pinned toolchain
and `Cargo.lock` are committed. Build with:

```bash
uv build native/omnisus-dbf --wheel --out-dir dist/native
uv build native/omnisus-dbf --sdist --out-dir dist/native
```

One abi3 wheel per platform (Linux x86_64, Windows x86_64, macOS arm64/x86_64)
serves CPython 3.12 and later; it is smoke-tested on 3.12, 3.13 and 3.14. The
`native.yml` workflow produces tested artifacts on pull requests and main pushes
that change native-related paths (listed in its triggers), on manual dispatch and on
`dbf-v*` tags, and `release.yml` runs it for every `v*` tag to test the native
wheels at the tagged commit. Only a `dbf-v*` tag publishes them (below). Every
native-only installation must use binary dependencies and pass outside the
checkout.

`omnisus` depends on `omnisus-dbf` from PyPI on the platforms with a wheel
(Linux x86_64, macOS, Windows x86_64) and decodes DBF and DBC in pure Python
elsewhere. The main wheel stays `py3-none-any`.

A `dbf-v<version>` tag publishes the native wheels and sdist to PyPI from
`native.yml` once repository variable `PUBLISH_DBF_TO_PYPI` equals `true` and
its Trusted Publisher exists (project `omnisus-dbf`, owner `raphaelfh`,
repository `omnisus`, workflow `native.yml`, environment `pypi-dbf`); the job
checks the tag against `Cargo.toml` and publishes only artifacts that passed
the complete matrix. `v<version>` continues to identify the main package. Raise
the main package's `omnisus-dbf` lower bound and `uv.lock` only after the new
native version is on PyPI; an unpublished dependency must not break installs.

## Main Python package

A `v<version>` tag publishes `omnisus` to PyPI. Preparing a local artifact does
not publish it or authorize a tag/push.

```bash
uv build --wheel --sdist --out-dir dist
```

The version has one home, `src/omnisus/_version.py`. Update the changelog and
lockfile with it, and the `omnisus==<version>` pin that `notebooks/colab.ipynb`
and the PEP 723 header of every notebook install (tests check both). The docs
site reads the version at build time. Validate the candidate wheel outside the
checkout, including public metadata, packaged evidence and analytical
projections, before release.

After the release is authorized, tag that reviewed commit with `v<version>` and
push the specific branch/tag. `release.yml` checks the tag, builds wheel/sdist
once and retains them with checksums as the `distribution` workflow artifact.
The same wheel passes the binary-only installation matrix on Python 3.12–3.14,
Linux, macOS and Windows; only then does the `publish` job upload it to PyPI.
That job runs when repository variable `PUBLISH_TO_PYPI` equals `true`, through
a Trusted Publisher (project `omnisus`, owner `raphaelfh`, repository
`omnisus`, workflow `release.yml`, environment `pypi`). No token is stored in
this repo. The notebooks pin a version that exists only after this job, so tag
right after merging the release.

Attach the same artifacts to the GitHub release:

```bash
gh run download <run-id> -n distribution -D dist
gh release create v<version> dist/*.whl dist/*.tar.gz dist/SHA256SUMS
```

## Supported Python

`requires-python` is `>=3.12`. The wheel-only install gate in `test.yml` and
`release.yml` installs the built wheel with `--only-binary=:all:` on 3.12, 3.13
and 3.14 and must pass; no dependency needs a Rust toolchain.
