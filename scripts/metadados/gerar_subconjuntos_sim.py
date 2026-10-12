"""Escreve em DOINF, DOMAT e DOEXT a definição de `sim_obitos` de cada campo comum.

Os registros desses subconjuntos nacionais são registros do DO. Em 2018, 2019, 2022,
2023 e 2024, cada registro de residente de RR é igual, byte a byte, a um registro do
DORR do ano; em 1996, 2005, 2015 e 2017 só difere `CONTADOR`, a numeração do arquivo
(evidência em `evidence/2026-09-23-sim-subconjuntos/`). O mesmo valor tem então o
mesmo rótulo nos dois dicionários. O DOFET fica de fora: é outro registro, não cópia do DO.

Rodar de novo não muda nada; `--check` falha se algum dicionário mudaria.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gerar_decode_cnv import DICIONARIOS, ROOT, replace_field

SUBCONJUNTOS = ("sim_obitos_infantis", "sim_obitos_maternos", "sim_obitos_externos")


def generate() -> dict[Path, str]:
    """New text of each subset dictionary, with sim_obitos' definition of every shared field."""
    do_text = (DICIONARIOS / "sim_obitos.yaml").read_text(encoding="utf-8")
    do = {f["name"]: f for f in yaml.load(do_text, Loader=yaml.CSafeLoader)["schema"]["fields"]}
    out = {}
    for dataset in SUBCONJUNTOS:
        path = DICIONARIOS / f"{dataset}.yaml"
        text = path.read_text(encoding="utf-8")
        for field in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]:
            name = field["name"]
            if name not in do:
                raise ValueError(f"{dataset}.{name} is not a sim_obitos field")
            if field != do[name]:
                text = replace_field(text, name, do[name])
        out[path] = text
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
