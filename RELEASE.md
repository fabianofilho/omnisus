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
`omnisus` accepts exactly one `API_VERSION` and caps `omnisus-dbf` below its next
minor (`<0.3`). Change `API_VERSION` only in a new minor of `omnisus-dbf`, and only
after an `omnisus` that accepts it and caps the following minor is on PyPI. Published
`omnisus` 0.2.0 has no cap, so an `omnisus-dbf` 0.2.x with another `API_VERSION`
would break fresh installs of it.

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

The notebooks pin a version that must already be on PyPI when `main` gets it,
so the tag comes before the merge:

1. Open the release PR: `_version.py`, the CHANGELOG (`## Unreleased` becomes
   `## v<version> — <date>`), the notebooks' pins and `uv.lock`.
2. When its CI is green and the release is authorized, tag the PR's head commit
   and push only the tag:

   ```bash
   git tag -a v<version> -m "omnisus <version>" <head-sha>
   git push origin v<version>
   ```

   `release.yml` checks the tag against `_version.py`, builds wheel and sdist once
   (the `distribution` artifact, with checksums), installs that wheel binary-only
   on Python 3.12–3.14 on Linux, macOS and Windows, and only then runs `publish`.
3. Approve the `pypi` environment in the run. `publish` uploads through a Trusted
   Publisher (project `omnisus`, owner `raphaelfh`, repository `omnisus`, workflow
   `release.yml`, environment `pypi`) when repository variable `PUBLISH_TO_PYPI`
   equals `true`. No token is stored in this repo.
4. Check that `uv pip install omnisus==<version>` resolves.
5. Merge the PR with a merge commit, not a squash, so the tagged commit is on
   `main`. If the PR changes after tagging and nothing was published, delete the
   tag (`git push origin :v<version>`) and tag again.
6. Create the GitHub release with the CHANGELOG section as notes and the same
   artifacts:

   ```bash
   gh run download <run-id> -n distribution -D /tmp/omnisus-v<version>
   gh release create v<version> --title v<version> \
     --notes-file <(awk '/^## v<version>/{f=1;next} /^## v/{f=0} f' CHANGELOG.md) \
     /tmp/omnisus-v<version>/*
   ```

## Supported Python

`requires-python` is `>=3.12`. The wheel-only install gate in `test.yml` and
`release.yml` installs the built wheel with `--only-binary=:all:` on 3.12, 3.13
and 3.14 and must pass; no dependency needs a Rust toolchain.
