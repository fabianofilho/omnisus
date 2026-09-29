"""National-source contracts, independently of live FTP availability."""

import polars as pl
import pytest

import omnisus as sus
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import resolve
from omnisus.sources.datasus_ftp.filenames import decode_for
from tests.support.datasus_names import filename_for


def test_national_filename_and_planner():
    d = resolve("sinan_chagas")
    scopes = sus.scopes_for(d, years=[2023, 2024])
    assert scopes == [ScopeKey(uf=None, ano=2023), ScopeKey(uf=None, ano=2024)]
    assert filename_for(d, scopes[0]) == "CHAGBR23.dbc"
    assert decode_for(d, "CHAGBR23.dbc") == scopes[0]
    assert decode_for(d, "CHAGSP23.dbc") is None
    with pytest.raises(ValueError, match="national"):
        sus.scopes_for(d, years=[2023], ufs=["SP"])


def test_national_publication_replace_and_rollback(tmp_path):
    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:

        def publish(year, value, policy="append"):
            p = tmp_path / "data.parquet"
            # Geography and event year belong to records, not the source scope.
            pl.DataFrame(
                {"_source_ano": [year], "uf": ["PA"], "ano": [2019], "v": [value]}
            ).write_parquet(p)
            return lake.publish_scope(
                "national",
                p,
                scope=ScopeKey(uf=None, ano=year),
                source_sha256=str(value) * 64,
                parser_version="v1",
                policy=policy,
            )

        publish(2023, 1)
        publish(2024, 2)
        with pytest.raises(RuntimeError, match="interrupt"), lake.transaction():
            publish(2023, 3, "replace")
            raise RuntimeError("interrupt")
        assert len(lake.publications()) == 2
        publish(2023, 3, "replace")
        assert lake.connect().execute(
            "SELECT _source_ano,uf,ano,v FROM lake.national ORDER BY _source_ano"
        ).fetchall() == [(2023, "PA", 2019, 3), (2024, "PA", 2019, 2)]
        assert publish(2023, 3, "skip_same") is None
        with pytest.raises(ValueError):
            publish(2023, 4, "skip_same")
        assert len(lake.publications()) == 3


def test_identity_rejects_wrong_year_source(tmp_path, monkeypatch):
    from omnisus.sources.datasus_ftp._runner import ingest_raw
    from tests.support.dbf import make_dbf
    from tests.support.listings import listed

    # Only compression is replaced: real DBF decoding and staging execute.
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    fields = [
        ("ID_AGRAVO", "C", 4, 0),
        ("NU_ANO", "C", 4, 0),
        ("SG_UF_NOT", "C", 2, 0),
        ("ANO", "C", 4, 0),
        ("UF", "C", 2, 0),
    ]
    wrong_year = make_dbf(fields, [b" B5712022152019PA", b" B5712022332020RJ"])
    d = resolve("sinan_chagas")
    scope = ScopeKey(uf=None, ano=2023)
    with (
        sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake,
        pytest.raises(ValueError, match="year"),
    ):
        ingest_raw(d, scope, listed(d, scope, wrong_year), lake, policy="skip_same")


def test_synthetic_full_pipeline_and_corruption_preserve_publication(tmp_path, monkeypatch):
    from omnisus.sources.datasus_ftp import parse
    from omnisus.sources.datasus_ftp._runner import ingest_raw
    from tests.support.dbf import make_dbf
    from tests.support.listings import listed

    # Only compression is replaced: real DBF decoding, staging and DuckLake execute.
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    fields = [
        ("ID_AGRAVO", "C", 4, 0),
        ("NU_ANO", "C", 4, 0),
        ("SG_UF_NOT", "C", 2, 0),
        ("ANO", "C", 4, 0),
        ("UF", "C", 2, 0),
    ]
    good = make_dbf(fields, [b" B5712023152019PA", b" B5712023332020RJ"])
    wrong = make_dbf(fields, [b" B5712022152019PA"])
    d = resolve("sinan_chagas")
    scope = ScopeKey(uf=None, ano=2023)
    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:
        ingest_raw(d, scope, listed(d, scope, good), lake, policy="skip_same", run_id="initial")
        assert ingest_raw(d, scope, listed(d, scope, good), lake, policy="skip_same") is None
        before = lake.connect().sql("SELECT * FROM lake.sinan_chagas").pl()
        assert before["ano"].to_list() == ["2019", "2020"]
        assert before["uf"].to_list() == ["PA", "RJ"]
        assert before["_source_ano"].to_list() == [2023, 2023]
        for bad in [wrong, good[:-8]]:
            with pytest.raises((ValueError, parse.DbfIntegrityError)):
                ingest_raw(d, scope, listed(d, scope, bad), lake, policy="replace")
            assert lake.connect().sql("SELECT * FROM lake.sinan_chagas").pl().equals(before)
            assert len(lake.publications()) == 1
        publication = lake.publications(run_id="initial")[0]
        assert (
            publication["source_uri"]
            == "ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS/CHAGBR23.dbc"
        )


