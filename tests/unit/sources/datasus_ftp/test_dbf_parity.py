"""Real native decoding must match independently specified values and Python."""

import gc
import math

import polars as pl
import pyarrow as pa
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from polars.testing import assert_frame_equal

from omnisus.sources.datasus_ftp import parse
from omnisus.sources.datasus_ftp.dbf_batches import open_dbf_batches
from omnisus.sources.datasus_ftp.staging import dbc_bytes_to_parquet
from tests.support.dbf import DBC_CASES, make_dbf

pytestmark = pytest.mark.rust_dbf


@pytest.mark.parametrize("batch_size", [7, 100_000])
@pytest.mark.parametrize("name,dataset", DBC_CASES)
def test_all_fixtures_exact_parity(
    name, dataset, batch_size, dbc_fixture, monkeypatch, tmp_path, request
):
    if dataset.startswith("sinan_"):  # SINAN national files carry D fields
        request.getfixturevalue("native_reads_date")
    raw = dbc_fixture(name).read_bytes()
    monkeypatch.setattr(parse, "BATCH_ROWS", batch_size)
    frames = []
    for backend in ("python", "rust"):
        monkeypatch.setenv("OMNISUS_DBF_BACKEND", backend)
        output = tmp_path / f"{backend}.parquet"
        result = dbc_bytes_to_parquet(raw, output, dataset=dataset, ano=2024, uf="RR", mes=1)
        frame = pl.read_parquet(output)
        assert result.rows == frame.height
        frames.append(frame)
    assert_frame_equal(frames[0], frames[1], check_exact=True)


def native():
    import omnisus_dbf

    return omnisus_dbf


@pytest.mark.parametrize("batch_rows", [1, 7, 1024, 100000])
def test_literal_values_nulls_and_lifetime(batch_rows):
    raw = make_dbf(
        [("TEXT", "C", 3, 0), ("VALUE", "N", 20, 0)],
        [
            b" \x81  " + b" " * 20,
            b"  a " + str(2**60 + 1).rjust(20).encode(),
            b"    " + b" " * 20,
            b"*xyz" + b" " * 20,
        ],
    )
    reader = native().open_reader(raw, encoding="latin-1", batch_rows=batch_rows)
    batches = list(reader)
    reader.close()
    reader.close()
    del reader, raw
    gc.collect()
    assert all(0 < b.num_rows <= batch_rows for b in batches)
    assert [r for b in batches for r in b.to_pylist()] == [
        {"TEXT": "\x81", "VALUE": None},
        {"TEXT": " a", "VALUE": 1152921504606846977},
        {"TEXT": "", "VALUE": None},
    ]


def test_batch_survives_reader_destroyed_before_exhaustion():
    raw = make_dbf([("X", "C", 1, 0)], [b" a", b" b"])
    reader = native().open_reader(raw, encoding="latin-1", batch_rows=1)
    first = next(reader)
    del reader, raw
    gc.collect()
    assert first.to_pylist() == [{"X": "a"}]


@pytest.mark.parametrize(
    "raw", [b"1,25", b"1e2", b"+42", b" ** ", b"\x00", b" 00042 ", b"\x0b42\x0b", b" \t1.5\x0b"]
)
def test_numeric_padding_matches_python(raw):
    data = make_dbf([("X", "N", len(raw), 0)], [b" " + raw])
    results = []
    for backend in ("python", "rust"):
        with open_dbf_batches(data, encoding="latin-1", batch_rows=1, backend=backend) as stream:
            results.append(next(stream))
    assert results[0].equals(results[1])


def test_negative_nan_preserves_sign():
    raw = make_dbf([("X", "N", 4, 0)], [b" -nan"])
    with open_dbf_batches(raw, encoding="latin-1", batch_rows=1, backend="rust") as reader:
        value = next(reader).to_pylist()[0]["X"]
    assert math.isnan(value)
    assert math.copysign(1, value) == -1


@pytest.mark.parametrize("eof", [b"", b"\x1a", b"\x1a\x00\x00padding"])
def test_bytes_after_eof_do_not_change_rows(eof):
    raw = make_dbf([("X", "C", 1, 0)], [b" a"], eof=eof)
    for backend in ("python", "rust"):
        with open_dbf_batches(raw, encoding="latin-1", batch_rows=1, backend=backend) as reader:
            assert [row for batch in reader for row in batch.to_pylist()] == [{"X": "a"}]


def test_encoding_error_is_not_replacement_text():
    raw = make_dbf([("X", "C", 1, 0)], [b" \x81"])
    with (
        open_dbf_batches(raw, encoding="cp1252", batch_rows=1, backend="rust") as reader,
        pytest.raises(UnicodeDecodeError),
    ):
        next(reader)


def _batches(raw, backend, batch_rows):
    with open_dbf_batches(
        raw, encoding="cp1252", batch_rows=batch_rows, backend=backend
    ) as reader:
        return list(reader)


