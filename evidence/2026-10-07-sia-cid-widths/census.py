"""The DBF field layout of the SIA files that carry CID-10 fields, one row per file read.

    uv run --locked python evidence/2026-10-07-sia-cid-widths/census.py CACHE_DIR \
        evidence/2026-10-07-sia-cid-widths/census.csv

The reading of `evidence/2026-10-06-rd-2008-layouts/census.py`, for three SIA series: PA of
RR in `SIASUS/199407_200712/Dados` and in `SIASUS/200801_/Dados`, and AQ and AR of AL in
`SIASUS/200801_/Dados` (AL lists both in every month from 2008-01; RR lists no AR). One
file per month the server lists for the series. Downloads are kept in CACHE_DIR and
reused; sizes and dates come from the live listing, and a file whose size differs from
the listing's stops the run and is not kept. The CSV goes to the path given.

`fields` is the header's descriptor list in file order, each `NAME TYPE WIDTH.DECIMALS`;
`layout` numbers the distinct lists of one series in the order of the first month that
has them. The width of every CID field, by run of months, is printed on stderr.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import re
import sys
from pathlib import Path

from omnisus.sources.datasus_ftp.dbc import decompress_bytes
from omnisus.sources.datasus_ftp.dbf_contract import _read_field_descriptors
from omnisus.sources.datasus_ftp.fetch import _download
from omnisus.sources.datasus_ftp.inventory import FtpEntry, list_dir

SERIES = [
    ("/dissemin/publicos/SIASUS/199407_200712/Dados", "PA", "RR"),
    ("/dissemin/publicos/SIASUS/200801_/Dados", "PA", "RR"),
    ("/dissemin/publicos/SIASUS/200801_/Dados", "AQ", "AL"),
    ("/dissemin/publicos/SIASUS/200801_/Dados", "AR", "AL"),
]
COLUMNS = [
    "file",
    "month",
    "server_modified",
    "size_bytes",
    "sha256",
    "records",
    "layout",
    "fields",
]


def header(dbf: bytes) -> tuple[int, str]:
    """Record count and descriptor list of one DBF."""
    fields = " ".join(
        f"{f.name} {f.kind}{f.width}.{f.decimals}" for f in _read_field_descriptors(dbf)
    )
    return int.from_bytes(dbf[4:8], "little"), fields


def month_of(name: str) -> str:
    aamm = name[4:8]
    return f"{19 if aamm >= '90' else 20}{aamm[:2]}-{aamm[2:]}"


async def read(cache: Path, entry: FtpEntry) -> list[object]:
    path = cache / entry.name
    cached = path.exists()
    raw = path.read_bytes() if cached else await _download(entry.parent, entry.name, 900)
    if len(raw) != entry.size_bytes:
        raise ValueError(f"{entry.name}: {len(raw)} bytes, the listing says {entry.size_bytes}")
    if not cached:
        path.write_bytes(raw)
    records, fields = header(decompress_bytes(raw))
    modified = entry.modified.strftime("%Y-%m-%dT%H:%M")
    sha256 = hashlib.sha256(raw).hexdigest()
    return [entry.name, month_of(entry.name), modified, entry.size_bytes, sha256, records, fields]


async def census(cache: Path) -> list[list[object]]:
    rows: list[list[object]] = []
    for directory, prefix, uf in SERIES:
        pattern = re.compile(rf"{prefix}{uf}\d{{4}}\.dbc", re.IGNORECASE)
        listed = sorted(
            (e for e in list_dir(directory).files if pattern.fullmatch(e.name)),
            key=lambda e: month_of(e.name),
        )
        series = [await read(cache, entry) for entry in listed]
        layouts: dict[str, int] = {}
        for row in series:
            row.insert(6, layouts.setdefault(str(row[6]), len(layouts) + 1))
        rows += series
    return rows


def summary(rows: list[list[object]]) -> None:
    runs: dict[tuple[str, str], list[list[str]]] = {}
    for row in rows:
        parts = str(row[7]).split(" ")
        for name, spec in zip(parts[::2], parts[1::2], strict=True):
            if "CID" not in name:
                continue
            key = (str(row[0])[:4].upper(), name)
            spans = runs.setdefault(key, [])
            if spans and spans[-1][2] == spec:
                spans[-1][1] = str(row[1])
            else:
                spans.append([str(row[1]), str(row[1]), spec])
    for (series, name), spans in sorted(runs.items()):
        text = "; ".join(f"{a}..{b} {spec}" for a, b, spec in spans)
        print(f"{series} {name}: {text}", file=sys.stderr)


def main(cache: str, out: str) -> None:
    rows = asyncio.run(census(Path(cache)))
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    summary(rows)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
