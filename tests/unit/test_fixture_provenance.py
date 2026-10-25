"""Every committed data fixture has a provenance row (AGENTS.md, policy rule 2)."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

from scripts.dbc_excerpt import _columns, blank_dbf

from omnisus.sources.datasus_ftp.dbc import decompress_bytes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TABLE = FIXTURES / "FIXTURES.md"
COLUMNS = ["file", "kind", "source", "server_modified", "source_sha256", "records", "note"]
KINDS = {"whole", "excerpt", "listing", "synthetic", "vector", "member"}
PINNED_URL = r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/\S+"
DATA_GLOBS = ["dbc/**/*.dbc", "listings/*.txt.gz", "cnv/*", "sigtap/*", "cnes_base/*"]


def load_fixture_rows() -> list[dict[str, str]]:
    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(COLUMNS) or cells[0] in ("file", "") or set(cells[0]) <= {"-"}:
            continue
        rows.append(dict(zip(COLUMNS, cells, strict=True)))
    return rows


def test_every_data_fixture_has_exactly_one_row() -> None:
    files = sorted(
        # as_posix: FIXTURES.md records one separator, the one the repository uses.
        path.relative_to(FIXTURES).as_posix()
        for pattern in DATA_GLOBS
        for path in FIXTURES.glob(pattern)
    )
    recorded = [row["file"] for row in load_fixture_rows()]
    assert sorted(recorded) == files


def test_rows_are_complete() -> None:
    for row in load_fixture_rows():
        assert row["kind"] in KINDS, row
        if row["kind"] == "synthetic":
            assert row["note"], f"{row['file']}: a synthetic fixture must say why"
            continue
        if row["kind"] == "vector":
            assert re.fullmatch(PINNED_URL, row["source"]), row
            assert re.fullmatch("[0-9a-f]{64}", row["source_sha256"]), row
            assert row["note"], f"{row['file']}: a vector must name its licence"
            continue
        assert row["source"].startswith("ftp://"), row
        assert re.fullmatch("[0-9a-f]{64}", row["source_sha256"]), row
        assert row["server_modified"], row


def test_whole_files_are_the_recorded_bytes() -> None:
    for row in load_fixture_rows():
        if row["kind"] in ("whole", "vector", "member"):
            digest = hashlib.sha256((FIXTURES / row["file"]).read_bytes()).hexdigest()
            assert digest == row["source_sha256"], row["file"]


def test_excerpts_record_how_many_records_they_keep() -> None:
    for row in load_fixture_rows():
        if row["kind"] in ("excerpt", "listing"):
            assert row["records"].isdigit() and int(row["records"]) > 0, row


def _cpf(digits: str) -> bool:
    """Eleven digits, not all equal, whose two check digits are right."""
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    numbers = [int(digit) for digit in digits]
    for size in (9, 10):
        weighted = sum(n * (size + 1 - i) for i, n in enumerate(numbers[:size]))
        if numbers[size] != weighted * 10 % 11 % 10:
            return False
    return True


def _cnpj(digits: str) -> bool:
    """Fourteen digits whose two check digits are right."""
    if len(digits) != 14:
        return False
    numbers = [int(digit) for digit in digits]
    weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for size in (12, 13):
        remainder = (
            sum(n * w for n, w in zip(numbers[:size], weights[13 - size :], strict=True)) % 11
        )
        if numbers[size] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


def _person_identifier(cell: str) -> bool:
    """A CPF (zero-padded, and not also a valid CNPJ) or a CNS, in clear."""
    if not cell.isdigit():
        return False
    if (
        len(cell) == 15
        and cell[0] in "12789"
        and sum(int(digit) * (15 - i) for i, digit in enumerate(cell)) % 11 == 0
    ):
        return True
    return len(cell) >= 11 and not cell[:-11].strip("0") and _cpf(cell[-11:]) and not _cnpj(cell)


def test_no_fixture_holds_a_person_identifier_in_clear() -> None:
    """AGENTS.md, "Never commit": no CPF or CNS in a fixture. scripts/dbc_excerpt.py
    --blank fills such a column with spaces; the cipher DATASUS applies to patient
    CNS (CNS_PAC, AP_CNSPCN) leaves no digits, so it is not flagged."""
    found = []
    for path in sorted((FIXTURES / "dbc").glob("*.dbc")):
        dbf = decompress_bytes(path.read_bytes())
        records = int.from_bytes(dbf[4:8], "little")
        header_length = int.from_bytes(dbf[8:10], "little")
        record_length = int.from_bytes(dbf[10:12], "little")
        for column, (offset, width) in _columns(dbf).items():
            if width < 11:
                continue
            hits = sum(
                _person_identifier(
                    dbf[start + offset : start + offset + width].decode("latin-1").strip()
                )
                for start in range(
                    header_length, header_length + records * record_length, record_length
                )
            )
            if hits:
                found.append(f"{path.name} {column}: {hits} records")
    assert found == []


def _zipped_csv_records(path: Path) -> list[dict[str, str]]:
    """Records of the single CSV member of a zipped excerpt (``cnes_base/``)."""
    with zipfile.ZipFile(path) as zf:
        (member,) = zf.namelist()
        text = zf.read(member).decode("latin-1")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def test_blanked_columns_are_blank() -> None:
    """A note's ``blanked:`` list is what the file holds: blanking it again changes nothing."""
    for row in load_fixture_rows():
        listed = re.search(r"blanked: ([A-Z0-9_:=, ]+)", row["note"])
        if listed and row["file"].endswith(".ZIP"):
            assert all(
                record[column] == ""
                for record in _zipped_csv_records(FIXTURES / row["file"])
                for column in listed.group(1).split(", ")
            ), row["file"]
        elif listed:
            dbf = decompress_bytes((FIXTURES / row["file"]).read_bytes())
            assert blank_dbf(dbf, listed.group(1).split(", ")) == dbf, row["file"]
