"""Tests for CNES names from the full CNES base (FTP zip -> lake.cnes_master).

The fixture is six records of the real tbEstabelecimento202312.csv
(tests/fixtures/FIXTURES.md): four hospitals with a nome fantasia, one of them
with a leading-zero code, one establishment with only a razão social, and one
pessoa física (TP_PFPJ=1) whose names are blanked in the fixture.

The real file has no row without a name and no repeated CO_CNES (checked on all 509875
rows of 202312), and the committed pessoa física has its names blanked. The tests that
need those cases build a ZIP from the fixture's CSV and say so: they are synthetic,
for malformed or sensitive input only.
"""

from __future__ import annotations

import csv
import ftplib
import hashlib
import zipfile
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from omnisus.lake import Lake
from omnisus.sources.cnes.importers.master_ftp import (
    FTP_FONTE,
    download_base,
    import_cnes_master_ftp,
    read_names,
)
from omnisus.sources.datasus_ftp.fetch import FtpFileNotFound, FtpUnavailable
from tests.support import fake_ftp

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "cnes_base"
    / "BASE_DE_DADOS_CNES_202312.ZIP"
)
CODES = ["0860638", "2319659", "2320886", "4339517", "6185177"]
PESSOA_FISICA = "3107981"
MEMBER = "tbEstabelecimento202312.csv"


def _synthetic_zip(tmp_path: Path, edit) -> Path:
    """Synthetic: the fixture's CSV text passed through ``edit``, zipped under the same name."""
    with zipfile.ZipFile(FIXTURE) as zf:
        text = zf.read(MEMBER).decode("latin-1")
    path = tmp_path / "BASE_DE_DADOS_CNES_202312.ZIP"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(MEMBER, edit(text).encode("latin-1"))
    return path


def _line_of(text: str, code: str) -> str:
    (line,) = [ln for ln in text.splitlines() if f'";"{code}";"' in ln]
    return line


def _seed(lake: Lake, codes: list[str]) -> None:
    con = lake.connect()
    con.execute(
        f"CREATE TABLE {lake.alias}.cnes_estabelecimentos "
        "(cnes VARCHAR, pf_pj VARCHAR, tp_unid VARCHAR, codufmun VARCHAR, ano INTEGER, mes INTEGER)"
    )
    con.executemany(
        f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES (?, '3', '05', '140010', 2023, 12)",
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


def test_a_pessoa_fisica_row_gives_no_name() -> None:
    """The committed pessoa física has its names blanked; the row is left out, not written empty."""
    with capture_logs() as logs:
        recs = {r["cnes"] for r in read_names(FIXTURE, "202312")}
    assert PESSOA_FISICA not in recs
    (skipped,) = [e for e in logs if e["event"] == "cnes_master_ftp.rows_skipped"]
    assert (skipped["pessoa_fisica"], skipped["pf_pj_desconhecido"], skipped["sem_nome"]) == (
        1,
        0,
        0,
    )


def test_a_pessoa_fisica_name_in_the_file_never_reaches_the_records(tmp_path: Path) -> None:
    """Synthetic: the real pessoa física has the professional's name in NO_FANTASIA (and in
    NO_RAZAO_SOCIAL); the fixture blanks it, so a name is put back here."""

    def with_names(text: str) -> str:
        text = _set_field(text, PESSOA_FISICA, "NO_RAZAO_SOCIAL", "DR EXEMPLO")
        return _set_field(text, PESSOA_FISICA, "NO_FANTASIA", "CONSULTORIO DR EXEMPLO")

    path = _synthetic_zip(tmp_path, with_names)
    assert "CONSULTORIO DR EXEMPLO" in zipfile.ZipFile(path).read(MEMBER).decode("latin-1")
    recs = read_names(path, "202312")
    assert sorted(r["cnes"] for r in recs) == CODES
    assert "EXEMPLO" not in repr(recs)


def test_a_row_without_any_name_is_skipped_and_the_month_still_loads(tmp_path: Path) -> None:
    """Synthetic: the real file has no row with both names empty; the razão social of the
    fixture's only fantasia-less establishment is blanked to make one."""

    def nameless(text: str) -> str:
        line = _line_of(text, "4339517")
        return text.replace(
            line, line.replace("ASSOCIACAO PESTALOZZI DE DIVINO DE SAO LOURENCO", "")
        )

    path = _synthetic_zip(tmp_path, nameless)
    with capture_logs() as logs:
        recs = read_names(path, "202312")
    assert sorted(r["cnes"] for r in recs) == [c for c in CODES if c != "4339517"]
    (skipped,) = [e for e in logs if e["event"] == "cnes_master_ftp.rows_skipped"]
    assert (skipped["pessoa_fisica"], skipped["sem_nome"]) == (1, 1)
    target = f"ducklake:{tmp_path}/sem_nome.ducklake"
    assert import_cnes_master_ftp("202312", zip_path=path, target=target) == 4


def test_a_repeated_code_with_another_name_is_a_conflict(tmp_path: Path) -> None:
    """Synthetic: the real file repeats no CO_CNES; a second line of 2320886 with another
    nome fantasia is added, as the API path would receive two answers for one code."""

    def repeated(text: str) -> str:
        line = _line_of(text, "2320886")
        return text + line.replace("HOSPITAL JOSE GUEDES CATAO", "OUTRO NOME") + "\n"

    path = _synthetic_zip(tmp_path, repeated)
    with pytest.raises(ValueError, match="conflicting CNES records for 2320886"):
        read_names(path, "202312")
    with pytest.raises(ValueError, match="conflicting CNES records for 2320886"):
        import_cnes_master_ftp("202312", zip_path=path, target=f"ducklake:{tmp_path}/c.ducklake")


def test_a_repeated_identical_line_is_one_record(tmp_path: Path) -> None:
    """Synthetic: the line of 2320886 twice, byte for byte."""
    path = _synthetic_zip(tmp_path, lambda text: text + _line_of(text, "2320886") + "\n")
    assert sorted(r["cnes"] for r in read_names(path, "202312")) == CODES


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
                f"SELECT cnes, nome, competencia_nome, fonte_nome "
                f"FROM {lake.alias}.aux_cnes WHERE cnes IN ('0860638', '4339517') ORDER BY cnes"
            )
            .fetchall()
        )
    assert rows == [
        ("0860638", "HOSPITAL HELIO MACEDO", "202312", FTP_FONTE),
        ("4339517", "ASSOCIACAO PESTALOZZI DE DIVINO DE SAO LOURENCO", "202312", FTP_FONTE),
    ]


