"""The DBF field layout of the RD files of 1992-2007, one row per file read.

    uv run --locked python evidence/2026-10-01-rd-1992-2007-layouts/census.py CACHE_DIR \
        evidence/2026-10-01-rd-1992-2007-layouts/census.csv

For every month from 1992-01 to 2007-12 it reads RDRRaamm.dbc, or RDAPaamm.dbc when the
server does not list the RR file. Where two consecutive months differ in layout it also
reads RDSP and RDMG of both months, to show the change is not one UF's. Downloads are
kept in CACHE_DIR and reused; sizes and dates come from the live listing, and a file
whose size differs from the listing's stops the run and is not kept. The CSV goes to the
path given, not stdout, which carries the client's log lines.

`fields` is the header's descriptor list in file order, each `NAME TYPE WIDTH.DECIMALS`;
`layout` numbers the distinct lists in the order of the first month that has them. The
layouts, with the fields each adds and drops, are printed on stderr.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import itertools
import sys
from pathlib import Path

from omnisus.sources.datasus_ftp.dbc import decompress_bytes
from omnisus.sources.datasus_ftp.dbf_contract import _read_field_descriptors
from omnisus.sources.datasus_ftp.fetch import _download
from omnisus.sources.datasus_ftp.inventory import FtpEntry, list_dir

DIRECTORY = "/dissemin/publicos/SIHSUS/199201_200712/Dados"
MONTHS = [f"{year % 100:02d}{month:02d}" for year in range(1992, 2008) for month in range(1, 13)]
UFS = ("RR", "AP")
BOUNDARY_UFS = ("SP", "MG")
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
    return f"{19 if aamm >= '92' else 20}{aamm[:2]}-{aamm[2:]}"


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


def pick(listed: dict[str, FtpEntry], ufs: tuple[str, ...], month: str) -> list[FtpEntry]:
    return [listed[f"RD{uf}{month}.dbc"] for uf in ufs if f"RD{uf}{month}.dbc" in listed]


async def census(cache: Path) -> list[list[object]]:
    listed = {e.name: e for e in list_dir(DIRECTORY).files}
    rows = [await read(cache, pick(listed, UFS, month)[0]) for month in MONTHS]
    boundaries = sorted(
        {
            str(row[0])[4:8]
            for before, after in itertools.pairwise(rows)
            if before[6] != after[6]
            for row in (before, after)
        }
    )
    for month in boundaries:
        for entry in pick(listed, BOUNDARY_UFS, month):
            rows.append(await read(cache, entry))
    layouts: dict[str, int] = {}
    for row in sorted(rows, key=lambda r: (r[1], r[0])):
        row.insert(6, layouts.setdefault(row[6], len(layouts) + 1))
    return rows


def summary(rows: list[list[object]]) -> None:
    previous: list[str] = []
    for layout in sorted({row[6] for row in rows}):  # type: ignore[type-var]
        own = [row for row in rows if row[6] == layout]
        names = str(own[0][7]).split(" ")[::2]
        months = sorted(str(row[1]) for row in own)
        added = [n for n in names if n not in previous]
        dropped = [n for n in previous if n not in names]
        print(
            f"layout {layout}: {months[0]}..{months[-1]}, {len(own)} files, {len(names)} fields;"
            f" adds {' '.join(added) or '-'}; drops {' '.join(dropped) or '-'}",
            file=sys.stderr,
        )
        previous = names


def main(cache: str, out: str) -> None:
    rows = asyncio.run(census(Path(cache)))
    rows.sort(key=lambda r: (r[1], r[0]))
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    summary(rows)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
