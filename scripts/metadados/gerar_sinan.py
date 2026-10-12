"""Copia os campos de `sinan_bloco_comum.yaml` para os dicionários SINAN.

Cada campo de `comum` vai para todo `sinan_*.yaml` que já tem um campo com esse nome;
cada campo de `agravo.<dataset>` vai só para aquele dicionário e, com o mesmo nome,
substitui o de `comum`. O gerador não acrescenta nem remove campos: a lista de campos
continua sendo a do descritor DBF.

Um campo com `x-decode` recebe uma claim `/field/codes` (`method: page-read`) cujas
evidências são as `fontes` do bloco. Antes de escrever, o gerador confere que a união
dos `codigos` das fontes é exatamente o conjunto de chaves de `x-decode` e que cada
código de uma fonte com `membro` está no CNV empacotado, e nenhum campo do bloco está
em `campos` de `sources/cnv/vinculos.json` (o CNV e o bloco nunca escrevem o mesmo
campo). Um campo com claim `page-read` sem entrada no bloco faz o gerador parar: tirar
um mapa do bloco não deixa o mapa antigo para trás. Uma entrada de `comum` que nenhum
dicionário SINAN tem, ou de `agravo.<dataset>` que aquele dicionário não tem, também faz
o gerador parar. `nota` de uma entrada vai para a nota da claim, não para o campo.
Rodar de novo não muda nada; `--check` falha se algum dicionário mudaria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gerar_decode_cnv import CNV, DICIONARIOS, read_member, replace_field

from omnisus.metadata import canonical_json, resolved_codes, sources_registry
from omnisus.transforms.cnv import cnv_map, parse_cnv

ROOT = Path(__file__).resolve().parents[2]
BLOCO = Path(__file__).resolve().parent / "sinan_bloco_comum.yaml"
METHOD = "page-read"
REVIEWER = "scripts/metadados/sinan_bloco_comum.yaml"


def definition_for(
    entry: dict[str, Any], where: str, checked_at: str, membros: dict[str, Any]
) -> dict[str, Any]:
    """The dictionary field an entry of the block describes, with its codes claim.

    `membros` is the packaged-member table of `vinculos.json`, used to read a cited CNV.
    """
    field = {k: v for k, v in entry.items() if k not in ("fontes", "nota")}
    decode = field.get("x-decode")
    if not decode:
        if entry.get("fontes"):
            raise ValueError(f"{where}: fontes without x-decode")
        return field
    registry = {s["id"] for s in sources_registry()["sources"]}
    cited: set[str] = set()
    evidence = []
    for fonte in entry["fontes"]:
        if fonte["source_id"] not in registry:
            raise ValueError(f"{where}: unknown source {fonte['source_id']!r}")
        codes = [str(c) for c in fonte["codigos"]]
        if "membro" in fonte:
            listed = cnv_map(parse_cnv(read_member(fonte["membro"], membros)))
            missing = sorted(set(codes) - set(listed))
            if missing:
                raise ValueError(f"{where}: {fonte['membro']} does not list {missing}")
        cited |= set(codes)
        evidence.append({k: fonte[k] for k in ("source_id", "pages", "locator")})
    keys = {str(k) for k in decode}
    if cited != keys:
        raise ValueError(
            f"{where}: codes without a source {sorted(keys - cited)}, "
            f"sources citing codes not in x-decode {sorted(cited - keys)}"
        )
    digest = hashlib.sha256(canonical_json(resolved_codes(field))).hexdigest()
    meta = dict(field.get("x-metadata", {}))
    meta["claims"] = [
        {
            "target": "/field/codes",
            "value_sha256": digest,
            "status": "verified_in_source",
            "checked_at": checked_at,
            "method": METHOD,
            "reviewer": REVIEWER,
            "evidence": evidence,
            "note": " ".join(
                [
                    "Cada código citado por uma página ou um CNV oficial.",
                    *entry.get("nota", []),
                ]
            ),
        }
    ]
    return {**field, "x-metadata": meta}


def generate() -> dict[Path, str]:
    """New text of every SINAN dictionary."""
    bloco = yaml.load(BLOCO.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
    unknown = set(bloco["agravo"]) - {p.stem for p in DICIONARIOS.glob("sinan_*.yaml")}
    if unknown:
        raise ValueError(f"agravo names no dictionary: {sorted(unknown)}")
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    out = {}
    seen: set[str] = set()
    for path in sorted(DICIONARIOS.glob("sinan_*.yaml")):
        dataset = path.stem
        text = path.read_text(encoding="utf-8")
        fields = {
            f["name"]: f for f in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]
        }
        seen |= set(fields)
        by_cnv = set(vinculos["datasets"].get(dataset, {}).get("campos", {}))
        missing = sorted({e["name"] for e in bloco["agravo"].get(dataset, [])} - set(fields))
        if missing:
            raise ValueError(f"{dataset}: agravo names no field {missing}")
        entries = {e["name"]: e for e in bloco["comum"]}
        entries.update({e["name"]: e for e in bloco["agravo"].get(dataset, [])})
        for name, field in fields.items():
            claims = field.get("x-metadata", {}).get("claims", [])
            if name not in entries and any(c.get("method") == METHOD for c in claims):
                raise ValueError(f"{dataset}.{name}: page-read claim without a block entry")
        for name, entry in entries.items():
            if name not in fields:
                continue
            if name in by_cnv:
                raise ValueError(f"{dataset}.{name}: in the block and in vinculos.json campos")
            where = f"{dataset}.{name}"
            claims = fields[name].get("x-metadata", {}).get("claims", [])
            if any(c.get("method") == "cnv-parse" for c in claims):
                raise ValueError(
                    f"{where}: cnv-parse claim from gerar_decode_cnv.py; "
                    "review it by hand before the block may replace it"
                )
            new = definition_for(entry, where, bloco["revisado_em"], vinculos["membros"])
            if new != fields[name]:
                text = replace_field(text, name, new)
        out[path] = text
    unmatched = sorted({e["name"] for e in bloco["comum"]} - seen)
    if unmatched:
        raise ValueError(f"comum names no SINAN field: {unmatched}")
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