def test_the_importer_is_public_next_to_import_cnes_master(tmp_path: Path) -> None:
    import omnisus as sus

    assert "import_cnes_master_ftp" in sus.__all__
    target = f"ducklake:{tmp_path}/publico.ducklake"
    assert sus.import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target) == 5


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


# Download: the FTP connection is `fake_ftp`; the bytes are the real fixture ZIP.
MDTM = "213 20240112212745"
URL = "ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_202312.ZIP"


def _serve_base(monkeypatch: pytest.MonkeyPatch, **replies: list[object]) -> list[str]:
    replies.setdefault("CWD", [fake_ftp.CWD_OK])
    replies.setdefault("MDTM", [MDTM])
    replies.setdefault("RETR", [FIXTURE.read_bytes()])
    replies.setdefault("SIZE", [FIXTURE.stat().st_size])
    return fake_ftp.serve(monkeypatch, **replies)


def test_download_writes_the_zip_and_returns_url_and_mdtm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OMNISUS_FTP_HOST", raising=False)
    _serve_base(monkeypatch)
    got = download_base("202312", tmp_path / "dl")
    assert got.path.read_bytes() == FIXTURE.read_bytes()
    assert (got.url, got.modificado_em) == (URL, "2024-01-12T21:27")
    assert [p.name for p in got.path.parent.iterdir()] == [got.path.name]


def test_download_retries_a_550_that_size_says_is_the_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent = _serve_base(monkeypatch, RETR=[fake_ftp.ABORTED, FIXTURE.read_bytes()])
    got = download_base("202312", tmp_path, backoff_seconds=0)
    assert got.path.read_bytes() == FIXTURE.read_bytes()
    assert sent.count("RETR") == 2


def test_a_failed_download_leaves_no_part_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve_base(monkeypatch, RETR=[fake_ftp.ABORTED])
    with pytest.raises(FtpUnavailable):
        download_base("202312", tmp_path, backoff_seconds=0)
    assert list(tmp_path.iterdir()) == []


def test_a_base_the_server_does_not_have_is_file_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve_base(monkeypatch, MDTM=[fake_ftp.NOT_FOUND])
    with pytest.raises(FtpFileNotFound):
        download_base("202312", tmp_path, backoff_seconds=0)
    assert list(tmp_path.iterdir()) == []


def test_download_goes_to_the_overridden_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _serve_base(monkeypatch)
    hosts: list[str] = []
    monkeypatch.setattr(ftplib.FTP, "connect", lambda _self, host, *_: hosts.append(host))
    monkeypatch.setenv("OMNISUS_FTP_HOST", "mirror.example.org")
    got = download_base("202312", tmp_path)
    assert hosts == ["mirror.example.org"]
    assert got.url == "ftp://mirror.example.org/cnes/BASE_DE_DADOS_CNES_202312.ZIP"


def test_a_downloaded_base_records_url_mdtm_and_sha256(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OMNISUS_FTP_HOST", raising=False)
    _serve_base(monkeypatch)
    target = f"ducklake:{tmp_path}/dl.ducklake"
    assert import_cnes_master_ftp("202312", download_dir=tmp_path / "dl", target=target) == 5
    with Lake.local(target) as lake:
        rows = (
            lake.connect()
            .execute(
                f"SELECT DISTINCT arquivo, url, modificado_em, sha256 FROM {lake.alias}.cnes_master"
            )
            .fetchall()
        )
    sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert rows == [("BASE_DE_DADOS_CNES_202312.ZIP", URL, "2024-01-12T21:27", sha)]


def test_a_zip_from_the_caller_has_no_url_or_mdtm(tmp_path: Path) -> None:
    """Nothing says where a caller's file came from, so no origin is recorded for it."""
    target = f"ducklake:{tmp_path}/local.ducklake"
    import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target)
    with Lake.local(target) as lake:
        rows = (
            lake.connect()
            .execute(f"SELECT DISTINCT url, modificado_em FROM {lake.alias}.cnes_master")
            .fetchall()
        )
    assert rows == [(None, None)]


