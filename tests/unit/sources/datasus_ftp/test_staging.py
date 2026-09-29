from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from omnisus.sources.datasus_ftp import parse
from omnisus.sources.datasus_ftp.staging import dbc_bytes_to_parquet


def records(monkeypatch, values, batch=2):
    monkeypatch.setenv("OMNISUS_DBF_BACKEND", "python")
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda _: b"fake")
    monkeypatch.setattr(parse, "_stream_records", lambda *_args, **_kwargs: iter(values))
    monkeypatch.setattr(parse, "BATCH_ROWS", batch)


def test_null_first_and_missing_columns_are_preserved(monkeypatch, tmp_path):
    records(monkeypatch, [{"X": None}, {"X": None}, {"X": 2**60 + 1, "Y": "a"}])
    target = tmp_path / "output.parquet"
    result = dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos", ano=2023, uf="RR", mes=1)
    df = pl.read_parquet(target)
    assert result.rows == 3 and result.bytes == target.stat().st_size
    assert df["x"].to_list() == [None, None, 2**60 + 1]
    assert df["y"].to_list() == [None, None, "a"]
    assert df["ano"].dtype == pl.UInt16
    assert df["mes"].to_list() == [1, 1, 1]
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize(
    "values,batch", [([1, 1.5], 2), ([2**60 + 1, 1.5], 1), ([Decimal("1.1"), 1], 2), ([1, "a"], 1)]
)
def test_incompatible_families_rejected_without_publishing(monkeypatch, tmp_path, values, batch):
    records(monkeypatch, [{"X": value} for value in values], batch)
    target = tmp_path / "output.parquet"
    target.write_bytes(b"previous")
    with pytest.raises((TypeError, ValueError)):
        dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos", ano=2023, uf="RR")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


def test_legacy_parser_rejects_lossy_batches(monkeypatch):
    records(monkeypatch, [{"X": 2**60 + 1}, {"X": 1.5}], 1)
    with pytest.raises((TypeError, ValueError)):
        parse.dbc_bytes_to_lazyframe(b"x", dataset="sim_obitos")


def test_fixture_multiple_batches_equivalent(dbc_fixture, monkeypatch, tmp_path):
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    expected = parse.dbc_bytes_to_lazyframe(raw, dataset="sim_obitos", ano=2023, uf="RR").collect()
    monkeypatch.setattr(parse, "BATCH_ROWS", 7)
    target = tmp_path / "output.parquet"
    dbc_bytes_to_parquet(raw, target, dataset="sim_obitos", ano=2023, uf="RR")
    assert pl.read_parquet(target).equals(expected)


def test_integrity_failure_does_not_publish(monkeypatch, tmp_path):
    records(monkeypatch, [{"X": 1}])

    def fail(*args, **kwargs):
        raise parse.DbfIntegrityError("early stop")

    monkeypatch.setattr(parse, "_check_record_count", fail)
    with pytest.raises(parse.DbfIntegrityError):
        dbc_bytes_to_parquet(
            b"x", tmp_path / "out.parquet", dataset="sim_obitos", ano=2023, uf="RR"
        )
    assert not list(tmp_path.iterdir())


def test_cancelled_stream_cleans_spool_and_closes_generator(monkeypatch, tmp_path):
    records(monkeypatch, [], 1)
    closed = []

    def interrupted(*args, **kwargs):
        try:
            yield {"X": 1}
            raise KeyboardInterrupt()
        finally:
            closed.append(True)

    monkeypatch.setattr(parse, "_stream_records", interrupted)
    with pytest.raises(KeyboardInterrupt):
        dbc_bytes_to_parquet(b"x", tmp_path / "out.parquet", dataset="sim_obitos")
    assert closed == [True]
    assert not list(tmp_path.iterdir())


def test_empty_staging_preserves_partition_schema(monkeypatch, tmp_path):
    records(monkeypatch, [])
    target = tmp_path / "out.parquet"
    result = dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos", ano=2023, uf="RR")
    assert result.rows == 0
    assert pl.read_parquet(target)["ano"].dtype == pl.UInt16


def test_staging_stamps_source_release(monkeypatch, tmp_path):
    from tests.support.dbf import make_dbf

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    raw = make_dbf([("NU_ANO", "C", 4, 0)], [b" 2025"])
    out = tmp_path / "s.parquet"
    dbc_bytes_to_parquet(raw, out, dataset="sinan_chagas", source_ano=2025, release="prelim")
    frame = pl.read_parquet(out)
    assert frame["_source_release"].to_list() == ["prelim"]
    assert frame["_source_ano"].to_list() == [2025]


def test_empty_staging_stamps_source_release_column(monkeypatch, tmp_path):
    records(monkeypatch, [])
    target = tmp_path / "out.parquet"
    dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos", ano=2023, uf="RR", release="final")
    frame = pl.read_parquet(target)
    assert frame["_source_release"].dtype == pl.Utf8
    assert list(frame["_source_release"]) == []


