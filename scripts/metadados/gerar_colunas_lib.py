"""Escreve em cada dicionário DATASUS as colunas que o import acrescenta ao arquivo.

`ano`, `uf`, `mes`, `_source_ano` e `_source_release` não são campos do DBF: o staging
as grava a partir do nome e do diretório do arquivo. `library_columns(dataset)`
(`omnisus.sources.datasus_ftp.library_columns`) diz quais delas cada linha do registro
recebe, e o runner usa a mesma função. Este script declara cada uma no dicionário da
linha, com `type`, `label`, `constraints` e `x-metadata.derivation`, então um campo sem
`derivation` é um campo que o DBF publica. Uma coluna nova vai para o fim da lista de
campos; uma já declarada é reescrita no lugar, e o que o script não gera (`physical_name`,
`physical_type`, claims, issues) fica como estava. `x-decode` e a chave `derivation:`
solta, que nenhum leitor usa, saem.

Rodar de novo não muda nada; `--check` falha se algum dicionário mudaria. Mudar o
conteúdo de um dicionário pede nova `x-version` e `travar_versoes.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from omnisus.sources.datasus_ftp.datasets import REGISTRY, Dataset
from omnisus.sources.datasus_ftp.library_columns import LibraryColumn, library_columns

ROOT = Path(__file__).resolve().parents[2]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"


def _cnv_module() -> Any:
    """`gerar_decode_cnv.py`, whose `replace_field` and dumper this script reuses."""
    script = Path(__file__).with_name("gerar_decode_cnv.py")
    spec = importlib.util.spec_from_file_location("gerar_decode_cnv", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gerar_decode_cnv", module)
    spec.loader.exec_module(module)
    return module


def declared(existing: dict[str, Any] | None, column: LibraryColumn) -> dict[str, Any]:
    """The field entry of `column`: `existing` with the generated keys set, or a new one."""
    kept = {
        key: value
        for key, value in (existing or {}).items()
        if key not in {"name", "type", "label", "constraints", "x-decode", "derivation"}
    }
    meta = dict(kept.pop("x-metadata", {}))
    meta["derivation"] = dict(column.derivation)
    out: dict[str, Any] = {
        "name": column.name,
        "type": column.type,
        "label": column.label,
        "constraints": dict(column.constraints),
    }
    out.update(kept)
    out["x-metadata"] = meta
    return out


def append_fields(text: str, definitions: list[dict[str, Any]], dumper: type) -> str:
    """Add `definitions` after the last entry of the fields list, at its indentation."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.lstrip(" ").startswith("- name: ")]
    if not starts:
        raise ValueError("no field entries")
    last = starts[-1]
    indent = lines[last][: len(lines[last]) - len(lines[last].lstrip(" "))]
    end = last + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith(indent + "  ")):
        end += 1
    while not lines[end - 1].strip():
        end -= 1
    dumped = yaml.dump(definitions, Dumper=dumper, sort_keys=False, allow_unicode=True, width=100)
    block = "".join(indent + line if line.strip() else line for line in dumped.splitlines(True))
    return "".join(lines[:end]) + block + "".join(lines[end:])


def generate_one(d: Dataset, text: str, cnv: Any) -> str:
    """New text of `d`'s dictionary."""
    fields = {f["name"]: f for f in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]}
    added = []
    for column in library_columns(d):
        new = declared(fields.get(column.name), column)
        if column.name not in fields:
            added.append(new)
        elif new != fields[column.name]:
            text = cnv.replace_field(text, column.name, new)
    return append_fields(text, added, cnv._Dumper) if added else text


def generate() -> dict[Path, str]:
    """New text of every DATASUS dictionary."""
    cnv = _cnv_module()
    out = {}
    for d in REGISTRY.values():
        path = DICIONARIOS / f"{d.dictionary or d.name}.yaml"
        out[path] = generate_one(d, path.read_text(encoding="utf-8"), cnv)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="falha se algo mudaria")
    args = parser.parse_args()
    generated = generate()
    changed = [p for p, t in generated.items() if p.read_text(encoding="utf-8") != t]
    if args.check:
        for p in changed:
            print(f"desatualizado: {p.relative_to(ROOT)}")
        return 1 if changed else 0
    for p in changed:
        p.write_text(generated[p], encoding="utf-8")
    print(f"{len(changed)} dicionários atualizados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
