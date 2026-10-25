"""CNES names from the full CNES base on the DATASUS FTP.

The CNES-ST DBF has no establishment name. The monthly full base
(``ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_AAAAMM.ZIP``) does: its
``tbEstabelecimentoAAAAMM.csv`` carries ``CO_CNES``, ``NO_RAZAO_SOCIAL`` and
``NO_FANTASIA`` for every establishment in that competência. One file fills
``cnes_master`` in a single pass, instead of one API request per code.

Each row records the file name, its SHA-256 and the competência, because a name
reflects the month of the file: a CNES last seen in 2018 gets the name it had in
that file's month, which may differ from the name in 2018.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import urllib.request
import zipfile
from contextlib import nullcontext
from pathlib import Path

import structlog

from omnisus.lake import Lake
from omnisus.sources.cnes.importers.master import (
    _ensure_master_table,
    _prepare_master_rows,
    _upsert_master,
)

logger = structlog.get_logger(__name__)

FTP_URL = "ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_{competencia}.ZIP"
FTP_FONTE = "DATASUS FTP, base completa do CNES (tbEstabelecimento)"
_COMPETENCIA = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_base(competencia: str, dest_dir: Path) -> Path:
    """Download ``BASE_DE_DADOS_CNES_{competencia}.ZIP`` into ``dest_dir``."""
    if not _COMPETENCIA.match(competencia):
        raise ValueError("competencia must be AAAAMM")
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"BASE_DE_DADOS_CNES_{competencia}.ZIP"
    partial = final.with_suffix(".ZIP.part")
    url = FTP_URL.format(competencia=competencia)
    with urllib.request.urlopen(url, timeout=120) as resp, partial.open("wb") as fh:
        shutil.copyfileobj(resp, fh, 1 << 20)
    partial.replace(final)
    return final


def read_names(zip_path: Path, competencia: str) -> list[dict]:
    """One record per establishment in the base's tbEstabelecimento."""
    sha = _sha256(zip_path)
    wanted = f"tbestabelecimento{competencia}.csv"
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if Path(m).name.lower() == wanted]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name} has no single {wanted}")
        with zf.open(members[0]) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";"
            )
            missing = {"CO_CNES", "NO_RAZAO_SOCIAL", "NO_FANTASIA"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"tbEstabelecimento lacks columns: {sorted(missing)}")
            records: dict[str, dict] = {}
            for row in reader:
                code = row["CO_CNES"].strip()
                fantasia = row["NO_FANTASIA"].strip() or None
                razao = row["NO_RAZAO_SOCIAL"].strip() or None
                records[code] = {
                    "cnes": code,
                    "nome": fantasia or razao,
                    "nome_fantasia": fantasia,
                    "razao_social": razao,
                    "fonte": FTP_FONTE,
                    "arquivo": zip_path.name,
                    "sha256": sha,
                    "competencia_nome": competencia,
                }
    return list(records.values())


def import_cnes_master_ftp(
    competencia: str,
    *,
    zip_path: Path | None = None,
    download_dir: Path | None = None,
    target: str | None = None,
    only_missing: bool = True,
) -> int:
    """Fill ``cnes_master`` from one month of the full CNES base and refresh ``aux_cnes``.

    Args:
        competencia: ``AAAAMM`` of the base, e.g. ``"202312"``.
        zip_path: an already downloaded ``BASE_DE_DADOS_CNES_AAAAMM.ZIP``; when
            ``None`` the file is downloaded into ``download_dir``.
        download_dir: where to download; required when ``zip_path`` is ``None``.
        target: DuckLake target, as in the other importers.
        only_missing: ``True`` (default) keeps names already in ``cnes_master``, so
            loading a recent month first and older months after only fills gaps.

    Returns:
        The number of rows written.
    """
    if not _COMPETENCIA.match(competencia):
        raise ValueError("competencia must be AAAAMM")
    if zip_path is None:
        if download_dir is None:
            raise ValueError("pass zip_path or download_dir")
        zip_path = download_base(competencia, download_dir)
    records = read_names(Path(zip_path), competencia)
    _prepare_master_rows(records)
    with Lake.local(target) as lake:
        context = nullcontext() if lake.in_transaction else lake.transaction()
        with context:
            _ensure_master_table(lake)
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
    logger.info("cnes_master_ftp.done", competencia=competencia, written=len(records))
    return len(records)
