"""Do the three TAB_SIH packages of 1992-2007 give RD the same seven CNV maps?

    uv run --locked python evidence/2026-09-29-tab-sih-rd-eras/compare.py ZIP...

For each zip and each RD.DEF line that binds one of the fields at position 1 (parsed with
omnisus.transforms.cnv.parse_def), one CSV row on stdout: the zip's SHA-256, the line,
the CNV member, its SHA-256 and the SHA-256 of its parsed map (cnv_map, as canonical
JSON).
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path

from omnisus.metadata import canonical_json
from omnisus.transforms.cnv import cnv_map, parse_cnv, parse_def

FIELDS = ("ident", "sexo", "morte", "natureza", "gestao", "instru", "vincprev")


def rows(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        members = {name.upper(): name for name in zf.namelist()}
        def_text = zf.read(members["RD.DEF"]).decode("latin-1")
        out = []
        for binding in parse_def(def_text):
            if binding.field.lower() not in FIELDS or binding.start != 1:
                continue
            member = zf.read(members[binding.table.upper()])
            labels = cnv_map(parse_cnv(member.decode("latin-1")))
            out.append(
                [
                    path.name,
                    hashlib.sha256(raw).hexdigest(),
                    binding.field.lower(),
                    f"{binding.kind}{binding.label}, {binding.field}, {binding.start}, "
                    f"{binding.table}",
                    binding.table,
                    hashlib.sha256(member).hexdigest(),
                    hashlib.sha256(canonical_json(labels)).hexdigest(),
                ]
            )
    return out


def main() -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["zip", "zip_sha256", "field", "def_line", "cnv", "cnv_sha256", "map_sha256"])
    for arg in sys.argv[1:]:
        writer.writerows(rows(Path(arg)))


if __name__ == "__main__":
    main()