def test_failed_atomic_replace_preserves_target_and_cleans_spool(monkeypatch, tmp_path):
    from omnisus.sources.datasus_ftp import staging

    records(monkeypatch, [{"X": 1}, {"X": 2}], 1)
    target = tmp_path / "previous.parquet"
    target.write_bytes(b"previous")

    def fail_replace(source, destination):
        assert pl.read_parquet(source)["x"].to_list() == [1, 2]
        raise OSError("disk publication failed")

    monkeypatch.setattr(staging.os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication"):
        dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


def test_python_dbf_write_failure_removes_incomplete_file(monkeypatch, tmp_path):
    from tests.support.dbf import make_dbf

    original = parse.tempfile.NamedTemporaryFile
    monkeypatch.setattr(parse.tempfile, "tempdir", str(tmp_path))

    class BrokenFile:
        def __init__(self, **kwargs):
            self.file = original(**kwargs)
            self.name = self.file.name

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            self.file.write(data[:8])
            raise OSError("disk full during DBF write")

    monkeypatch.setattr(parse.tempfile, "NamedTemporaryFile", BrokenFile)
    stream = parse._stream_records(make_dbf([("X", "C", 1, 0)], [b" a"]), "latin-1")
    with pytest.raises(OSError, match="disk full"):
        next(stream)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.rust_dbf
@pytest.mark.parametrize("phase,fail_on", [("ipc", 2), ("parquet", 1)])
def test_writer_failure_closes_native_reader_and_preserves_target(
    monkeypatch, tmp_path, phase, fail_on
):
    import omnisus_dbf

    from omnisus.sources.datasus_ftp import staging
    from tests.support.dbf import make_dbf

    raw = make_dbf([("X", "C", 1, 0)], [b" a", b" b", b" c"])
    monkeypatch.setenv("OMNISUS_DBF_BACKEND", "rust")
    monkeypatch.setattr(parse, "BATCH_ROWS", 1)
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda _: raw)
    native_open = omnisus_dbf.open_reader
    opened = []

    def track_reader(*args, **kwargs):
        reader = native_open(*args, **kwargs)
        opened.append(reader)
        return reader

    monkeypatch.setattr(omnisus_dbf, "open_reader", track_reader)
    owner, name = (staging.pa.ipc, "new_file") if phase == "ipc" else (staging.pq, "ParquetWriter")
    original_writer = getattr(owner, name)
    writes = []

    class BrokenWriter:
        def __init__(self, *args, **kwargs):
            self.writer = original_writer(*args, **kwargs)

        def __enter__(self):
            self.writer.__enter__()
            return self

        def __exit__(self, *args):
            return self.writer.__exit__(*args)

        def write_table(self, table):
            self.writer.write_table(table)
            writes.append(table.num_rows)
            if len(writes) == fail_on:
                raise OSError(f"disk full during {phase} write")

    monkeypatch.setattr(owner, name, BrokenWriter)
    target = tmp_path / "previous.parquet"
    target.write_bytes(b"previous")
    with pytest.raises(OSError, match="disk full"):
        dbc_bytes_to_parquet(b"x", target, dataset="sim_obitos")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]
    assert len(opened) == 1
    with pytest.raises(StopIteration):
        next(opened[0])


def _dictionary_with_a_date(tmp_path, extra_fields=()):
    """Ad-hoc dicionario declaring dt_x as a date, written to a temp YAML."""
    import yaml

    fields = [{"name": "dt_x", "type": "date"}, {"name": "v", "type": "string"}]
    fields.extend({"name": name, "type": "string"} for name in extra_fields)
    path = tmp_path / "adhoc.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "adhoc",
                "title": "Ad-hoc",
                "encoding": "latin-1",
                "x-version": "1.0.0",
                "x-source-format": "dbc",
                "x-partitions": ["ano"],
                "schema": {"fields": fields},
            }
        ),
        encoding="utf-8",
    )
    return path


def _adhoc_dataset(dictionary):
    from omnisus.sources.datasus_ftp.datasets import Dataset

    return Dataset(
        name="adhoc",
        prefix="AD0",
        ftp_dir="/dissemin/publicos/X",
        cadence="yearly",
        partition_by=("ano", "uf"),
        coverage=((2000, 1), None),
        dictionary=dictionary,
    )


