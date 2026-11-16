"""Column names as staging writes them: file names trimmed, partition names checked."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from omnisus.sources.datasus_ftp.dbc import decompress_bytes
from omnisus.sources.datasus_ftp.staging import dbc_bytes_to_parquet
from omnisus.transforms.dictionaries import load_dicionario

DBC = Path(__file__).resolve().parents[3] / "fixtures" / "dbc"


def test_a_field_name_padded_with_spaces_stages_trimmed(tmp_path: Path) -> None:
    """PSRR2401's descriptor spells the field ``TIPPRE`` plus two spaces, then NULs."""
    raw = (DBC / "sia_ps_rr_2024_01_mini.dbc").read_bytes()
    assert b"TIPPRE  \x00\x00\x00" in decompress_bytes(raw)[:1024]
    out = tmp_path / "ps.parquet"
    dbc_bytes_to_parquet(
        raw, out, dataset="sia_psicossocial", uf="RR", ano=2024, mes=1, release="final"
    )
    columns = pl.read_parquet_schema(out)
    assert "tippre" in columns
    assert [name for name in columns if name != name.strip()] == []
    declared = {field["name"] for field in load_dicionario("sia_psicossocial").fields}
    assert declared <= set(columns)


def test_a_file_column_named_like_a_partition_is_kept_when_it_agrees(tmp_path: Path) -> None:
    """ERRR2401 has its own ANO ("2024") and MES ("01"); they equal the scope, as in
    every ER file on the server (4,931 files, 2011-01 to 2026-07)."""
    out = tmp_path / "er.parquet"
    raw = (DBC / "sih_er_rr_2024_01_mini.dbc").read_bytes()
    dbc_bytes_to_parquet(raw, out, dataset="sih_aih_rejeitada_erro", uf="RR", ano=2024, mes=1)
    frame = pl.read_parquet(out)
    assert frame["ano"].unique().to_list() == [2024]
    assert frame["mes"].unique().to_list() == [1]


@pytest.mark.parametrize(("ano", "mes", "column"), [(2023, 1, "ano"), (2024, 2, "mes")])
def test_a_file_column_that_contradicts_its_partition_is_refused(
    tmp_path: Path, ano: int, mes: int, column: str
) -> None:
    """Served as another month or year, ERRR2401's own ANO/MES would be overwritten."""
    out = tmp_path / "er.parquet"
    raw = (DBC / "sih_er_rr_2024_01_mini.dbc").read_bytes()
    with pytest.raises(ValueError, match=f"DBF column {column} "):
        dbc_bytes_to_parquet(raw, out, dataset="sih_aih_rejeitada_erro", uf="RR", ano=ano, mes=mes)
    assert not out.exists()
