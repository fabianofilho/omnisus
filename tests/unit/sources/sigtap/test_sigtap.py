"""SIGTAP procedures by competência, on real server files."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from omnisus import cite
from omnisus.lake import Lake
from omnisus.sources import sigtap
from omnisus.sources._base import ScopeKey
from omnisus.transforms.dictionaries import load_dicionario

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
ZIP_200801 = FIXTURES / "sigtap" / "TabelaUnificada_200801.zip"


def server_names() -> list[str]:
    raw = gzip.decompress(
        (FIXTURES / "listings" / "sigtap_tup_downloads_nlst.txt.gz").read_bytes()
    )
    return raw.decode("latin-1").splitlines()


def test_every_competencia_from_2008_01_to_2026_09_is_listed_once():
    found = sigtap.competencias(server_names())
    assert len(found) == 225
    assert min(found) == (2008, 1) and max(found) == (2026, 9)
    assert found[(2008, 1)] == "TabelaUnificada_200801.zip"
    assert found[(2026, 9)] == "TabelaUnificada_202609_v2609171117.zip"


def test_the_layout_file_drives_the_columns():
    old = sigtap.read_procedimentos(ZIP_200801.read_bytes())
    new = sigtap.parse_layout(
        (FIXTURES / "sigtap" / "tb_procedimento_layout_202609.txt").read_text("latin-1")
    )
    assert old.height == 4190
    assert old.columns[:2] == ["co_procedimento", "no_procedimento"]
    assert "qt_tempo_permanencia" not in old.columns
    assert [c.name for c in new][-2:] == ["qt_tempo_permanencia", "dt_competencia"]
    assert {c.name: c.end - c.start + 1 for c in new}["vl_sa"] == 12
    first = old.row(0, named=True)
    assert first["co_procedimento"] == "0101010010"
    assert (
        first["no_procedimento"] == "ATIVIDADE EDUCATIVA / ORIENTACAO EM GRUPO NA ATENCAO BASICA"
    )
    assert first["dt_competencia"] == "200801"
    assert isinstance(first["vl_sa"], int)
    declared = [f["name"] for f in load_dicionario(sigtap.TABLE).fields]
    assert declared == [c.name for c in new]
    assert set(old.columns) < set(declared)


def test_national_monthly_scope_round_trips():
    from omnisus.lake.publication import scope_fields, scope_from_fields

    scope = ScopeKey(uf=None, ano=2008, mes=1)
    assert scope_fields(scope) == {"_source_ano": 2008, "_source_mes": 1}
    assert scope_from_fields(scope_fields(scope)) == scope
    assert str(scope) == "national_2008_01"


def test_import_publishes_once_then_reports_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(sigtap, "list_names", server_names)
    monkeypatch.setattr(
        sigtap, "download", lambda name: (ZIP_200801.read_bytes(), "2009-01-08T00:00")
    )
    target = f"ducklake:{tmp_path}/x.ducklake"
    with Lake.local(target) as lake:
        first = sigtap.import_sigtap([(2008, 1), (1999, 1)], lake=lake)
        again = sigtap.import_sigtap([(2008, 1)], lake=lake)
        rows = (
            lake.connect()
            .execute(
                "SELECT count(*), min(_source_ano), min(_source_mes) FROM lake.aux_sigtap_procedimentos"
            )
            .fetchone()
        )
        publications = [p for p in lake.publications() if p["dataset"] == sigtap.TABLE]
        citation = cite(lake, dataset=sigtap.TABLE)
    assert [(o.scope, o.status, o.code) for o in first.outcomes] == [
        (ScopeKey(None, 2008, 1), "ok", None),
        (ScopeKey(None, 1999, 1), "skipped", "not_listed"),
    ]
    assert first.rows == 4190 == rows[0]
    assert rows[1:] == (2008, 1)
    assert [(o.status, o.code) for o in again.outcomes] == [("skipped", "unchanged")]
    assert len(publications) == 1
    assert citation.text.startswith("SIGTAP — procedimentos da Tabela Unificada")
    assert "TabelaUnificada_200801.zip" in citation.text
    assert publications[0]["source_uri"] == (
        "ftp://ftp2.datasus.gov.br/public/sistemas/tup/downloads/TabelaUnificada_200801.zip"
    )


def test_a_zip_of_another_competencia_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(sigtap, "list_names", server_names)
    monkeypatch.setattr(
        sigtap, "download", lambda name: (ZIP_200801.read_bytes(), "2009-01-08T00:00")
    )
    with Lake.local(f"ducklake:{tmp_path}/x.ducklake") as lake:
        report = sigtap.import_sigtap([(2008, 2)], lake=lake)
    assert [(o.status, o.code) for o in report.outcomes] == [("failed", "ingest_failed")]
    assert "200801" in (report.outcomes[0].reason or "")


@pytest.mark.parametrize("name", ["TabelaUnificada_2008011.zip", "Mapeamento_TUSS_SIGTAP.zip"])
def test_other_names_are_not_competencias(name):
    assert sigtap.competencias([name]) == {}


def test_public_import_sigtap_takes_years_and_months(tmp_path, monkeypatch):
    """Same names as `load` and `scopes_for`: the competências are years x months."""
    import omnisus as sus

    monkeypatch.setattr(sigtap, "list_names", server_names)
    monkeypatch.setattr(
        sigtap, "download", lambda name: (ZIP_200801.read_bytes(), "2009-01-08T00:00")
    )

    report = sus.import_sigtap(years=[2008], months=[1], target=f"ducklake:{tmp_path}/x.ducklake")

    assert [(o.scope, o.status) for o in report.outcomes] == [(ScopeKey(None, 2008, 1), "ok")]
