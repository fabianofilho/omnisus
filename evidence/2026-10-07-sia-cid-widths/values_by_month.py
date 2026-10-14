"""CID-10 values of the PA 1994-2007 files, by month and by PA_DOCORIG (#82).

    uv run --locked python evidence/2026-10-07-sia-cid-widths/values_by_month.py CACHE_DIR \
        evidence/2026-10-07-sia-cid-widths

Reads the PA files of 1994-07 to 2007-12 that `census.py` cached in CACHE_DIR, after
checking each SHA-256 against `census.csv`, with `sia_producao_ambulatorial_1994_2007`.
For each file, PA_DOCORIG value and CID field it counts the rows of every class of value:
`blank`; `resolved4` and `resolved3`, codes of 4 or 3 characters with a row in
`aux_cid10.codigo` of the packaged bootstrap; `zero1` (`0`) and `zero4` (`0000`);
`padded`, a 4-character code with no row whose last character is `0` and whose first 3
are a category with a row (`C610` for `C61`); and `other`, anything else with no row.
Writes `values_by_month.csv` (one row per file, PA_DOCORIG, field and class) and
`padded_by_month.csv` (one row per file, PA_DOCORIG, field and padded value). Files
without the CID fields (before 1999-07) are written with the class `no_field`.
"""

from __future__ import annotations

import collections
import csv
import hashlib
import io
import sys
import zipfile
from importlib.resources import files
from pathlib import Path

import polars as pl

from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe

DATASET = "sia_producao_ambulatorial_1994_2007"
FIELDS = ("pa_cidpri", "pa_cidsec")
CLASSES = ("blank", "resolved4", "resolved3", "zero1", "zero4", "padded", "other")


def is_era(name: str) -> bool:
    yy, mm = int(name[4:6]), int(name[6:8])
    return name[:2].upper() == "PA" and (yy >= 90 or (yy, mm) <= (7, 12))


def aux_cid10() -> set[str]:
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        table = pl.read_parquet(io.BytesIO(zf.read("aux_cid10.parquet")))
    return set(table["codigo"].to_list())


def classify(value: str, known: set[str]) -> str:
    if value == "":
        return "blank"
    if value in known:
        return "resolved4" if len(value) == 4 else "resolved3"
    if value == "0":
        return "zero1"
    if value == "0000":
        return "zero4"
    if len(value) == 4 and value[-1] == "0" and value[:3] in known:
        return "padded"
    return "other"


def main(cache: str, out_dir: str) -> None:
    out = Path(out_dir)
    with (out / "census.csv").open(encoding="utf-8", newline="") as f:
        census = {row["file"]: row for row in csv.DictReader(f)}
    known = aux_cid10()
    classes: list[list[object]] = []
    padded: list[list[object]] = []
    for path in sorted(p for p in Path(cache).iterdir() if is_era(p.name)):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != census[path.name]["sha256"]:
            raise ValueError(f"{path.name} does not hash to its census.csv row")
        month = census[path.name]["month"]
        frame = dbc_bytes_to_lazyframe(raw, dataset=DATASET).collect()
        if not all(field in frame.columns for field in FIELDS):
            classes.append([path.name, month, "", "", "no_field", len(frame)])
            continue
        for (docorig,), group in frame.group_by("pa_docorig", maintain_order=True):
            for field in FIELDS:
                counts: collections.Counter[str] = collections.Counter()
                values: collections.Counter[str] = collections.Counter()
                for value in group[field].to_list():
                    value = value or ""
                    kind = classify(value, known)
                    counts[kind] += 1
                    if kind == "padded":
                        values[value] += 1
                for kind in CLASSES:
                    classes.append([path.name, month, docorig, field, kind, counts[kind]])
                for value, rows in sorted(values.items()):
                    padded.append([path.name, month, docorig, field, value, rows])
    for name, header, rows in (
        (
            "values_by_month.csv",
            ["file", "month", "pa_docorig", "field", "class", "rows"],
            classes,
        ),
        ("padded_by_month.csv", ["file", "month", "pa_docorig", "field", "value", "rows"], padded),
    ):
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
