"""CNES names from the full CNES base on the DATASUS FTP.

The CNES-ST DBF has no establishment name. The monthly full base
(``ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_AAAAMM.ZIP``) does: its
``tbEstabelecimentoAAAAMM.csv`` carries ``CO_CNES``, ``NO_RAZAO_SOCIAL`` and
``NO_FANTASIA`` for every establishment in that competência. One file fills
``cnes_master`` in a single pass, instead of one API request per code.

Each row records the file name, its SHA-256 and the competência, because a name
reflects the month of the file: a CNES last seen in 2018 gets the name it had in
that file's month, which may differ from the name in 2018. A file this module
downloaded also records the server URL and the file's ``MDTM``; a file the caller
passes in has no known origin, so those two stay empty.

The zip is about 576 MB (202312), more than ``fetch_dbc_bytes`` keeps in memory, so it
goes to disk through the connection primitives of ``datasus_ftp._ftp``: the host
override, the retry on transient errors and the transient ``550`` of a dropped data
connection.
"""

from __future__ import annotations

import contextlib
import csv
import ftplib
import hashlib
import io
import re
import time
import zipfile
from pathlib import Path
from typing import NamedTuple

import structlog

from omnisus.lake import Lake
from omnisus.sources.cnes.importers.master import (
    _contains_cpf,
    _delete_cpf_names,
    _delete_master_codes,
    _ensure_master_table,
    _pf_pj_codes,
    _prepare_master_rows,
    _upsert_master,
)
from omnisus.sources.datasus_ftp._ftp import (
    TRANSIENT_FTP_ERRORS,
    DataConnectionLost,
    ftp_host,
    is_missing,
)
from omnisus.sources.datasus_ftp.fetch import FtpFileNotFound, FtpUnavailable, _still_there

logger = structlog.get_logger(__name__)

FTP_DIR = "/cnes"
FTP_NAME = "BASE_DE_DADOS_CNES_{competencia}.ZIP"
FTP_FONTE = "DATASUS FTP, base completa do CNES (tbEstabelecimento)"
PESSOA_FISICA = "1"  # TP_PFPJ: 1 pessoa física, 3 pessoa jurídica
PESSOA_JURIDICA = "3"
_COMPETENCIA = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Download(NamedTuple):
    path: Path
    url: str  # where the bytes came from, on the host in use
    modificado_em: str  # the file's MDTM on the server, ``YYYY-MM-DDTHH:MM``


def _fetch_to_disk(name: str, partial: Path, timeout_seconds: float) -> str:
    """One attempt: ``RETR`` ``name`` into ``partial``; returns its ``MDTM``."""
    with contextlib.closing(ftplib.FTP(timeout=timeout_seconds)) as ftp:
        ftp.connect(ftp_host())
        ftp.login()
        ftp.cwd(FTP_DIR)
        stamp = ftp.sendcmd(f"MDTM {name}").split()[-1]
        with partial.open("wb") as fh:
            try:
                ftp.retrbinary(f"RETR {name}", fh.write)
            except ftplib.error_perm as exc:
                if is_missing(exc) and _still_there(ftp, name):
                    raise DataConnectionLost(str(exc)) from exc
                raise
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[8:10]}:{stamp[10:12]}"


