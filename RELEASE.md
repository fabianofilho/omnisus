# Release procedure

## Optional native package

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
`dbf-v*` tags, and `release.yml` runs it for every `v*` tag. It
does not publish packages; the release step below attaches its wheels. Every
native-only installation must use binary dependencies and pass outside the
checkout.

`omnisus` does not depend on this package: it decodes DBF and DBC in pure
Python without it. A `dbf-v<version>` tag publishes the native wheels and sdist
to PyPI from `native.yml` once repository variable `PUBLISH_DBF_TO_PYPI` equals
`true` and its Trusted Publisher exists (project `omnisus-dbf`, owner
`raphaelfh`, repository `omnisus`, workflow `native.yml`, environment
`pypi-dbf`); the job checks the tag against `Cargo.toml` and publishes only
artifacts that passed the complete matrix. Use
`dbf-v<version>` for the native package; `v<version>` continues to identify
the main package. Only after the native version is available in the index
should the main package add a `native` extra and update `uv.lock`; an
unpublished dependency must not break base installs. Until then, install the
locally built wheel directly. The main wheel stays `py3-none-any` and Python
decoding remains available.

## Main Python package

The distribution channel is a wheel built from a version tag. **The package is
not published to PyPI, by decision.** Preparing a local artifact does not publish
it or authorize a tag/push.

```bash
uv build --wheel --sdist --out-dir dist
```

The version has one home, `src/omnisus/_version.py`. Update the changelog and
lockfile with it, and the tag that `notebooks/colab.ipynb` installs (a test checks
it). The docs site reads the version at build time. Validate the candidate wheel outside the checkout, including
public metadata, packaged evidence and analytical projections, before release.

After the release is authorized, tag that reviewed commit with `v<version>` and
push the specific branch/tag. `release.yml` checks the tag, builds wheel/sdist
once and retains them with checksums as the `distribution` workflow artifact.
The same wheel passes the binary-only installation matrix on Python 3.12–3.14,
Linux, macOS and Windows. Consumers install the identified wheel and record its
SHA-256; they should not depend on editable neighboring checkouts.

The same run builds the four native wheels (`native-wheel-*` artifacts). Attach them
to the GitHub release with the main wheel, so that `--find-links` on the release page
finds both packages:

```bash
gh run download <run-id> -n distribution -D dist
gh run download <run-id> -p 'native-wheel-*' -D dist/native
gh release create v<version> dist/*.whl dist/*.tar.gz dist/SHA256SUMS dist/native/*/*.whl
```

The PyPI job is skipped unless repository variable `PUBLISH_TO_PYPI` equals
`true`. Changing that channel requires the account owner's decision and a
configured Trusted Publisher (project `omnisus`, owner `raphaelfh`, repository
`omnisus`, workflow `release.yml`, environment `pypi`). A missing publisher is
not an expected failing release step anymore. No token is stored in this repo.

## Supported Python

`requires-python` is `>=3.12`. The wheel-only install gate in `test.yml` and
`release.yml` installs the built wheel with `--only-binary=:all:` on 3.12, 3.13
and 3.14 and must pass; no dependency needs a Rust toolchain.
