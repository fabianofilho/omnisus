"""Trava o conteúdo de cada `x-version` dos dicionários em `versoes.json`.

`src/omnisus/data/dicionarios/versoes.json` guarda, por dicionário, o SHA-256 do
conteúdo de cada `x-version` já publicada: o YAML lido, sem a chave `x-version`, em
JSON canônico (`omnisus.metadata.canonical_json`), para que aspas, posição da linha
ou fim de linha CRLF não mudem o hash. A versão atual de um dicionário que falta no
arquivo é acrescentada; uma versão já travada nunca muda de hash, e o script para se
o conteúdo mudou sem trocar a `x-version`. As entradas antigas ficam para sempre, então
dois pull requests que travam a mesma versão do mesmo dicionário conflitam no Git
(issue #25). O arquivo só cresce: a `x-version` atual é sempre a maior travada, e um
conflito nele se resolve trocando de novo a versão e rodando o script, nunca editando ou
apagando entradas à mão. Uma chave repetida, um dicionário sem YAML ou um YAML sem
`x-version` também param o script.

Rodar de novo não muda nada; `--check` falha se o arquivo mudaria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from omnisus.metadata import canonical_json

ROOT = Path(__file__).resolve().parents[2]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"
LOCK = DICIONARIOS / "versoes.json"


def digest(raw: dict[str, Any]) -> str:
    """SHA-256 of a loaded dictionary without its top-level x-version."""
    content = {k: v for k, v in raw.items() if k != "x-version"}
    return hashlib.sha256(canonical_json(content)).hexdigest()


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    repeated = sorted({k for k in keys if keys.count(k) > 1})
    if repeated:
        raise ValueError(f"versoes.json repeats {repeated}; bump x-version instead of merging")
    return dict(pairs)


def load_lock(text: str) -> dict[str, dict[str, str]]:
    """The lock, refusing a key repeated at any level (json.loads would keep the last)."""
    lock: dict[str, dict[str, str]] = json.loads(text, object_pairs_hook=_no_duplicates)
    return lock


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def generate(dicionarios: Path = DICIONARIOS, lock_path: Path = LOCK) -> str:
    """New lock text: the current version of every dictionary added, old entries kept."""
    lock = load_lock(lock_path.read_text(encoding="utf-8"))
    paths = {p.stem: p for p in dicionarios.glob("*.yaml")}
    unknown = sorted(set(lock) - set(paths))
    if unknown:
        raise ValueError(f"versoes.json names dictionaries without a YAML: {unknown}")
    for name, path in paths.items():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "x-version" not in raw:
            raise ValueError(f"{path.name} has no x-version")
        version, sha = str(raw["x-version"]), digest(raw)
        versions = lock.setdefault(name, {})
        if versions.setdefault(version, sha) != sha:
            raise ValueError(
                f"{name}: content changed but x-version {version} is locked to another "
                "content; bump x-version"
            )
        highest = max(versions, key=_version_key)
        if highest != version:
            raise ValueError(
                f"{name}: x-version {version} is below the locked {highest}; x-version only grows"
            )
    out = {
        name: {v: lock[name][v] for v in sorted(lock[name], key=_version_key)}
        for name in sorted(lock)
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="falha se algo mudaria")
    args = parser.parse_args()
    try:
        text = generate()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    changed = LOCK.read_text(encoding="utf-8") != text
    if args.check:
        if changed:
            print(
                f"desatualizado: {LOCK.relative_to(ROOT)}; rodar uv run python scripts/metadados/travar_versoes.py"
            )
        return 1 if changed else 0
    if changed:
        LOCK.write_text(text, encoding="utf-8")
    print(f"{LOCK.relative_to(ROOT)} {'atualizado' if changed else 'sem mudança'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
