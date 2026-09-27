"""Public research helpers: citation, skip_same import, municipality join key."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus


def _serve_sim_rr_2023(monkeypatch, payload: bytes) -> None:
    fake_datasus.serve(monkeypatch, "sim_obitos", {ScopeKey(uf="RR", ano=2023): payload})


def test_research_helpers_are_exported() -> None:
    for name in (
        "Citation",
        "citation_from_publications",
        "cite",
        "import_research",
        "latest_snapshot_id",
        "municipality_join_key",
        "municipality_join_key_sql",
    ):
        assert name in sus.__all__
        assert hasattr(sus, name)


def test_import_research_requires_run_id_and_refuses_append(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    _serve_sim_rr_2023(monkeypatch, dbc_fixture("sim_rr_2023_mini").read_bytes())
    target = f"ducklake:{tmp_path}/research.ducklake"
    scopes = [ScopeKey(uf="RR", ano=2023)]

    with pytest.raises(TypeError):
        sus.import_research("sim_obitos", scopes=scopes, target=target)  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="append"):
        sus.import_research(
            "sim_obitos",
            scopes=scopes,
            target=target,
            run_id="r1",
            policy="append",
        )

    with pytest.raises(ValueError, match="run_id"):
        sus.import_research("sim_obitos", scopes=scopes, target=target, run_id="  ")


def test_import_research_skip_same_does_not_duplicate(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    _serve_sim_rr_2023(monkeypatch, dbc_fixture("sim_rr_2023_mini").read_bytes())
    target = f"ducklake:{tmp_path}/research.ducklake"
    scopes = [ScopeKey(uf="RR", ano=2023)]

    first = sus.import_research("sim_obitos", scopes=scopes, target=target, run_id="r1")
    second = sus.import_research("sim_obitos", scopes=scopes, target=target, run_id="r2")

    assert first.rows > 0
    assert second.rows == 0
    assert second.skipped
    with Lake.local(target) as lake:
        (n,) = lake.connect().execute("SELECT count(*) FROM lake.sim_obitos").fetchone()
    assert n == first.rows


def test_latest_snapshot_id_and_cite_name_the_file(
    monkeypatch, tmp_path: Path, dbc_fixture
) -> None:
    _serve_sim_rr_2023(monkeypatch, dbc_fixture("sim_rr_2023_mini").read_bytes())
    target = f"ducklake:{tmp_path}/cite.ducklake"
    sus.import_research(
        "sim_obitos",
        scopes=[ScopeKey(uf="RR", ano=2023)],
        target=target,
        run_id="sim-rr-2023-01",
    )

    with sus.LakeReader(target) as leitor:
        snapshot_id = sus.latest_snapshot_id(leitor)
        citacao = sus.cite(
            leitor,
            dataset="sim_obitos",
            snapshot_id=snapshot_id,
            run_id="sim-rr-2023-01",
            accessed=date(2026, 9, 18),
        )

    assert snapshot_id == citacao.snapshot_id
    assert citacao.dataset == "sim_obitos"
    assert citacao.run_id == "sim-rr-2023-01"
    assert citacao.omnisus == sus.__version__
    assert len(citacao.publications) == 1
    pub = citacao.publications[0]
    assert pub["source_sha256"]
    assert "sim_obitos" in citacao.text
    assert pub["source_sha256"] in citacao.text
    assert "sim-rr-2023-01" in citacao.text
    assert str(snapshot_id) in citacao.text
    assert "2026-09-18" in citacao.text
    assert sus.__version__ in citacao.text


def test_cite_without_snapshot_pins_the_latest(monkeypatch, tmp_path: Path, dbc_fixture) -> None:
    _serve_sim_rr_2023(monkeypatch, dbc_fixture("sim_rr_2023_mini").read_bytes())
    target = f"ducklake:{tmp_path}/pin.ducklake"
    sus.import_research(
        "sim_obitos",
        scopes=[ScopeKey(uf="RR", ano=2023)],
        target=target,
        run_id="r1",
    )
    with sus.LakeReader(target) as leitor:
        expected = sus.latest_snapshot_id(leitor)
        citacao = sus.cite(leitor, dataset="sim_obitos")
    assert citacao.snapshot_id == expected


def test_latest_snapshot_id_without_history() -> None:
    class _Vazio:
        def snapshots(self):
            return []

    with pytest.raises(LookupError, match="snapshot"):
        sus.latest_snapshot_id(_Vazio())  # type: ignore[arg-type]


def test_cite_ibge_uses_population_manifest(tmp_path: Path) -> None:
    target = f"ducklake:{tmp_path}/ibge.ducklake"
    with Lake.local(target) as lake:
        lake.ingest(
            "ibge_population_manifest",
            __import__("polars")
            .DataFrame(
                {
                    "publication_id": ["pub-1"],
                    "product": ["census"],
                    "ano": [2022],
                    "sha256": ["abc123"],
                    "url": ["https://example.test/sidra"],
                    "collected_at": ["2026-01-01T00:00:00+00:00"],
                }
            )
            .lazy(),
        )
        snapshot_id = sus.latest_snapshot_id(lake)
        citacao = sus.cite(
            lake,
            dataset="ibge_populacao",
            snapshot_id=snapshot_id,
            accessed=date(2026, 9, 18),
        )
    assert citacao.publications[0]["sha256"] == "abc123"
    assert "abc123" in citacao.text
    assert "https://example.test/sidra" in citacao.text
    assert "pub-1" in citacao.text


def test_the_citation_names_every_part_of_a_split_month() -> None:
    row = {
        "dataset": "sia_bpa_individualizado",
        "source_uri": "ftp://ftp.datasus.gov.br/d/BIMG2412_1.dbc",
        "source_sha256": "0" * 64,
        "run_id": "r1",
        "sources": [
            {
                "ordinal": 0,
                "source_uri": "ftp://ftp.datasus.gov.br/d/BIMG2412_1.dbc",
                "source_sha256": "1" * 64,
                "source_bytes": 1,
                "source_modified": None,
            },
            {
                "ordinal": 1,
                "source_uri": "ftp://ftp.datasus.gov.br/d/BIMG2412_2.dbc",
                "source_sha256": "2" * 64,
                "source_bytes": 1,
                "source_modified": None,
            },
        ],
    }
    text = sus.citation_from_publications([row], snapshot_id=3).text
    assert "BIMG2412_1.dbc" in text and "BIMG2412_2.dbc" in text
    assert "1" * 64 in text and "2" * 64 in text


def test_municipality_join_key_takes_the_left_digits() -> None:
    assert sus.municipality_join_key("1400100") == "140010"
    assert sus.municipality_join_key("140010", digits=6) == "140010"
    assert sus.municipality_join_key(1400100) == "140010"
    assert sus.municipality_join_key(" 1400100 ", digits=7) == "1400100"
    assert sus.municipality_join_key(None) is None
    assert sus.municipality_join_key("  ") is None
    with pytest.raises(ValueError, match="digits"):
        sus.municipality_join_key("1400100", digits=5)


def test_municipality_join_key_sql_matches_the_guide() -> None:
    sql = sus.municipality_join_key_sql("codmunres")
    assert sql == 'left(trim(CAST("codmunres" AS VARCHAR)), 6)'
    ibge = sus.municipality_join_key_sql("codigo_ibge", digits=6)
    con = duckdb.connect()
    assert con.execute(f"SELECT {sql} FROM (SELECT '1400100' AS codmunres)").fetchone() == (
        "140010",
    )
    assert con.execute(f"SELECT {ibge} FROM (SELECT '1400100' AS codigo_ibge)").fetchone() == (
        "140010",
    )
    with pytest.raises(ValueError):
        sus.municipality_join_key_sql("codmunres", digits=8)