def _set_field(text: str, code: str, column: str, value: str) -> str:
    """Synthetic: one field of the fixture row of ``code`` replaced, every other byte kept."""
    header = next(csv.reader([text.splitlines()[0]], delimiter=";"))
    line = _line_of(text, code)
    fields = next(csv.reader([line], delimiter=";"))
    fields[header.index(column)] = value
    return text.replace(line, ";".join(f'"{f}"' for f in fields))


@pytest.mark.parametrize("tp_pfpj", ["", "2", "9"])
def test_a_tp_pfpj_other_than_3_gives_no_name(tmp_path: Path, tp_pfpj: str) -> None:
    """Synthetic, malformed input: 202312 only has TP_PFPJ 1 and 3. Any other value, blank
    included, is not taken as a pessoa jurídica and is counted apart."""
    path = _synthetic_zip(tmp_path, lambda t: _set_field(t, "2320886", "TP_PFPJ", tp_pfpj))
    with capture_logs() as logs:
        recs = {r["cnes"] for r in read_names(path, "202312")}
    assert "2320886" not in recs
    (skipped,) = [e for e in logs if e["event"] == "cnes_master_ftp.rows_skipped"]
    assert (skipped["pessoa_fisica"], skipped["pf_pj_desconhecido"]) == (1, 1)


def test_a_pessoa_fisica_name_already_in_cnes_master_is_removed(tmp_path: Path) -> None:
    """A lake filled before the rule keeps the professional's name; the next FTP import
    removes it in the same transaction as the upsert, even with only_missing=True."""
    target = f"ducklake:{tmp_path}/ftp.ducklake"
    with Lake.local(target) as lake:
        _seed(lake, [*CODES, PESSOA_FISICA])
    import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target)
    with Lake.local(target) as lake:
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_master (cnes, nome) "
            f"VALUES ('{PESSOA_FISICA}', 'DR LEGADO')"
        )

    import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target)

    with Lake.local(target) as lake:
        master = {
            r[0]
            for r in lake.connect()
            .execute(f"SELECT cnes FROM {lake.alias}.cnes_master")
            .fetchall()
        }
    assert PESSOA_FISICA not in master
    assert set(CODES) <= master


def test_a_code_the_st_marks_pessoa_fisica_gets_no_name_from_the_file(tmp_path: Path) -> None:
    """The file says TP_PFPJ 3, the lake's ST says pf_pj '1' in some month: no name."""
    target = f"ducklake:{tmp_path}/ftp.ducklake"
    with Lake.local(target) as lake:
        _seed(lake, CODES)
        lake.connect().execute(
            f"INSERT INTO {lake.alias}.cnes_estabelecimentos VALUES ('2320886', '1', '05', '140010', 2023, 11)"
        )
    import_cnes_master_ftp("202312", zip_path=FIXTURE, target=target)
    with Lake.local(target) as lake:
        master = {
            r[0]
            for r in lake.connect()
            .execute(f"SELECT cnes FROM {lake.alias}.cnes_master")
            .fetchall()
        }
    assert "2320886" not in master
    assert set(CODES) - {"2320886"} <= master


@pytest.mark.parametrize("column", ["NO_RAZAO_SOCIAL", "NO_FANTASIA"])
def test_a_name_with_a_valid_cpf_gives_no_name(tmp_path: Path, column: str) -> None:
    """Synthetic, sensitive input: 546 rows of 202312 with TP_PFPJ 3 carry a valid CPF in a
    name, mostly empresário individual (evidence/2026-11-09-cnes-cpf-em-nome-pj.md). The
    CPF here is a made-up one with valid check digits. No name of that row is kept."""
    path = _synthetic_zip(
        tmp_path, lambda t: _set_field(t, "2320886", column, "FULANO DE TAL 52998224725")
    )
    with capture_logs() as logs:
        recs = {r["cnes"] for r in read_names(path, "202312")}
    assert "2320886" not in recs
    (skipped,) = [e for e in logs if e["event"] == "cnes_master_ftp.rows_skipped"]
    assert skipped["cpf_no_nome"] == 1


def test_eleven_digits_that_fail_the_cpf_check_keep_the_name(tmp_path: Path) -> None:
    """Synthetic: an 11-digit run whose check digits do not match is not a CPF."""
    path = _synthetic_zip(
        tmp_path, lambda t: _set_field(t, "2320886", "NO_FANTASIA", "UNIDADE 52998224724")
    )
    recs = {r["cnes"]: r for r in read_names(path, "202312")}
    assert recs["2320886"]["nome"] == "UNIDADE 52998224724"
