"""CID-10 values of the census files that find no row in the packaged aux_cid10.

    uv run --locked python evidence/2026-10-07-sia-cid-widths/values.py CACHE_DIR \
        TAB_SIA.zip evidence/2026-10-07-sia-cid-widths/values.csv

Reads every file `census.py` cached in CACHE_DIR (PA of RR in both eras, AQ and AR of AL),
after checking its SHA-256 against `census.csv` next to this script, with the dictionary of
its era: PA files of 1994-07 to 2007-12 with
`sia_producao_ambulatorial_1994_2007`, the others with their 2008-on dictionary. For each
CID field it counts the filled values, and writes one row per value that has no row in
`aux_cid10.codigo` of the packaged bootstrap, with the label `DBF/S_CID.DBF` of
TAB_SIA.zip gives it (empty when the code is not in S_CID). TAB_SIA.zip must be the
registered archive (`sia-tab-e5812b51d802`); the member is read in place, not packaged.
It prints the `x-version` of `aux_cid10` and the SHA-256 of the `aux_cid10.parquet` it
compared against.
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

from omnisus.sources.datasus_ftp.parse import _stream_records, dbc_bytes_to_lazyframe
from omnisus.transforms.dictionaries import load_dicionario

TAB_SIA_SHA256 = "e5812b51d802b2fe3d0c7988a24d694b97a7998a9f2f5cff390b0b4103e74d98"
DATASETS = {
    "PA": "sia_producao_ambulatorial",
    "AQ": "sia_apac_quimioterapia",
    "AR": "sia_apac_radioterapia",
}
COLUMNS = ["dataset", "field", "filled", "value", "rows", "s_cid_label"]


def dataset_of(name: str) -> str:
    prefix, yy, mm = name[:2].upper(), int(name[4:6]), int(name[6:8])
    if prefix == "PA" and (yy >= 90 or (yy, mm) <= (7, 12)):
        return "sia_producao_ambulatorial_1994_2007"
    return DATASETS[prefix]


def s_cid(tab_sia: Path) -> dict[str, str]:
    raw = tab_sia.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TAB_SIA_SHA256:
        raise ValueError(f"{tab_sia} is not the registered TAB_SIA.zip")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        member = zf.read("DBF/S_CID.DBF")
    return {
        str(r["CD_COD"]).rstrip(): str(r["CD_DESCR"]).strip()
        for r in _stream_records(member, encoding="latin-1")
    }


def aux_cid10() -> set[str]:
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        member = zf.read("aux_cid10.parquet")
    version = load_dicionario("aux_cid10").raw["x-version"]
    print(f"aux_cid10 {version}, aux_cid10.parquet {hashlib.sha256(member).hexdigest()}")
    return set(pl.read_parquet(io.BytesIO(member))["codigo"].to_list())


def census_sha256() -> dict[str, str]:
    with (Path(__file__).parent / "census.csv").open(encoding="utf-8") as f:
        return {row["file"]: row["sha256"] for row in csv.DictReader(f)}


def main(cache: str, tab_sia: str, out: str) -> None:
    labels, known, hashes = s_cid(Path(tab_sia)), aux_cid10(), census_sha256()
    filled: collections.Counter[tuple[str, str]] = collections.Counter()
    missing: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for path in sorted(Path(cache).iterdir()):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != hashes[path.name]:
            raise ValueError(f"{path.name} does not hash to its census.csv row")
        dataset = dataset_of(path.name)
        frame = dbc_bytes_to_lazyframe(raw, dataset=dataset).collect()
        for field in (c for c in frame.columns if "cid" in c):
            values = [v for v in frame[field].to_list() if v not in (None, "")]
            filled[(dataset, field)] += len(values)
            missing[(dataset, field)].update(v for v in values if v not in known)
    with Path(out).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for (dataset, field), total in sorted(filled.items()):
            rows = sorted(missing[(dataset, field)].items(), key=lambda kv: (-kv[1], kv[0]))
            for value, count in rows or [("", 0)]:
                writer.writerow([dataset, field, total, value, count, labels.get(value, "")])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
