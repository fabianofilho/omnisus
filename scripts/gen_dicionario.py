"""Write a physical-inventory dictionary YAML from one DATASUS DBC file.

The YAML records what the file physically contains — field names, DBF types
mapped to Frictionless types — and says so in ``x-evidence``. It is the
starting point for every new dataset row; semantic curation is a later,
separate act (docs/dicionario/consumo.md).

    uv run --locked python scripts/gen_dicionario.py sinan_hanseniase HANSBR26.dbc \
        --title "SINAN — Hanseníase, notificações nacionais" \
        --source-url ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/HANSBR26.dbc \
        --dictionary-url https://portalsinan.saude.gov.br/images/documentos/Agravos/Hanseniase/DIC_DADOS_Hanseniase_v5.pdf \
        --identity nu_ano id_agravo A309
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import yaml

from omnisus.sources.datasus_ftp import dbc

_TYPES = {"C": "string", "D": "date", "L": "boolean", "M": "string", "F": "number"}


def fields_of(dbf: bytes) -> list[dict[str, str]]:
    """Field name and Frictionless type for every descriptor in the DBF header."""
    out: list[dict[str, str]] = []
    pos = 32
    while dbf[pos] != 0x0D:
        name = dbf[pos : pos + 11].split(b"\0")[0].decode("latin-1").lower()
        kind, decimals = chr(dbf[pos + 11]), dbf[pos + 17]
        if kind == "N":
            ftype = "integer" if decimals == 0 else "number"
        else:
            ftype = _TYPES.get(kind, "string")
        out.append({"name": name, "type": ftype})
        pos += 32
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("name")
    ap.add_argument("dbc", type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--dictionary-url", required=True)
    ap.add_argument("--identity", nargs=3, metavar=("YEAR_COLUMN", "CODE_COLUMN", "CODE"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    dbf = dbc.decompress_bytes(args.dbc.read_bytes())
    fields = fields_of(dbf)
    doc: dict = {
        "name": args.name,
        "title": args.title,
        "profile": "tabular-data-resource",
        "encoding": "latin-1",
        "x-version": "1.0.0",
        "x-source-format": "dbc",
        "x-evidence": {
            "physical_schema": (
                f"{args.dbc.name}, {len(fields)} fields; observed {dt.date.today().isoformat()}"
            ),
            "semantic_status": (
                "Physical inventory; individual semantic fields not audited. "
                "No inferred category mappings."
            ),
            "dictionary_url": args.dictionary_url,
            "source_url": args.source_url,
        },
        "schema": {"fields": fields},
    }
    if args.identity:
        year_column, code_column, code = args.identity
        doc["x-identity"] = {
            "year_column": year_column,
            "code_column": code_column,
            "code": code,
        }
    out = args.out or Path("src/omnisus/data/dicionarios") / f"{args.name}.yaml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {out} ({len(fields)} fields)")


if __name__ == "__main__":
    main()
