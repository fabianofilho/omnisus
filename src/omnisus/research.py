"""Helpers for citing a lake snapshot and importing without duplicating research rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from omnisus._version import __version__
from omnisus.lake import Lake, LakeReader
from omnisus.lake.publication import ImportPolicy
from omnisus.lake.sql import qualified, quote_identifier
from omnisus.sources._base import ImportReport, ScopeKey
from omnisus.sources.datasus_ftp._runner import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
)
from omnisus.sources.datasus_ftp.datasets import Dataset
from omnisus.sources.datasus_ftp.fetch import (
    DEFAULT_MAX_INFLIGHT_BYTES,
    DEFAULT_MAX_PAYLOAD_BYTES,
)
from omnisus.transforms.dictionaries import load_dicionario


@dataclass(frozen=True)
class Citation:
    """Structured citation plus the Portuguese paragraph the guide uses."""

    text: str
    snapshot_id: int
    omnisus: str
    dataset: str | None
    run_id: str | None
    publications: tuple[dict[str, Any], ...]


def latest_snapshot_id(lake: Lake | LakeReader) -> int:
    """The newest snapshot of the lake, to pin a query or a citation to it.

    Args:
        lake: An open :class:`~omnisus.Lake` or :class:`~omnisus.LakeReader`.

    Returns:
        The snapshot id; pass it to ``LakeReader(snapshot_id=...)`` and :func:`cite`.

    Raises:
        LookupError: the lake has no snapshots yet.

    Examples:
        >>> import omnisus as odb
        >>> with odb.LakeReader() as lake:  # doctest: +SKIP
        ...     snapshot = odb.latest_snapshot_id(lake)
    """
    snaps = lake.snapshots()
    if not snaps:
        raise LookupError("lake has no snapshots")
    raw = snaps[-1]["snapshot_id"]
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    raise TypeError(f"snapshot_id must be int, got {type(raw).__name__}")


def import_research(
    dataset: str | Dataset,
    *,
    scopes: Sequence[ScopeKey],
    run_id: str,
    target: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    batch_size: int = DEFAULT_BATCH_SIZE,
    policy: ImportPolicy = "skip_same",
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    max_inflight_bytes: int = DEFAULT_MAX_INFLIGHT_BYTES,
) -> ImportReport:
    """Import for a citable run: you choose the ``run_id`` before anything downloads.

    Same as :func:`~omnisus.import_dataset`, but ``run_id`` is required, so an
    interrupted run is reconciled through ``Lake.publications(run_id=...)``, and the
    default policy never duplicates rows on a retry.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a :class:`~omnisus.Dataset`.
        scopes: The scopes to import, e.g. from :func:`~omnisus.scopes_for`.
        run_id: Your non-empty identifier for this run, e.g. ``"tese-cap2-2026-09-23"``.
        target: DuckLake target; ``None`` (default) is ``data/raw/omnisus.ducklake``
            under the working directory, or under ``$OMNISUS_DATA_DIR``.
        concurrency: Downloads in flight; see :func:`~omnisus.import_dataset`.
        batch_size: Scopes committed per DuckLake transaction.
        policy: ``"skip_same"`` (default), ``"error_if_exists"`` or ``"replace"``.
            ``"append"`` is refused: it duplicates rows on retry.
        max_payload_bytes: Largest compressed download accepted per file (512 MiB).
        max_inflight_bytes: Compressed bytes held at once before parsing (1 GiB).

    Returns:
        The :class:`~omnisus.ImportReport`, as :func:`~omnisus.import_dataset`.

    Raises:
        ValueError: ``run_id`` is empty or ``policy`` is ``"append"``.
        ImportAbortedError: as :func:`~omnisus.import_dataset`.

    Examples:
        >>> import omnisus as odb
        >>> scopes = odb.scopes_for("sim_obitos", years=[2023], ufs=["RR"])
        >>> odb.import_research("sim_obitos", scopes=scopes, run_id="cap2")  # doctest: +SKIP
    """
    from omnisus import import_dataset

    if not str(run_id).strip():
        raise ValueError("import_research requires a nonempty run_id")
    if policy == "append":
        raise ValueError(
            "import_research refuses policy='append'; use import_dataset or policy='replace'"
        )
    return import_dataset(
        dataset,
        scopes=scopes,
        target=target,
        concurrency=concurrency,
        batch_size=batch_size,
        policy=policy,
        run_id=run_id,
        max_payload_bytes=max_payload_bytes,
        max_inflight_bytes=max_inflight_bytes,
    )


def municipality_join_key(value: object, *, digits: int = 6) -> str | None:
    """The leftmost digits of an IBGE municipality code, to join bases on them.

    DATASUS bases use 6 digits and IBGE uses 7 (with a check digit). This keeps the
    leftmost ``digits`` and never pads or invents a check digit.

    Args:
        value: A municipality code, e.g. ``"3550308"`` or ``355030``.
        digits: ``6`` (default) or ``7``.

    Returns:
        The key as text, or ``None`` for ``None`` or a blank value.

    Raises:
        ValueError: ``digits`` is not 6 or 7.

    Examples:
        >>> import omnisus as odb
        >>> odb.municipality_join_key("3550308")
        '355030'
        >>> odb.municipality_join_key(" ") is None
        True
    """
    _require_join_digits(digits)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:digits]


def municipality_join_key_sql(column: str, *, digits: int = 6) -> str:
    """SQL for :func:`municipality_join_key` on a lake column.

    Args:
        column: Column name, e.g. ``"codmunres"``.
        digits: ``6`` (default) or ``7``.

    Returns:
        A DuckDB expression to use in ``SELECT`` or ``JOIN ... ON``.

    Raises:
        ValueError: ``digits`` is not 6 or 7.

    Examples:
        >>> import omnisus as odb
        >>> odb.municipality_join_key_sql("codmunres")
        'left(trim(CAST("codmunres" AS VARCHAR)), 6)'
    """
    _require_join_digits(digits)
    ident = quote_identifier(column)
    return f"left(trim(CAST({ident} AS VARCHAR)), {digits})"


def reference_join_sql(
    dataset: str, field: str, *, alias: str = "d", lake_alias: str = "lake"
) -> str:
    """The ``LEFT JOIN`` from a coded field to the vocabulary its dictionary declares.

    The declaration is the field's ``foreignKeys`` entry; an ``x-join-rule`` adds a
    condition. Nothing joins at import: paste the result after
    ``FROM lake.<dataset> AS <alias>``.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``.
        field: A field that declares a reference, e.g. ``"causabas"`` (CID-10) or
            ``"ocup"`` (CBO).
        alias: Alias of the dataset table in your query (default ``"d"``).
        lake_alias: Alias the lake is attached as (default ``"lake"``).

    Returns:
        SQL text; the vocabulary is aliased ``ref_<field>``.

    Raises:
        ValueError: the field declares no reference, or more than one.
        FileNotFoundError: ``dataset`` has no packaged dictionary.

    Examples:
        >>> import omnisus as odb
        >>> odb.reference_join_sql("sim_obitos", "causabas")
        'LEFT JOIN "lake"."aux_cid10" AS "ref_causabas" ON d."causabas" = "ref_causabas"."codigo"'
    """
    definition = load_dicionario(dataset).field_def(field) or {}
    keys = definition.get("foreignKeys", [])
    if len(keys) != 1:
        raise ValueError(f"{dataset}.{field} declares no reference (or more than one)")
    reference = keys[0]["reference"]
    ref = quote_identifier(f"ref_{field}")
    sql = (
        f"LEFT JOIN {qualified(lake_alias, reference['resource'])} AS {ref} "
        f"ON {alias}.{quote_identifier(field)} = {ref}.{quote_identifier(reference['fields'])}"
    )
    rule = keys[0].get("x-join-rule")
    if rule:
        sql += " AND (" + rule.replace("{d}", alias).replace("{r}", ref) + ")"
    return sql


def citation_from_publications(
    publications: Sequence[Mapping[str, Any]],
    *,
    snapshot_id: int,
    dataset: str | None = None,
    run_id: str | None = None,
    accessed: date | None = None,
) -> Citation:
    """Format publication rows you already have, e.g. kept in a JSON file.

    Args:
        publications: Rows of ``Lake.publications()``, or IBGE manifest rows.
        snapshot_id: The lake snapshot the analysis read.
        dataset: Dataset name, used when a row lacks it; ``"ibge_populacao"`` selects
            the IBGE wording.
        run_id: The run to name; ``None`` uses each row's own ``run_id``.
        accessed: Access date to print; ``None`` (default) is today.

    Returns:
        A :class:`~omnisus.Citation` whose ``text`` is the Portuguese paragraph.

    Examples:
        >>> from datetime import date
        >>> import omnisus as odb
        >>> row = {
        ...     "dataset": "sim_obitos",
        ...     "source_uri": "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc",
        ...     "source_sha256": "15b5203507161b7c35f9c69a52c955bdac133629549099b85a88e03a9a45baf0",
        ...     "run_id": "cap2",
        ... }
        >>> print(odb.citation_from_publications([row], snapshot_id=7, accessed=date(2026, 9, 23)).text)
        SIM — Declarações de Óbito (sim_obitos), arquivo DORR2023.dbc (...), SHA-256 15b5...baf0, acessado em 2026-09-23 pelo DATASUS. Importado com omnisus ..., lake snapshot 7, execução cap2.
    """
    accessed_on = accessed or datetime.now(UTC).date()
    rows = [dict(row) for row in publications]
    if dataset:
        for row in rows:
            row.setdefault("dataset", dataset)
    if dataset == "ibge_populacao" or (rows and "url" in rows[0] and "source_uri" not in rows[0]):
        paragraphs = [_ibge_paragraph(row, snapshot_id, accessed_on) for row in rows]
    else:
        paragraphs = [_ftp_paragraph(row, snapshot_id, accessed_on, run_id) for row in rows]
    if not paragraphs:
        paragraphs = [
            (
                f"Nenhuma publicação ativa encontrada"
                f"{f' para {dataset}' if dataset else ''}. "
                f"Importado com omnisus {__version__}, lake snapshot {snapshot_id}"
                f"{f', execução {run_id}' if run_id else ''}."
            )
        ]
    return Citation(
        text="\n\n".join(paragraphs),
        snapshot_id=snapshot_id,
        omnisus=__version__,
        dataset=dataset,
        run_id=run_id,
        publications=tuple(rows),
    )


def cite(
    lake: Lake | LakeReader,
    *,
    dataset: str | None = None,
    snapshot_id: int | None = None,
    run_id: str | None = None,
    accessed: date | None = None,
) -> Citation:
    """The Portuguese citation of what a lake holds: files, hashes, snapshot and run.

    Args:
        lake: An open :class:`~omnisus.Lake` or :class:`~omnisus.LakeReader`.
        dataset: Cite only this dataset, e.g. ``"sim_obitos"``; ``None`` (default)
            cites every active publication.
        snapshot_id: The snapshot your analysis read; ``None`` (default) is the
            newest.
        run_id: Cite only this run's publications.
        accessed: Access date to print; ``None`` (default) is today.

    Returns:
        A :class:`~omnisus.Citation`; paste ``citation.text`` into the methods.

    Raises:
        LookupError: ``snapshot_id`` is ``None`` and the lake has no snapshots.

    Examples:
        >>> import omnisus as odb
        >>> with odb.LakeReader() as lake:  # doctest: +SKIP
        ...     print(odb.cite(lake, dataset="sim_obitos").text)
    """
    pinned = latest_snapshot_id(lake) if snapshot_id is None else snapshot_id
    if dataset == "ibge_populacao":
        rows = _ibge_manifest(lake)
    else:
        rows = [
            row
            for row in lake.publications(run_id=run_id)
            if row.get("active", True) and (dataset is None or row.get("dataset") == dataset)
        ]
    return citation_from_publications(
        rows,
        snapshot_id=pinned,
        dataset=dataset,
        run_id=run_id,
        accessed=accessed,
    )


def _require_join_digits(digits: int) -> None:
    if digits not in (6, 7):
        raise ValueError("digits must be 6 or 7")


def _filename(uri: str | None) -> str:
    if not uri:
        return "(arquivo desconhecido)"
    path = urlparse(uri).path or uri
    name = path.rsplit("/", 1)[-1]
    return name or uri


def _title(dataset: str) -> str:
    try:
        return load_dicionario(dataset).title
    except Exception:
        return dataset


def _ftp_paragraph(
    row: Mapping[str, Any], snapshot_id: int, accessed_on: date, run_id: str | None
) -> str:
    dataset = str(row.get("dataset") or "(dataset desconhecido)")
    execucao = run_id or row.get("run_id") or "(run_id desconhecido)"
    titulo = _title(dataset) if row.get("dataset") else dataset
    files = row.get("sources") or []
    if len(files) > 1:
        arquivos = "; ".join(
            f"{_filename(f['source_uri'])} ({f['source_uri']}), SHA-256 {f['source_sha256']}"
            for f in files
        )
        origem = f"arquivos {arquivos}, acessados"
    else:
        uri = row.get("source_uri")
        sha = row.get("source_sha256") or "(SHA-256 desconhecido)"
        origem = f"arquivo {_filename(uri)} ({uri}), SHA-256 {sha}, acessado"
    return (
        f"{titulo} ({dataset}), {origem} em {accessed_on.isoformat()} pelo DATASUS. "
        f"Importado com omnisus {__version__}, lake snapshot {snapshot_id}, "
        f"execução {execucao}."
    )


def _ibge_paragraph(row: Mapping[str, Any], snapshot_id: int, accessed_on: date) -> str:
    url = row.get("url") or "(URL desconhecida)"
    sha = row.get("sha256") or "(SHA-256 desconhecido)"
    execucao = row.get("publication_id") or "(publication_id desconhecido)"
    return (
        f"IBGE · população (ibge_populacao), URL {url}, SHA-256 {sha}, "
        f"acessado em {accessed_on.isoformat()}. Importado com omnisus {__version__}, "
        f"lake snapshot {snapshot_id}, execução {execucao}."
    )


def _ibge_manifest(lake: Lake | LakeReader) -> list[dict[str, Any]]:
    tables = lake.tables()
    if "ibge_population_manifest" not in tables:
        return []
    rows = (
        lake.connect()
        .execute(
            f"SELECT publication_id, product, ano, sha256, url, collected_at "
            f"FROM {qualified(lake.alias, 'ibge_population_manifest')}"
        )
        .to_arrow_table()
        .to_pylist()
    )
    return list(rows)
