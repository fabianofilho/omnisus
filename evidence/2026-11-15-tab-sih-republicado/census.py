"""List every member of a TAB_SIH.zip and compare it with what the repository recorded.

    uv run --locked python evidence/2026-11-15-tab-sih-republicado/census.py ZIP > members.csv

One CSV row per member: path, size, SHA-256, the date stored in the zip, and the SHA-256
the repository holds for it (``vinculos.json`` for the packaged members of
``sih-tab-f05b32f32908``, ``evidence/2026-09-14-contrato-analitico/tab-sih-sources.json``
for those of ``sih-tab-714ed980d483``), empty when it holds none. The summary goes to stderr.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VINCULOS = ROOT / "src/omnisus/data/dicionarios/sources/cnv/vinculos.json"
OLD = ROOT / "evidence/2026-09-14-contrato-analitico/tab-sih-sources.json"


def recorded() -> dict[str, dict[str, str]]:
    """``{member path: {source id: SHA-256}}`` from the two places that hold them."""
    out: dict[str, dict[str, str]] = {}
    for entry in json.loads(VINCULOS.read_text(encoding="utf-8"))["membros"].values():
        if entry["fonte"] == "sih-tab-f05b32f32908":
            out.setdefault(entry["membro"], {})[entry["fonte"]] = entry["sha256"]
    for member in json.loads(OLD.read_text(encoding="utf-8"))["members"]:
        out.setdefault(member["path"], {})["sih-tab-714ed980d483"] = member["sha256"]
    return out


def main(zip_path: Path) -> None:
    known = recorded()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(
        ["member", "bytes", "sha256", "zip_date", "recorded_source", "recorded_sha256"]
    )
    compared = equal = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            digest = hashlib.sha256(zf.read(info)).hexdigest()
            date = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*info.date_time)
            for source, sha in known.get(info.filename, {}).items() or [("", "")]:
                writer.writerow([info.filename, info.file_size, digest, date, source, sha])
                if source:
                    compared += 1
                    equal += sha == digest
    print(f"{compared} recorded members compared, {equal} equal", file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
