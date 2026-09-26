# AGENTS.md

omnisus imports DATASUS, IBGE and CNES data into a DuckLake lake whose every row
can be cited; the why is in `CONTRIBUTING.md`, which this file overrides.

## Zero-assumption policy

Code and tests cite these rules by number ("AGENTS.md rule 2"); keep the numbering.

1. **Facts come from the server or from a hashed artifact.** A directory,
   filename shape, code list, layout or label enters code or docs only after it
   was read from the live DATASUS server or from an archived file whose SHA-256
   is recorded. "Not published" needs the same evidence as "published".
2. **Tests run on real data.** Semantics are tested against committed excerpts
   of real DATASUS files, each listed with its provenance in
   `tests/fixtures/FIXTURES.md`. Synthetic bytes are allowed only for
   malformed-input cases of the decoder, and the test says so.
3. **TDD, red first.** Every behaviour change starts with a failing test on
   real data. The pull request records the red run. A test that cannot be made
   to fail proves nothing.
4. **No dead code.** Every function, column, script or fixture lands with a
   consumer or a test in the same change, and is deleted with its last
   consumer. Pull requests list their deletions.
5. **Keep it simple and readable.** Prefer one mechanism over two, a plain
   function over a framework, a generated file over a loader feature. Write
   code and docs to be read once by someone who did not write them. If a rule
   needs a diagram to be understood, simplify the rule.

When a rule and a deadline conflict, the rule wins: open an issue for the gap
instead of filling it with a guess.

## Invariants

A change that breaks one of these is a bug, however small the diff.

- An importer writes a scope together with its publication (server path, SHA-256).
- Codes stay as published. A label comes only from the dictionary; an unknown code
  has no label.
- Harmonised categories exist only for validated sources (ADR 0003).
- A user-built `Dataset` takes the same code path as a registry row (ADR 0002).

## Commands

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run marimo check --strict --ignore-scripts notebooks
uv run python scripts/gen_datasets_doc.py --check
uv run pytest -m "not e2e and not perf" -n auto
uv run mkdocs build --strict
```

These are the CI checks. Tests marked `integration` and `e2e` reach the DATASUS
server and are not in pull request CI; run them when a change depends on what the
server lists today.

## Boundaries

**Always**
- Use the terms of `CONTEXT.md` in code, tests and issues.
- Cite a new fact's evidence: a row in `tests/fixtures/FIXTURES.md`, a document in
  `src/omnisus/data/dicionarios/sources/registry.json`, or a file in `evidence/` that
  records the SHA-256 of what it read and that something cites.
- Regenerate generated files instead of editing them: `docs/datasets.md`
  (`scripts/gen_datasets_doc.py`), CNV code maps and SINAN/SIM-subset dictionaries
  (`scripts/metadados/`).
- Write researcher pages (`docs/pesquisa/`, `docs/sources/`, `docs/dicionario/`) in
  Portuguese; technical guides and the API reference in English.

**Ask first**
- A change that contradicts an ADR in `docs/decisions/`; name the ADR.

**Never commit** (this repository and its history are public; check
`git diff --cached` before every commit):
- credentials, tokens, or connection strings with a password (tests use obvious
  placeholders such as `user:dummy`);
- absolute local paths (`/Users/...`, `/home/...`), machine names, or anything else
  that describes a contributor's computer;
- names, modules, plans or tasks of private projects, clients or other repositories;
- personal data. Fixtures are excerpts of public DATASUS files without person
  identifiers; a dataset that names people (CPF, CNS, name), such as CNES `PF`, is
  out of scope;
- agent working files: plans, specs, progress notes, handoffs, review transcripts,
  test or lint logs. Plans and decisions go to GitHub Issues and pull requests; a
  skill that writes a plan or spec to a file writes it to an issue instead.

If something private reaches a pushed commit, deleting it in a new commit does not
remove it: stop and tell the maintainer.

## Agent workflow

Issues and plans live in GitHub Issues (`docs/agents/issue-tracker.md`, labels in
`docs/agents/triage-labels.md`). Use any workflow or skills you like, as long as
the result follows this file.
