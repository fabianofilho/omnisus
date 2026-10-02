import hashlib
import multiprocessing

import polars as pl
import pytest

from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey


def _try_writer(target, queue):
    try:
        with Lake.local(target):
            queue.put("opened")
    except Exception as exc:
        queue.put(type(exc).__name__)


def test_second_process_writer_rejected_and_released(tmp_path):
    target = f"ducklake:{tmp_path}/p.ducklake"
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    with Lake.local(target):
        process = context.Process(target=_try_writer, args=(target, queue))
        process.start()
        process.join(15)
        assert not process.is_alive()
        assert queue.get(timeout=2) == "WriterBusyError"
    with Lake.local(target) as lake:
        lake.ingest("t", pl.DataFrame({"x": [1]}).lazy())


def test_same_process_handle_and_symlink_are_locked(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with Lake.local(f"ducklake:{real}/p.ducklake"), pytest.raises(Exception, match="writer"):
        Lake.local(f"ducklake:{alias}/p.ducklake")


def _publish(
    lake, tmp_path, uf="SP", value=1, policy="append", digest=None, run_id="run-1", mes=1
):
    path = tmp_path / f"{uf}-{value}-{mes}.parquet"
    pl.DataFrame({"ano": [2024], "mes": [mes], "uf": [uf], "v": [value]}).write_parquet(path)
    return lake.publish_scope(
        "t",
        path,
        scope=ScopeKey(uf=uf, ano=2024, mes=mes),
        source_sha256=digest or hashlib.sha256(str(value).encode()).hexdigest(),
        parser_version="parser-v1",
        policy=policy,
        run_id=run_id,
        partition_by=("ano", "mes"),
    )


def test_skip_same_and_changed_version(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/p.ducklake") as lake:
        result = _publish(lake, tmp_path)
        assert result.run_id == "run-1"
        assert _publish(lake, tmp_path, policy="skip_same") is None
        with pytest.raises(ValueError, match="the server file differs from the one imported"):
            _publish(lake, tmp_path, value=2, policy="skip_same")
        assert lake.connect().execute("SELECT v FROM lake.t").fetchall() == [(1,)]
        assert len(lake.publications(run_id="run-1")) == 1


def test_replace_preserves_other_uf_and_manifest(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/p.ducklake") as lake:
        _publish(lake, tmp_path)
        _publish(lake, tmp_path, uf="RJ", value=3)
        _publish(lake, tmp_path, value=2, policy="replace")
        assert lake.connect().execute("SELECT uf,v FROM lake.t ORDER BY uf").fetchall() == [
            ("RJ", 3),
            ("SP", 2),
        ]
        records = lake.publications()
        assert len(records) == 3
        assert sum(r["active"] for r in records) == 2


def test_replace_invalid_scope_or_empty_preserves_data(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/p.ducklake") as lake:
        _publish(lake, tmp_path)
        for frame in [
            pl.DataFrame({"ano": [2024], "mes": [1], "uf": ["RJ"], "v": [9]}),
            pl.DataFrame(
                schema={"ano": pl.Int64, "mes": pl.Int64, "uf": pl.String, "v": pl.Int64}
            ),
        ]:
            path = tmp_path / "bad.parquet"
            frame.write_parquet(path)
            with pytest.raises(ValueError, match=r"scope|empty"):
                lake.publish_scope(
                    "t",
                    path,
                    scope=ScopeKey(uf="SP", ano=2024, mes=1),
                    source_sha256="a" * 64,
                    parser_version="v1",
                    policy="replace",
                )
        assert lake.connect().execute("SELECT v FROM lake.t").fetchall() == [(1,)]


def test_legacy_rows_not_declared_managed_by_append(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/p.ducklake") as lake:
        lake.ingest("t", pl.DataFrame({"ano": [2024], "mes": [1], "uf": ["SP"], "v": [9]}).lazy())
        _publish(lake, tmp_path)
        with pytest.raises(ValueError, match=r"legacy|unmanaged"):
            _publish(lake, tmp_path, value=2, policy="replace")
        assert lake.connect().execute("SELECT count(*) FROM lake.t").fetchone()[0] == 2


def _state_lake_and_staging(tmp_path):
    lake = Lake.local(f"ducklake:{tmp_path}/x.ducklake")
    path = tmp_path / "staging.parquet"
    pl.DataFrame({"ano": [2024], "mes": [12], "uf": ["MG"], "v": [1]}).write_parquet(path)
    return lake, path, ScopeKey(uf="MG", ano=2024, mes=12)


def test_a_publication_records_each_of_its_source_files_in_order(tmp_path) -> None:
    from omnisus.lake.publication import SourceFile, aggregate_sha256

    files = [
        SourceFile("ftp://ftp.datasus.gov.br/d/BIMG2412_1.dbc", "a" * 64, 10, "2025-03-07T18:57"),
        SourceFile("ftp://ftp.datasus.gov.br/d/BIMG2412_2.dbc", "b" * 64, 20, "2025-03-07T18:57"),
    ]
    lake, staging, scope = _state_lake_and_staging(tmp_path)  # use this file's existing helper
    lake.publish_scope(
        "sia_bpa_individualizado",
        staging,
        scope=scope,
        source_sha256=aggregate_sha256(files),
        parser_version="p1",
        source_uri=files[0].uri,
        source_files=files,
    )
    (row,) = lake.publications()
    assert [s["source_uri"] for s in row["sources"]] == [f.uri for f in files]
    assert [s["source_bytes"] for s in row["sources"]] == [10, 20]
    assert row["source_sha256"] == aggregate_sha256(files)


def test_a_single_file_aggregate_is_the_file_digest() -> None:
    from omnisus.lake.publication import SourceFile, aggregate_sha256

    assert aggregate_sha256([SourceFile("ftp://h/d/x.dbc", "c" * 64)]) == "c" * 64


def test_inconsistent_source_files_are_refused(tmp_path) -> None:
    import pytest

    from omnisus.lake.publication import SourceFile

    lake, staging, scope = _state_lake_and_staging(tmp_path)
    with pytest.raises(ValueError, match="source files"):
        lake.publish_scope(
            "sia_bpa_individualizado",
            staging,
            scope=scope,
            source_sha256="d" * 64,
            parser_version="p1",
            source_uri="ftp://h/d/x.dbc",
            source_files=[SourceFile("ftp://h/d/x.dbc", "e" * 64)],
        )


def test_publications_without_source_rows_get_one_synthesized_entry(tmp_path) -> None:
    lake, staging, scope = _state_lake_and_staging(tmp_path)
    lake.publish_scope(
        "sim_obitos",
        staging,
        scope=scope,
        source_sha256="f" * 64,
        parser_version="p1",
        source_uri="ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc",
    )
    (row,) = lake.publications()
    assert row["sources"] == [
        {
            "ordinal": 0,
            "source_uri": row["source_uri"],
            "source_sha256": "f" * 64,
            "source_bytes": None,
            "source_modified": None,
        }
    ]


def test_publications_by_run_id_reads_only_that_runs_sources(tmp_path) -> None:
    from omnisus.lake.publication import SourceFile, aggregate_sha256

    lake, staging_a, scope_a = _state_lake_and_staging(tmp_path)
    files_a = [
        SourceFile("ftp://h/d/a1.dbc", "1" * 64),
        SourceFile("ftp://h/d/a2.dbc", "2" * 64),
    ]
    lake.publish_scope(
        "sia_bpa_individualizado",
        staging_a,
        scope=scope_a,
        source_sha256=aggregate_sha256(files_a),
        parser_version="p1",
        source_uri=files_a[0].uri,
        source_files=files_a,
        run_id="run-a",
    )
    staging_b = tmp_path / "b.parquet"
    pl.DataFrame({"ano": [2024], "mes": [12], "uf": ["SP"], "v": [1]}).write_parquet(staging_b)
    files_b = [
        SourceFile("ftp://h/d/b1.dbc", "3" * 64),
        SourceFile("ftp://h/d/b2.dbc", "4" * 64),
    ]
    lake.publish_scope(
        "sia_bpa_individualizado",
        staging_b,
        scope=ScopeKey(uf="SP", ano=2024, mes=12),
        source_sha256=aggregate_sha256(files_b),
        parser_version="p1",
        source_uri=files_b[0].uri,
        source_files=files_b,
        run_id="run-b",
    )
    (row,) = lake.publications(run_id="run-a")
    assert row["run_id"] == "run-a"
    assert [s["source_uri"] for s in row["sources"]] == [f.uri for f in files_a]


def test_publication_and_rows_rollback_together(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/p.ducklake") as lake:
        _publish(lake, tmp_path)
        with pytest.raises(RuntimeError), lake.transaction():
            _publish(lake, tmp_path, value=2, policy="replace", run_id="rollback")
            raise RuntimeError("abort")
        assert lake.connect().execute("SELECT v FROM lake.t").fetchall() == [(1,)]
        assert lake.publications(run_id="rollback") == []


def test_lost_commit_confirmation_can_be_reconciled(tmp_path):
    from omnisus.lake import CommitOutcomeUnknown
    from tests.support.connection_faults import FaultyConnection

    target = f"ducklake:{tmp_path}/lost.ducklake"
    with Lake.local(target) as lake:
        lake._con = FaultyConnection(
            lake.connect(), after={"COMMIT": RuntimeError("confirmation lost")}
        )
        with pytest.raises(CommitOutcomeUnknown):
            _publish(lake, tmp_path, run_id="recover-me")
    with Lake.local(target) as reopened:
        records = reopened.publications(run_id="recover-me")
        assert len(records) == 1 and records[0]["rows"] == 1
        assert reopened.connect().execute("SELECT v FROM lake.t").fetchall() == [(1,)]


def _publish_national(lake, tmp_path, ano=2023, value=1):
    path = tmp_path / f"BR-{ano}.parquet"
    pl.DataFrame({"_source_ano": [ano], "v": [value]}).write_parquet(path)
    return lake.publish_scope(
        "n",
        path,
        scope=ScopeKey(uf=None, ano=ano),
        source_sha256=hashlib.sha256(f"BR{ano}".encode()).hexdigest(),
        parser_version="parser-v1",
        run_id="national",
        partition_by=("_source_ano",),
    )


def test_publications_carry_a_decoded_scope(tmp_path):
    """The app decoded scope_json itself, including our private _source_ano
    encoding. The package now hands back the ScopeKey it wrote."""
    with Lake.local(f"ducklake:{tmp_path}/s.ducklake") as lake:
        _publish(lake, tmp_path)
        _publish_national(lake, tmp_path)
        scopes = {r["dataset"]: r["scope"] for r in lake.publications()}
        assert scopes == {
            "t": ScopeKey(uf="SP", ano=2024, mes=1),
            "n": ScopeKey(uf=None, ano=2023),
        }


def test_publications_expose_release_from_source_uri(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/r.ducklake") as lake:
        p = tmp_path / "d.parquet"
        pl.DataFrame(
            {"_source_ano": [2025], "_source_release": ["prelim"], "v": [1]}
        ).write_parquet(p)
        lake.publish_scope(
            "sinan_chagas",
            p,
            scope=ScopeKey(uf=None, ano=2025),
            source_sha256="a" * 64,
            parser_version="v1",
            source_uri="ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/CHAGBR25.dbc",
        )
        pl.DataFrame(
            {"_source_ano": [2024], "_source_release": ["final"], "v": [1]}
        ).write_parquet(p)
        lake.publish_scope(
            "sinan_chagas",
            p,
            scope=ScopeKey(uf=None, ano=2024),
            source_sha256="b" * 64,
            parser_version="v1",
            source_uri="ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS/CHAGBR24.dbc",
        )
        pl.DataFrame({"_source_ano": [2023], "v": [1]}).write_parquet(p)
        lake.publish_scope(
            "sinan_chagas",
            p,
            scope=ScopeKey(uf=None, ano=2023),
            source_sha256="c" * 64,
            parser_version="v1",
        )
        rows = {r["scope"].ano: r["release"] for r in lake.publications()}
    assert rows == {2025: "prelim", 2024: "final", 2023: None}


def test_scope_from_fields_rejects_shapes_this_version_never_writes():
    from omnisus.lake.publication import scope_from_fields

    assert scope_from_fields({"ano": 2024, "uf": "SP"}) == ScopeKey(uf="SP", ano=2024)
    assert scope_from_fields({"_source_ano": 2023}) == ScopeKey(uf=None, ano=2023)
    assert scope_from_fields({"product": "estimate", "ano": 2024}) is None
    assert scope_from_fields({"ano": "2024", "uf": "SP"}) is None


def test_delete_scope_removes_every_month_and_retires_their_publications(tmp_path):
    """A yearly scope on a monthly table covers all its months; the neighbouring
    UF and its publication are untouched."""
    from omnisus import DeletionResult

    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        _publish(lake, tmp_path)
        _publish(lake, tmp_path, value=2, mes=2)
        _publish(lake, tmp_path, uf="RJ", value=3)

        result = lake.delete_scope("t", ScopeKey(uf="SP", ano=2024))

        assert result == DeletionResult(rows_deleted=2, publications_retired=2)
        assert lake.connect().execute("SELECT uf, v FROM lake.t").fetchall() == [("RJ", 3)]
        assert {r["scope"]: r["active"] for r in lake.publications()} == {
            ScopeKey(uf="SP", ano=2024, mes=1): False,
            ScopeKey(uf="SP", ano=2024, mes=2): False,
            ScopeKey(uf="RJ", ano=2024, mes=1): True,
        }


def test_delete_scope_deletes_unmanaged_rows_without_retirements(tmp_path):
    from omnisus import DeletionResult

    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        lake.ingest("t", pl.DataFrame({"ano": [2024], "mes": [1], "uf": ["SP"], "v": [9]}).lazy())

        result = lake.delete_scope("t", ScopeKey(uf="SP", ano=2024, mes=1))

        assert result == DeletionResult(rows_deleted=1, publications_retired=0)
        assert lake.connect().execute("SELECT count(*) FROM lake.t").fetchone() == (0,)


def test_delete_scope_rejects_unknown_table_and_wrong_geography(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        _publish(lake, tmp_path)
        with pytest.raises(ValueError, match="unknown table"):
            lake.delete_scope("nope", ScopeKey(uf="SP", ano=2024))
        with pytest.raises(ValueError, match="national/state"):
            lake.delete_scope("t", ScopeKey(uf=None, ano=2024))
        with pytest.raises(ValueError, match="reserved"):
            lake.delete_scope("_omnisus_publications", ScopeKey(uf="SP", ano=2024))
        assert lake.connect().execute("SELECT count(*) FROM lake.t").fetchone() == (1,)


def test_delete_scope_rolls_back_with_the_callers_transaction(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        _publish(lake, tmp_path)
        with pytest.raises(RuntimeError), lake.transaction():
            lake.delete_scope("t", ScopeKey(uf="SP", ano=2024, mes=1))
            raise RuntimeError("abort")
        assert lake.connect().execute("SELECT v FROM lake.t").fetchall() == [(1,)]
        assert [r["active"] for r in lake.publications()] == [True]


def test_delete_scope_on_a_national_table(tmp_path):
    from omnisus import DeletionResult

    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        _publish_national(lake, tmp_path, ano=2023)
        _publish_national(lake, tmp_path, ano=2024, value=2)

        result = lake.delete_scope("n", ScopeKey(uf=None, ano=2023))

        assert result == DeletionResult(rows_deleted=1, publications_retired=1)
        assert lake.connect().execute("SELECT _source_ano FROM lake.n").fetchall() == [(2024,)]


def _publish_yearly(lake, tmp_path, uf="SP", value=1):
    path = tmp_path / f"y-{uf}-{value}.parquet"
    pl.DataFrame({"ano": [2023], "uf": [uf], "v": [value]}).write_parquet(path)
    return lake.publish_scope(
        "y",
        path,
        scope=ScopeKey(uf=uf, ano=2023),
        source_sha256=hashlib.sha256(f"y{uf}{value}".encode()).hexdigest(),
        parser_version="parser-v1",
        run_id="yearly",
        partition_by=("ano", "uf"),
    )


def test_delete_scope_on_a_yearly_table(tmp_path):
    from omnisus import DeletionResult

    with Lake.local(f"ducklake:{tmp_path}/d.ducklake") as lake:
        _publish_yearly(lake, tmp_path)
        _publish_yearly(lake, tmp_path, uf="RJ", value=2)

        result = lake.delete_scope("y", ScopeKey(uf="SP", ano=2023))

        assert result == DeletionResult(rows_deleted=1, publications_retired=1)
        assert lake.connect().execute("SELECT uf FROM lake.y").fetchall() == [("RJ",)]
        assert {r["scope"]: r["active"] for r in lake.publications(run_id="yearly")} == {
            ScopeKey(uf="SP", ano=2023): False,
            ScopeKey(uf="RJ", ano=2023): True,
        }


def test_parser_version_change_is_not_skip_same(tmp_path):
    with Lake.local(f"ducklake:{tmp_path}/v.ducklake") as lake:
        _publish(lake, tmp_path)
        with pytest.raises(ValueError, match="same file, imported by another parser version"):
            lake.publish_scope(
                "t",
                tmp_path / "SP-1-1.parquet",
                scope=ScopeKey(uf="SP", ano=2024, mes=1),
                source_sha256=hashlib.sha256(b"1").hexdigest(),
                parser_version="parser-v2",
                policy="skip_same",
            )


_LISTED = [("ftp://ftp.datasus.gov.br/d/BIMG2412.dbc", 10, "2025-03-07T18:57")]


def _publish_listed(lake, staging, scope, *, sizes_known=True):
    from omnisus.lake.publication import SourceFile

    ((uri, size, modified),) = _LISTED
    file = SourceFile(uri, "a" * 64, *((size, modified) if sizes_known else (None, None)))
    lake.publish_scope(
        "sia_bpa_individualizado",
        staging,
        scope=scope,
        source_sha256=file.sha256,
        parser_version="p1",
        source_uri=uri,
        source_files=[file],
    )


def _unchanged(lake, scope, parser_version="p1", listed=_LISTED):
    from omnisus.lake.publication import unchanged_since_listing

    return unchanged_since_listing(
        lake, "sia_bpa_individualizado", scope, parser_version=parser_version, listed=listed
    )


def test_unchanged_since_listing_needs_the_same_files_and_parser(tmp_path) -> None:
    lake, staging, scope = _state_lake_and_staging(tmp_path)
    with lake:
        assert not _unchanged(lake, scope)  # nothing published yet
        _publish_listed(lake, staging, scope)
        assert _unchanged(lake, scope)
        assert not _unchanged(lake, scope, parser_version="p2")
        ((uri, size, modified),) = _LISTED
        assert not _unchanged(lake, scope, listed=[(uri, size + 1, modified)])
        assert not _unchanged(lake, scope, listed=[(uri, size, "2025-03-07T18:58")])
        assert not _unchanged(lake, scope, listed=[*_LISTED, *_LISTED])


def test_unchanged_since_listing_is_false_for_a_scope_appended_twice(tmp_path) -> None:
    lake, staging, scope = _state_lake_and_staging(tmp_path)
    with lake:
        _publish_listed(lake, staging, scope)
        _publish_listed(lake, staging, scope)
        assert not _unchanged(lake, scope)


def test_unchanged_since_listing_is_false_without_recorded_size_and_time(tmp_path) -> None:
    """Publications written before sizes and times were recorded must download."""
    lake, staging, scope = _state_lake_and_staging(tmp_path)
    with lake:
        _publish_listed(lake, staging, scope, sizes_known=False)
        assert not _unchanged(lake, scope)


def test_unchanged_since_listing_is_false_with_rows_outside_the_publication(tmp_path) -> None:
    """Rows the manifest does not account for make skip_same raise; never skip them early."""
    lake, staging, scope = _state_lake_and_staging(tmp_path)
    with lake:
        _publish_listed(lake, staging, scope)
        lake.ingest(
            "sia_bpa_individualizado",
            pl.DataFrame({"ano": [2024], "mes": [12], "uf": ["MG"], "v": [2]}).lazy(),
        )
        assert not _unchanged(lake, scope)
