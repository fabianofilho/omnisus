"""Tests for CNES names from the full CNES base (FTP zip -> lake.cnes_master).

The fixture is five records of the real tbEstabelecimento202312.csv
(tests/fixtures/FIXTURES.md): four hospitals with a nome fantasia, one of them
with a leading-zero code, and one establishment with only a razão social.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from omnisus.lake import Lake
from omnisus.sources.cnes.importers.master_ftp import import_cnes_master_ftp, read_names

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "cnes_base"
    / "BASE_DE_DADOS_CNES_202312.ZIP"
)
CODES = ["0860638", "2319659", "2320886", "4339517", "6185177"]


def _seed(lake: Lake, codes: list[str]) -> None:
    con = lake.connect()
    con.execute(
        f"CREATE TABLE {lake.alias}.cnes_estabelecimentos "
        "(cnes VARCHAR, tp_unid VARCHAR, codufmun VARCHAR, ano INTEGER, mes INTEGER)"
    )
    con.executemany(
        f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES (?, '05', '140010', 2023, 12)",
        [(c,) for c in codes],
    )


def test_read_names_prefers_fantasia_and_records_provenance() -> None:
    recs = {r["cnes"]: r for r in read_names(FIXTURE, "202312")}
    assert sorted(recs) == CODES
    assert recs["2320886"]["nome"] == "HOSPITAL JOSE GUEDES CATAO"
    assert recs["2320886"]["razao_social"] == "ESTADO DE RORAIMA"
    assert recs["0860638"]["nome"] == "HOSPITAL HELIO MACEDO"
    assert recs["4339517"]["nome"] == "ASSOCIACAO PESTALOZZI DE DIVINO DE SAO LOURENCO"
    assert recs["4339517"]["nome_fantasia"] is None
    assert recs["2320886"]["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert recs["2320886"]["competencia_nome"] == "202312"
    assert recs["2320886"]["arquivo"] == "BASE_DE_DADOS_CNES_202312.ZIP"


def test_read_names_rejects_zip_without_the_month_file() -> None:
    with pytest.raises(ValueError, match="tbestabelecimento202311"):
        read_names(FIXTURE, "202311")


def test_import_fills_view_and_a_second_load_keeps_existing_names(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/ftp.ducklake"
    with Lake.local(target) as lake:
        _seed(lake, CODES)
    assert import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target) == 5
    assert import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target) == 0
    with Lake.local(target) as lake:
        rows = (
            lake.connect()
            .execute(
                f"SELECT cnes, nome, competencia_nome, fonte_nome IS NOT NULL "
                f"FROM {lake.alias}.aux_cnes WHERE cnes IN ('0860638', '4339517') ORDER BY cnes"
            )
            .fetchall()
        )
    assert rows == [
        ("0860638", "HOSPITAL HELIO MACEDO", "202312", True),
        ("4339517", "ASSOCIACAO PESTALOZZI DE DIVINO DE SAO LOURENCO", "202312", True),
    ]


def test_import_rejects_bad_competencia() -> None:
    with pytest.raises(ValueError, match="AAAAMM"):
        import_cnes_master_ftp("2023-12", zip_path=FIXTURE)


def test_api_rows_keep_working_alongside_provenance_columns(tmp_path: Path) -> None:
    """A cnes_master created by the old 4-column importer gains the new columns."""
    target = f"ducklake:{tmp_path}/legado.ducklake"
    with Lake.local(target) as lake:
        _seed(lake, CODES)
        lake.connect().execute(
            f"CREATE TABLE {lake.alias}.cnes_master "
            "(cnes VARCHAR, nome VARCHAR, nome_fantasia VARCHAR, razao_social VARCHAR)"
        )
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_master VALUES ('2320886', 'API', 'API', NULL)"
        )
    assert import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target) == 4
    with Lake.local(target) as lake:
        row = (
            lake.connect()
            .execute(
                f"SELECT nome, competencia_nome FROM {lake.alias}.aux_cnes WHERE cnes = '2320886'"
            )
            .fetchone()
        )
    assert row == ("API", None)