def download_base(
    competencia: str,
    dest_dir: Path,
    *,
    timeout_seconds: float = 120.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> Download:
    """Download ``BASE_DE_DADOS_CNES_{competencia}.ZIP`` into ``dest_dir``.

    Raises:
        FtpFileNotFound: the server has no such file. Terminal.
        FtpUnavailable: transient failures exhausted ``max_retries``.

    A failed download leaves no ``.ZIP.part`` behind.
    """
    if not _COMPETENCIA.match(competencia):
        raise ValueError("competencia must be AAAAMM")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = FTP_NAME.format(competencia=competencia)
    final = dest_dir / name
    partial = final.with_suffix(".ZIP.part")
    url = f"ftp://{ftp_host()}{FTP_DIR}/{name}"
    last_exc: BaseException | None = None
    try:
        for attempt in range(max_retries):
            try:
                modificado_em = _fetch_to_disk(name, partial, timeout_seconds)
            except TRANSIENT_FTP_ERRORS as exc:
                if is_missing(exc):
                    raise FtpFileNotFound(f"{url}: {exc}") from exc
                last_exc = exc
                if attempt + 1 < max_retries:
                    time.sleep(backoff_seconds * (2**attempt))
                continue
            partial.replace(final)
            logger.info("cnes_master_ftp.downloaded", url=url, attempt=attempt)
            return Download(final, url, modificado_em)
        raise FtpUnavailable(f"{url}: {max_retries} attempts failed") from last_exc
    finally:
        partial.unlink(missing_ok=True)


def read_base(
    zip_path: Path,
    competencia: str,
    *,
    url: str | None = None,
    modificado_em: str | None = None,
) -> tuple[list[dict], set[str]]:
    """``(records, codes that keep no name)`` of the base's tbEstabelecimento.

    Only a row with ``TP_PFPJ`` 3 (pessoa jurídica) gives a record; the codes of the other
    rows, pessoa física or an unknown value, come back apart so the importer can remove a
    name a lake already holds for them. A row with a valid CPF in a name gives no record,
    and its code does not come back: the importer removes every stored name with a CPF
    whatever the file says, and keeps a clean one.
    """
    sha = _sha256(zip_path)
    wanted = f"tbestabelecimento{competencia}.csv"
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if Path(m).name.lower() == wanted]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name} has no single {wanted}")
        with zf.open(members[0]) as raw:
            # latin-1, not cp1252: 202312 has no byte in 0x80-0x9F, so both read it the
            # same, and latin-1 cannot fail on a later month
            # (evidence/2026-10-31-cnes-tbestabelecimento-encoding.md).
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";"
            )
            missing = {"CO_CNES", "TP_PFPJ", "NO_RAZAO_SOCIAL", "NO_FANTASIA"} - set(
                reader.fieldnames or []
            )
            if missing:
                raise ValueError(f"tbEstabelecimento lacks columns: {sorted(missing)}")
            records: list[dict] = []
            sem_nome_publico: set[str] = set()
            pessoa_fisica = 0
            desconhecido = 0
            cpf_no_nome = 0
            sem_nome = 0
            for row in reader:
                code = row["CO_CNES"].strip()
                tp_pfpj = row["TP_PFPJ"].strip()
                if tp_pfpj != PESSOA_JURIDICA:
                    # NO_RAZAO_SOCIAL and NO_FANTASIA of a pessoa física carry the
                    # professional's name, and a value other than 1 or 3 cannot be told
                    # apart from one: only a pessoa jurídica keeps a name (AGENTS.md,
                    # "Never commit").
                    if tp_pfpj == PESSOA_FISICA:
                        pessoa_fisica += 1
                    else:
                        desconhecido += 1
                    sem_nome_publico.add(code)
                    continue
                fantasia = row["NO_FANTASIA"].strip() or None
                razao = row["NO_RAZAO_SOCIAL"].strip() or None
                if _contains_cpf(fantasia) or _contains_cpf(razao):
                    cpf_no_nome += 1
                    continue
                if not (fantasia or razao):
                    sem_nome += 1
                    continue
                records.append(
                    {
                        "cnes": code,
                        "nome": fantasia or razao,
                        "nome_fantasia": fantasia,
                        "razao_social": razao,
                        "fonte": FTP_FONTE,
                        "arquivo": zip_path.name,
                        "sha256": sha,
                        "competencia_nome": competencia,
                        "url": url,
                        "modificado_em": modificado_em,
                    }
                )
    logger.info(
        "cnes_master_ftp.rows_skipped",
        competencia=competencia,
        pessoa_fisica=pessoa_fisica,
        pf_pj_desconhecido=desconhecido,
        cpf_no_nome=cpf_no_nome,
        sem_nome=sem_nome,
    )
    # One answer per code, as on the API path: a repeated code with another name is an error.
    _prepare_master_rows(records)
    return list({record["cnes"]: record for record in records}.values()), sem_nome_publico


def import_cnes_master_ftp(
    competencia: str,
    *,
    zip_path: Path | None = None,
    download_dir: Path | None = None,
    target: str | None = None,
    only_missing: bool = True,
) -> int:
    """Fill ``cnes_master`` from one month of the full CNES base and refresh ``aux_cnes``.

    Only a pessoa jurídica row without a CPF in a name gives a name (``read_base``), and a
    code the lake's ST marks anything but ``'3'`` in some month gets none. In the same
    transaction as the upsert, the stored names of the codes without a public name go,
    and so does every stored name with a valid CPF, of any code.

    Args:
        competencia: ``AAAAMM`` of the base, e.g. ``"202312"``.
        zip_path: an already downloaded ``BASE_DE_DADOS_CNES_AAAAMM.ZIP``; when
            ``None`` the file is downloaded into ``download_dir``. Only a file
            downloaded here records its server ``url`` and ``modificado_em``.
        download_dir: where to download; required when ``zip_path`` is ``None``.
        target: DuckLake target, as in the other importers.
        only_missing: ``True`` (default) keeps names already in ``cnes_master``, so
            loading a recent month first and older months after only fills gaps. The
            removals of pessoa física and CPF names come first.

    Returns:
        The number of rows written.
    """
    if not _COMPETENCIA.match(competencia):
        raise ValueError("competencia must be AAAAMM")
    if zip_path is None:
        if download_dir is None:
            raise ValueError("pass zip_path or download_dir")
        downloaded = download_base(competencia, download_dir)
        records, sem_nome_publico = read_base(
            downloaded.path,
            competencia,
            url=downloaded.url,
            modificado_em=downloaded.modificado_em,
        )
    else:
        records, sem_nome_publico = read_base(Path(zip_path), competencia)
    with Lake.local(target) as lake:
        context = contextlib.nullcontext() if lake.in_transaction else lake.transaction()
        with context:
            _ensure_master_table(lake)
            # A code the lake's ST marks anything but pessoa jurídica in some month keeps
            # no name either, and a name a lake already holds for any of them goes.
            sem_nome_publico |= _pf_pj_codes(lake)[1]
            records = [r for r in records if r["cnes"] not in sem_nome_publico]
            removed = _delete_master_codes(lake, sem_nome_publico)
            # Before only_missing reads what is stored, so a clean row of the file fills a
            # code whose stored name had a CPF.
            removed_cpf = _delete_cpf_names(lake)
            if only_missing:
                have = {
                    r[0]
                    for r in lake.connect()
                    .execute(f"SELECT cnes FROM {lake.alias}.cnes_master WHERE nome IS NOT NULL")
                    .fetchall()
                }
                records = [r for r in records if r["cnes"] not in have]
            _upsert_master(lake, records)
            lake.ensure_aux_cnes_view()
    logger.info(
        "cnes_master_ftp.done",
        competencia=competencia,
        written=len(records),
        removed=removed,
        removed_cpf=removed_cpf,
    )
    return len(records)