@pytest.fixture
def native_reads_date(request):
    """omnisus-dbf 0.2.0 (on PyPI, pinned in uv.lock) rejects D fields; native.yml builds
    the wheel from this checkout and runs with --require-rust-dbf, so there it must pass."""
    try:
        native().open_reader(
            make_dbf([("X", "D", 8, 0)], [b" 20240101"]), encoding="latin-1", batch_rows=1
        ).close()
    except native().UnsupportedDbfError:
        if request.config.getoption("--require-rust-dbf"):
            pytest.fail("--require-rust-dbf: the installed omnisus-dbf rejects D fields")
        pytest.skip("installed omnisus-dbf predates D fields")


# dbfread2 parseD: int() of each slice, so whitespace, sign and underscores count.
@pytest.mark.parametrize(
    "raw",
    [
        b"20240101",
        b"99991231",
        b"00010101",
        b"2_240101",
        b"+0240101",
        b"        ",
        b"00000000",
        b"\x00" * 8,
        b"0 0\x000 0 ",
    ],
)
def test_date_matches_python(raw, native_reads_date):
    data = make_dbf([("X", "D", 8, 0)], [b" " + raw])
    python, rust = (_batches(data, backend, 1) for backend in ("python", "rust"))
    assert len(python) == len(rust) == 1
    assert python[0].equals(rust[0])


@pytest.mark.parametrize("raw", [b"20241301", b"20240230", b"2024ab01", b"-0240101", b"00000001"])
def test_invalid_date_fails_in_both_readers(raw, native_reads_date):
    data = make_dbf([("X", "D", 8, 0)], [b" " + raw])
    for backend in ("python", "rust"):
        with pytest.raises(ValueError):
            _batches(data, backend, 1)


@pytest.mark.parametrize("batch_rows", [1, 2])
def test_null_only_date_batch_matches_python(batch_rows, native_reads_date):
    data = make_dbf([("X", "D", 8, 0)], [b"         ", b" 20240101"])
    python, rust = (_batches(data, backend, batch_rows) for backend in ("python", "rust"))
    assert len(python) == len(rust)
    for p, r in zip(python, rust, strict=True):
        assert p.equals(r)
    assert rust[-1].schema.field("X").type == pa.date32()


@pytest.mark.parametrize("batch_rows", [1, 2])
def test_mixed_families_preserve_existing_output(monkeypatch, tmp_path, batch_rows):
    raw = make_dbf([("X", "N", 3, 0)], [b"   1", b" 1.5"])
    monkeypatch.setenv("OMNISUS_DBF_BACKEND", "rust")
    monkeypatch.setattr(parse, "BATCH_ROWS", batch_rows)
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda _: raw)
    target = tmp_path / "previous.parquet"
    target.write_bytes(b"previous")
    with pytest.raises((TypeError, ValueError)):
        dbc_bytes_to_parquet(b"ignored", target, dataset="sim_obitos")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("corrupt", ["late_number", "truncated", "early_eof"])
def test_corruption_never_publishes_partial_file(monkeypatch, tmp_path, corrupt):
    records = [b" 123", b" 456"]
    if corrupt == "late_number":
        records[1] = b" bad"
    elif corrupt == "early_eof":
        records[1] = b"\x1a456"
    raw = make_dbf([("X", "N", 3, 0)], records, declared_rows=3 if corrupt == "truncated" else 2)
    monkeypatch.setenv("OMNISUS_DBF_BACKEND", "rust")
    monkeypatch.setattr(parse, "BATCH_ROWS", 1)
    monkeypatch.setattr("omnisus.sources.datasus_ftp.dbc.decompress_bytes", lambda _: raw)
    target = tmp_path / "previous.parquet"
    target.write_bytes(b"previous")
    with pytest.raises((parse.DbfIntegrityError, ValueError)):
        dbc_bytes_to_parquet(b"ignored", target, dataset="sim_obitos")
    assert target.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [target]


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.integers(min_value=-(2**63), max_value=2**63 - 1), min_size=1, max_size=30),
    st.integers(1, 9),
)
def test_integer_batches_preserve_values(values, batch_rows):
    raw = make_dbf([("X", "N", 20, 0)], [b" " + str(v).rjust(20).encode() for v in values])
    with open_dbf_batches(
        raw, encoding="latin-1", batch_rows=batch_rows, backend="rust"
    ) as reader:
        batches = list(reader)
    assert [r["X"] for b in batches for r in b.to_pylist()] == values
    assert all(b.schema.field("X").type == pa.int64() for b in batches)


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=1024))
def test_arbitrary_input_fails_cleanly_or_reads_bounded_batches(raw):
    module = native()
    try:
        reader = module.open_reader(raw, encoding="latin-1", batch_rows=4)
        try:
            for batch in reader:
                assert 0 < batch.num_rows <= 4
        finally:
            reader.close()
    except (module.InvalidDbfError, module.UnsupportedDbfError, ValueError, TypeError):
        pass
