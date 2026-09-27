# 0003 — Harmonised categories only for validated sources

**Date:** 2026-09-23
**Status:** Decided

`sus.load` adds harmonised categories (`sexo_categoria`, `idade_anos_completos`, `*_data`)
only when every scope it returns comes from a validated source: a file whose SHA-256 is
listed in the rule's `validated_sources`. For any other scope the columns are absent, and a
warning names the reason. Labels still work for every scope.

We chose this because the one failure a status column cannot see is a code whose meaning
changes: SIH `"3"` means female, and nothing in the value says so. The zero-assumption
policy lets such a fact into code only from a hashed artifact.

## Considered options

- **Apply the rule to every scope and rely on `*_status = 'unsupported'`.** Rejected: that
  catches unknown codes, not known codes with another meaning.
- **Let researchers add validations in a local file.** Rejected: a second source of truth on
  each machine, and not citable.
- **Validate automatically at import.** Rejected: it turns an audit into a runtime default.

## Consequences

Most scopes have no harmonised categories until someone validates them (today SIM RR
2021–2024 and SP 2024, eight SIH scopes, one or two elsewhere; SINASC and SIA have no sex
rule). `scripts/metadados/validar_fonte.py` keeps the cost of validating one more scope to one
command and one PR.
