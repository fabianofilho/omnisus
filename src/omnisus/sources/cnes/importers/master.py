"""CNES Master importer — fetches establishment names from the public API.

The public CNES-ST DBF distributed by DATASUS doesn't carry the establishment
name; that lives only in the CNES web service. This importer fetches names
from ``https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}`` and
upserts them into ``lake.cnes_master``.

Typical workflow:

1. ``import_dataset("cnes_estabelecimentos", ...)`` or ``load`` populates
   ``lake.cnes_estabelecimentos`` (FTP) and refreshes ``aux_cnes``.
2. ``import_cnes_master()`` fetches names for every CNES that cnes_estabelecimentos marks
   pessoa jurídica (``pf_pj = '3'`` in every imported month) and that isn't yet in
   cnes_master. No other code gets a name, and no name holding a valid CPF is kept.
3. ``aux_cnes`` view auto-refreshes; explorer lookups now resolve names.

Re-runs are incremental by default (``only_missing=True``): codes already
in ``cnes_master`` are skipped, so periodic top-ups are cheap.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from contextlib import nullcontext

import httpx
import pyarrow as pa
import structlog

from omnisus._loop import run_sync
from omnisus.lake import Lake

logger = structlog.get_logger(__name__)

API_URL = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}"

# Provenance kept per row: which source gave the name, the file and its SHA-256,
# the competência (AAAAMM) the name reflects, and the server URL and MDTM of a file
# the importer downloaded. API rows carry only ``fonte``.
_PROVENANCE_COLUMNS = ("fonte", "arquivo", "sha256", "competencia_nome", "url", "modificado_em")
_MASTER_COLUMNS = ("cnes", "nome", "nome_fantasia", "razao_social", *_PROVENANCE_COLUMNS)
API_FONTE = "API dados abertos CNES (apidadosabertos.saude.gov.br)"

# Type alias: callback receives (done, total) after each fetch completes.
ProgressCallback = Callable[[int, int], None]


# Separators only where a CPF has them. 202312 writes the 11 digits plain or with spaces
# (evidence/2026-11-09-cnes-cpf-em-nome-pj.md); dots, dash and slash are the printed forms.
_CPF = re.compile(r"(?<!\d)\d{3}[. ]?\d{3}[. ]?\d{3}[-/ ]?\d{2}(?!\d)")

# Rows of cnes_master read per step of _delete_cpf_names.
_CPF_SCAN_BATCH = 10_000


def _contains_cpf(text: str | None) -> bool:
    """Whether ``text`` holds 11 digits in the CPF grouping (``ddd.ddd.ddd-dd``, the dots
    and dash optional or written as spaces, the dash also as a slash) with valid check digits.

    Some pessoa jurídica rows write the owner's name and CPF as the razão social, mostly
    empresário individual (evidence/2026-11-09-cnes-cpf-em-nome-pj.md): no such name is kept.
    """
    for match in _CPF.findall(text or ""):
        digits = [int(c) for c in re.sub(r"\D", "", match)]
        if len(set(digits)) == 1:
            continue
        if all(
            sum(digits[i] * (n + 1 - i) for i in range(n)) * 10 % 11 % 10 == digits[n]
            for n in (9, 10)
        ):
            return True
    return False


async def _fetch_one(client: httpx.AsyncClient, cnes: str) -> dict | None:
    """Fetch a single CNES record. Returns None on any failure (404, network).

    The API uses *unpadded* integer paths — passing ``"0123456"`` 404s.
    Strip leading zeros before the request, but keep the canonical 7-digit
    form in the returned record so it joins cleanly against ``cnes_estabelecimentos``.
    """
    cnes_canonical = cnes.zfill(7)
    cnes_path = cnes_canonical.lstrip("0") or "0"
    try:
        r = await client.get(API_URL.format(cnes=cnes_path), timeout=30)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        d = r.json()
    except ValueError:
        return None
    nome_fantasia = (d.get("nome_fantasia") or "").strip()
    razao_social = (d.get("nome_razao_social") or "").strip()
    if _contains_cpf(nome_fantasia) or _contains_cpf(razao_social):
        return None
    return {
        "cnes": cnes_canonical,
        "nome": nome_fantasia or razao_social or None,
        "nome_fantasia": nome_fantasia or None,
        "razao_social": razao_social or None,
        "fonte": API_FONTE,
    }


async def _fetch_all(
    codes: Sequence[str],
    *,
    concurrency: int,
    progress: ProgressCallback | None,
) -> list[dict]:
    """Fetch every code with bounded concurrency, reporting progress as we go."""
    sem = asyncio.Semaphore(concurrency)
    total = len(codes)
    done = 0
    records: list[dict] = []

    async with httpx.AsyncClient() as client:

        async def worker(c: str) -> dict | None:
            async with sem:
                return await _fetch_one(client, c)

        tasks = [asyncio.create_task(worker(c)) for c in codes]
        for fut in asyncio.as_completed(tasks):
            result = await fut
            if result is not None and result["nome"] is not None:
                records.append(result)
            done += 1
            if progress is not None:
                progress(done, total)

    return records


def _codes_from_lake(lake: Lake, *, only_missing: bool) -> list[str]:
    """Pull distinct non-null CNES codes from ``lake.cnes_estabelecimentos``.

    If ``only_missing=True`` and ``cnes_master`` already exists, returns only
    the codes not yet in ``cnes_master`` — making re-runs incremental.
    """
    if "cnes_estabelecimentos" not in lake.tables():
        return []
    con = lake.connect()
    if only_missing and "cnes_master" in lake.tables():
        sql = (
            f"SELECT DISTINCT s.cnes FROM {lake.alias}.cnes_estabelecimentos s "
            f"LEFT JOIN {lake.alias}.cnes_master m USING (cnes) "
            f"WHERE s.cnes IS NOT NULL AND s.cnes <> '' AND m.cnes IS NULL"
        )
    else:
        sql = f"SELECT DISTINCT cnes FROM {lake.alias}.cnes_estabelecimentos WHERE cnes IS NOT NULL AND cnes <> ''"
    return [r[0] for r in con.execute(sql).fetchall()]


def _pf_pj_codes(lake: Lake) -> tuple[set[str], set[str]]:
    """``(pessoa jurídica, not pessoa jurídica)`` codes, from ``cnes_estabelecimentos.pf_pj``.

    A code is pessoa jurídica only if every imported month marks it ``'3'``; ``'1'`` (pessoa
    física, whose names are the professional's) or any other value in some month makes it
    not. A code that is not in the table, or a lake whose table has no ``pf_pj``, is in
    neither set: unknown. Only the months already imported count, so a code marked ``'3'``
    in all of them and ``'1'`` in a month not imported is taken as pessoa jurídica.
    """
    if "cnes_estabelecimentos" not in lake.tables():
        return set(), set()
    con = lake.connect()
    describe = f"DESCRIBE {lake.alias}.cnes_estabelecimentos"
    if "pf_pj" not in {row[0] for row in con.execute(describe).fetchall()}:
        return set(), set()
    rows = con.execute(
        f"SELECT cnes, bool_and(coalesce(pf_pj, '') = '3') "
        f"FROM {lake.alias}.cnes_estabelecimentos WHERE cnes IS NOT NULL AND cnes <> '' "
        "GROUP BY cnes"
    ).fetchall()
    return {code for code, pj in rows if pj}, {code for code, pj in rows if not pj}


def _delete_master_codes(lake: Lake, codes: set[str]) -> int:
    """Remove the names of ``codes`` from ``cnes_master``; returns how many rows left."""
    if not codes:
        return 0
    con = lake.connect()
    con.register("_cnes_master_drop", pa.table({"cnes": sorted(codes)}))
    try:
        row = con.execute(
            f"DELETE FROM {lake.alias}.cnes_master "
            "WHERE cnes IN (SELECT cnes FROM _cnes_master_drop)"
        ).fetchone()
    finally:
        con.unregister("_cnes_master_drop")
    return int(row[0]) if row else 0


def _delete_cpf_names(lake: Lake) -> int:
    """Remove every ``cnes_master`` row with a CPF in ``nome``, ``nome_fantasia`` or
    ``razao_social`` (``_contains_cpf``); returns how many rows left.

    The whole table is read, not only the codes an import touches: a lake filled before the
    CPF rule, or from an answer that had no CPF then, may hold one in any code.
    """
    cursor = lake.connect().execute(
        f"SELECT cnes, nome, nome_fantasia, razao_social FROM {lake.alias}.cnes_master"
    )
    codes: set[str] = set()
    while batch := cursor.fetchmany(_CPF_SCAN_BATCH):
        codes.update(code for code, *names in batch if any(map(_contains_cpf, names)))
    return _delete_master_codes(lake, codes)


def _ensure_master_table(lake: Lake) -> None:
    """Create ``cnes_master`` if it doesn't exist yet (idempotent)."""
    lake.connect().execute(
        f"""
        CREATE TABLE IF NOT EXISTS {lake.alias}.cnes_master (
            cnes VARCHAR,
            nome VARCHAR,
            nome_fantasia VARCHAR,
            razao_social VARCHAR
        )
        """
    )
    # Provenance columns, added after the first release: tables created by the
    # API-only importer gain them on the next write.
    for column in _PROVENANCE_COLUMNS:
        lake.connect().execute(
            f"ALTER TABLE {lake.alias}.cnes_master ADD COLUMN IF NOT EXISTS {column} VARCHAR"
        )


def _upsert_master(lake: Lake, records: list[dict]) -> None:
    """Atomically replace the supplied CNES rows."""
    rows = _prepare_master_rows(records)
    if not rows:
        return
    context = nullcontext() if lake.in_transaction else lake.transaction()
    with context:
        con = lake.connect()
        # A whole monthly base is ~600k rows: go through an Arrow table instead of
        # one bound parameter per code.
        batch = pa.table({c: [row[i] for row in rows] for i, c in enumerate(_MASTER_COLUMNS)})
        con.register("_cnes_master_batch", batch)
        try:
            con.execute(
                f"DELETE FROM {lake.alias}.cnes_master "
                "WHERE cnes IN (SELECT cnes FROM _cnes_master_batch)"
            )
            names = ", ".join(_MASTER_COLUMNS)
            con.execute(
                f"INSERT INTO {lake.alias}.cnes_master ({names}) SELECT {names} FROM _cnes_master_batch"
            )
        finally:
            con.unregister("_cnes_master_batch")


def _prepare_master_rows(records: list[dict]) -> list[tuple[str | None, ...]]:
    prepared: dict[str, tuple[str | None, ...]] = {}
    for record in records:
        code = record.get("cnes")
        name = record.get("nome")
        if not isinstance(code, str) or len(code) != 7 or not code.isascii() or not code.isdigit():
            raise ValueError("CNES code must contain seven ASCII digits")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("CNES record must contain a usable name")
        fantasia = record.get("nome_fantasia")
        razao = record.get("razao_social")
        if any(value is not None and not isinstance(value, str) for value in (fantasia, razao)):
            raise ValueError("CNES optional names must be strings or None")
        provenance = tuple(record.get(column) for column in _PROVENANCE_COLUMNS)
        if any(value is not None and not isinstance(value, str) for value in provenance):
            raise ValueError("CNES provenance fields must be strings or None")
        row = (code, name, fantasia, razao, *provenance)
        if code in prepared and prepared[code] != row:
            raise ValueError(f"conflicting CNES records for {code}")
        prepared[code] = row
    return list(prepared.values())


def import_cnes_master(
    *,
    codes: Sequence[str] | None = None,
    target: str | None = None,
    concurrency: int = 5,
    only_missing: bool = True,
    progress: ProgressCallback | None = None,
) -> int:
    """Fetch establishment names from the CNES API and upsert ``lake.cnes_master``.

    Only a code ``cnes_estabelecimentos`` marks ``pf_pj = '3'`` in every imported month is
    fetched (``_pf_pj_codes``), listed or discovered. An answer with a valid CPF in a name
    is not written. In the transaction of the upsert, the stored names of the codes that are
    not pessoa jurídica go (``_delete_master_codes``), and so does every stored name with a
    valid CPF, of any code (``_delete_cpf_names``).

    Args:
        codes: explicit list of 7-digit CNES codes; only the pessoa jurídica ones are
            fetched. If ``None`` (default), pulls the pessoa jurídica codes from
            ``lake.cnes_estabelecimentos``.
        target: lake target string (same shape used by every other importer).
        concurrency: max concurrent API requests (default 5 to be polite).
        only_missing: when ``True`` (default), discovery (``codes=None``) skips codes
            already in ``cnes_master`` — re-runs become incremental top-ups. A code
            whose stored name held a CPF is missing after the removal.
        progress: optional ``(done, total)`` callback fired after each fetch
            completes for each unique requested code. Used by the backend to
            stream job progress to the UI.

    Returns the number of records written in this run. The table refresh and
    ``aux_cnes`` view refresh are published atomically after fetching.
    """
    with Lake.local(target) as lake:
        if codes is None:
            codes = _codes_from_lake(lake, only_missing=only_missing)
        codes = list(dict.fromkeys(str(code).zfill(7) for code in codes))
        if any(len(code) != 7 or not code.isascii() or not code.isdigit() for code in codes):
            raise ValueError("CNES codes must contain seven ASCII digits")
        pessoa_juridica, not_pessoa_juridica = _pf_pj_codes(lake)
        pessoa_fisica = sum(code in not_pessoa_juridica for code in codes)
        desconhecido = sum(
            code not in pessoa_juridica and code not in not_pessoa_juridica for code in codes
        )
        codes = [code for code in codes if code in pessoa_juridica]
        logger.info(
            "cnes_master.start",
            codes=len(codes),
            pessoa_fisica=pessoa_fisica,
            pf_pj_desconhecido=desconhecido,
            only_missing=only_missing,
        )

        records = run_sync(lambda: _fetch_all(codes, concurrency=concurrency, progress=progress))
        _prepare_master_rows(records)
        with lake.transaction():
            _ensure_master_table(lake)
            removed = _delete_master_codes(lake, not_pessoa_juridica)
            removed_cpf = _delete_cpf_names(lake)
            _upsert_master(lake, records)
            lake.ensure_aux_cnes_view()
        if removed or removed_cpf:
            logger.info(
                "cnes_master.names_removed", pessoa_fisica=removed, cpf_no_nome=removed_cpf
            )

        logger.info("cnes_master.done", fetched=len(records), requested=len(codes))
        return len(records)
