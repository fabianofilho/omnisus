"""A month DATASUS splits into parts becomes one publication with every part recorded."""

from __future__ import annotations

from pathlib import Path

import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.lake.publication import aggregate_sha256
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._runner import ingest_raw
from omnisus.sources.datasus_ftp.datasets import REGISTRY
from tests.support.listings import fixture_entry

BI = REGISTRY["sia_bpa_individualizado"]
SCOPE = ScopeKey("MG", 2024, 12)
DBC = Path(__file__).resolve().parents[3] / "fixtures" / "dbc"


def _parts() -> list[tuple]:
    payloads = []
    for n in (1, 2):
        raw = (DBC / f"sia_bi_mg_2024_12_part{n}_excerpt.dbc").read_bytes()
        payloads.append((fixture_entry(BI.ftp_dir, f"BIMG2412_{n}.dbc", raw), raw))
    return payloads


def test_both_parts_land_in_one_publication(tmp_path) -> None:
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        result = ingest_raw(BI, SCOPE, _parts(), lake)
        assert result is not None and result.rows == 400
        (row,) = lake.publications()
        assert [s["source_uri"].rsplit("/", 1)[1] for s in row["sources"]] == [
            "BIMG2412_1.dbc",
            "BIMG2412_2.dbc",
        ]
        assert row["release"] == "final"
        text = sus.cite(lake, dataset=BI.name).text
        assert "BIMG2412_1.dbc" in text and "BIMG2412_2.dbc" in text


def test_the_same_parts_again_are_unchanged(tmp_path) -> None:
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        ingest_raw(BI, SCOPE, _parts(), lake)
        assert ingest_raw(BI, SCOPE, _parts(), lake, policy="skip_same") is None


def test_the_publication_digest_covers_both_parts(tmp_path) -> None:
    import hashlib

    from omnisus.lake.publication import SourceFile

    parts = _parts()
    expected = aggregate_sha256(
        [SourceFile("u", hashlib.sha256(raw).hexdigest()) for _, raw in parts]
    )
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        ingest_raw(BI, SCOPE, parts, lake)
        (row,) = lake.publications()
        assert row["source_sha256"] == expected


def test_a_file_from_another_directory_is_refused(tmp_path) -> None:
    (entry, raw), _ = _parts()
    stray = fixture_entry("/dissemin/publicos/SIASUS/199407_200712/Dados", entry.name, raw)
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake, pytest.raises(ValueError):
        ingest_raw(BI, SCOPE, [(stray, raw)], lake)