def test_a_column_blank_in_one_year_takes_its_descriptor_type(monkeypatch, tmp_path):
    """A DATE column that is empty in the older file must not pin the lake column
    to the type of "nothing" and reject the next year's real dates
    (sinan_hanseniase: dt_transrm is blank in every record of HANSBR23)."""
    import omnisus as sus
    from omnisus.sources._base import ScopeKey
    from omnisus.sources.datasus_ftp._runner import ingest_raw
    from tests.support.dbf import make_dbf
    from tests.support.listings import listed

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    fields = [("DT_X", "D", 8, 0), ("V", "C", 1, 0)]
    blank = make_dbf(fields, [b" " + b" " * 8 + b"a", b" " + b" " * 8 + b"b"])
    dated = make_dbf(fields, [b" 20240115c"])
    d = _adhoc_dataset(_dictionary_with_a_date(tmp_path))

    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:
        older, newer = ScopeKey(uf="RR", ano=2023), ScopeKey(uf="RR", ano=2024)
        ingest_raw(d, older, listed(d, older, blank), lake, policy="append")
        ingest_raw(d, newer, listed(d, newer, dated), lake, policy="append")

        assert len(lake.publications()) == 2
        frame = lake.connect().sql("SELECT dt_x, ano FROM lake.adhoc ORDER BY ano").pl()
        assert frame["dt_x"].dtype == pl.Date
        assert frame["dt_x"].to_list() == [None, None, date(2024, 1, 15)]


def test_an_undeclared_blank_column_takes_its_descriptor_type(monkeypatch, tmp_path):
    """The header types every field, so a blank column the dicionario never
    mentions is typed too — as the integer its ``N`` descriptor stages."""
    from tests.support.dbf import make_dbf

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    raw = make_dbf(
        [("DT_X", "D", 8, 0), ("V", "C", 1, 0), ("EXTRA", "N", 3, 0)],
        [b" " + b" " * 8 + b"a" + b"   "],
    )
    target = tmp_path / "output.parquet"
    dbc_bytes_to_parquet(
        raw, target, dataset="adhoc", dictionary=_dictionary_with_a_date(tmp_path), ano=2023
    )
    schema = pl.read_parquet_schema(target)
    assert schema["dt_x"] == pl.Date
    assert schema["extra"] == pl.Int64


def test_a_blank_column_the_dictionary_mistypes_still_accepts_the_next_file(monkeypatch, tmp_path):
    """Curated dictionaries state semantics, not physical types: ``rubrica`` is
    an ``N`` field sih_aih_reduzida declares as ``string``. Typing a blank
    column from the dicionario would pin the lake to VARCHAR and make the next
    month's integers an unsafe schema change."""
    import omnisus as sus
    from omnisus.sources._base import ScopeKey
    from omnisus.sources.datasus_ftp._runner import ingest_raw
    from tests.support.dbf import make_dbf
    from tests.support.listings import listed

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    fields = [("DT_X", "D", 8, 0), ("V", "C", 1, 0), ("N_X", "N", 4, 0)]
    blank = make_dbf(fields, [b" " + b" " * 8 + b"a" + b"    "])
    numbered = make_dbf(fields, [b" " + b" " * 8 + b"b" + b"  42"])
    d = _adhoc_dataset(_dictionary_with_a_date(tmp_path, extra_fields=("n_x",)))

    with sus.Lake.local(f"ducklake:{tmp_path}/lake.ducklake") as lake:
        older, newer = ScopeKey(uf="RR", ano=2023), ScopeKey(uf="RR", ano=2024)
        ingest_raw(d, older, listed(d, older, blank), lake, policy="append")
        ingest_raw(d, newer, listed(d, newer, numbered), lake, policy="append")

        assert len(lake.publications()) == 2
        frame = lake.connect().sql("SELECT n_x FROM lake.adhoc ORDER BY ano").pl()
        assert frame["n_x"].dtype.is_integer()
        assert frame["n_x"].to_list() == [None, 42]


def test_an_empty_file_is_typed_from_its_header(monkeypatch, tmp_path):
    """A zero-record file has no values to disagree with its descriptors, so
    every column is typed from the same source as a blank column's."""
    from tests.support.dbf import make_dbf

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    raw = make_dbf([("V", "C", 1, 0), ("N_X", "N", 4, 0), ("DT_X", "D", 8, 0)], [])
    target = tmp_path / "output.parquet"
    result = dbc_bytes_to_parquet(
        raw, target, dataset="adhoc", dictionary=_dictionary_with_a_date(tmp_path), ano=2023
    )
    schema = pl.read_parquet_schema(target)
    assert result.rows == 0
    assert schema["v"] == pl.String
    assert schema["n_x"] == pl.Int64
    assert schema["dt_x"] == pl.Date


def test_parts_with_different_layouts_are_refused(monkeypatch, tmp_path):
    """Parts of one month are one file cut in pieces; a different header means
    they are not, and staging them together would silently mix schemas."""
    from tests.support.dbf import make_dbf

    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda raw: raw)
    first = make_dbf([("DT_X", "D", 8, 0), ("V", "C", 1, 0)], [b" 20240115a"])
    second = make_dbf([("DT_X", "D", 8, 0), ("V", "N", 1, 0)], [b" 202401151"])
    with pytest.raises(ValueError, match="different DBF layouts"):
        dbc_bytes_to_parquet(
            [first, second],
            tmp_path / "output.parquet",
            dataset="adhoc",
            dictionary=_dictionary_with_a_date(tmp_path),
            ano=2024,
        )