def test_national_inventory_and_cli_rejects_state_before_network(monkeypatch):
    from datetime import datetime

    from omnisus.cli.main import _plan_scopes
    from omnisus.sources.datasus_ftp import inventory

    entries = tuple(
        inventory.FtpEntry(
            name=name,
            path="/" + name,
            parent="/",
            is_dir=False,
            size_bytes=1,
            modified=datetime(2026, 1, 1),
        )
        for name in ["CHAGBR24.dbc", "CHAGBR23.dbc", "CHAGSP23.dbc"]
    )
    from omnisus.sources.datasus_ftp.datasets import REGISTRY

    sinan_prelim_dir = REGISTRY["sinan_chagas"].prelim_dir

    def fake_list(path: str, **kw: object) -> inventory.Listing:
        if path == sinan_prelim_dir:
            return inventory.Listing(entries=(), skipped=0, path=path)
        return inventory.Listing(entries=entries, skipped=0, path=path)

    monkeypatch.setattr(inventory, "list_dir_cached", fake_list)
    assert sus.available("sinan_chagas", years=[2023]) == [ScopeKey(uf=None, ano=2023)]
    for plan in ["product", "inventory"]:
        with pytest.raises(ValueError, match="national"):
            _plan_scopes(resolve("sinan_chagas"), plan=plan, years=[2023], ufs=["PA"], months=None)


def test_national_cannot_replace_state_table(tmp_path):
    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:
        p = tmp_path / "data.parquet"
        pl.DataFrame({"ano": [2023], "uf": ["PA"]}).write_parquet(p)
        lake.publish_scope(
            "t", p, scope=ScopeKey(uf="PA", ano=2023), source_sha256="a" * 64, parser_version="v1"
        )
        pl.DataFrame({"_source_ano": [2023]}).write_parquet(p)
        with pytest.raises(ValueError, match="national/state"):
            lake.publish_scope(
                "t",
                p,
                scope=ScopeKey(uf=None, ano=2023),
                source_sha256="b" * 64,
                parser_version="v1",
                policy="replace",
            )
        assert lake.connect().execute("SELECT * FROM lake.t").fetchall() == [(2023, "PA")]


def test_legacy_manifest_url_migration_and_two_publications_in_one_transaction(tmp_path):
    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:
        lake.connect().execute("""CREATE TABLE lake._omnisus_publications (
            publication_id VARCHAR, dataset VARCHAR, scope_json VARCHAR,
            source_sha256 VARCHAR, parser_version VARCHAR, run_id VARCHAR,
            batch_id VARCHAR, published_at VARCHAR, rows BIGINT,
            active BOOLEAN, managed BOOLEAN)""")
        with lake.transaction():
            for year in [2023, 2024]:
                p = tmp_path / "data.parquet"
                pl.DataFrame({"ano": [year], "uf": ["PA"]}).write_parquet(p)
                lake.publish_scope(
                    "t",
                    p,
                    scope=ScopeKey(uf="PA", ano=year),
                    source_sha256="a" * 64,
                    parser_version="v1",
                    source_uri="ftp://example/source.dbc",
                )
        assert lake.connect().execute("SELECT count(*) FROM lake.t").fetchone()[0] == 2
        assert [p["source_uri"] for p in lake.publications()] == ["ftp://example/source.dbc"] * 2
