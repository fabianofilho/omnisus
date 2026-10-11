"""Every importer family except SIGTAP, stated once: the FTP registry, IBGE and CNES master.

Facts, not forms. Year rules for IBGE are ``omnisus.CENSUS_YEARS`` and
``omnisus.ESTIMATE_UNAVAILABLE_YEARS``; an estimate is importable
only as its latest edition, checked live at import, so there is no floor year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl

from omnisus.lake.publication import POLICIES
from omnisus.metadata import category, describe_dataset
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import REGISTRY, YM, Dataset

ReconcileBy = Literal["run_id", "publication_id", "rerun"]


@dataclass(frozen=True)
class Product:
    """One importer family and what it supports."""

    name: str
    """Registry key or importer name: ``sim_obitos``, ``ibge_populacao``, ``cnes_master``.

    It is also the relation the importer writes in the lake: query
    ``FROM lake.<name>``. Whether that relation is a table or a view
    (``ibge_populacao`` is a view) is the catalog's to say, in
    ``information_schema.tables.table_type``."""

    dataset: Dataset | None
    """The FTP registry row, or ``None`` for IBGE and CNES master."""

    scope_fields: tuple[str, ...]
    """What identifies one import unit: ``("uf", "ano"[, "mes"])``, ``("ano",)``
    for national datasets, ``("product", "ano")`` for IBGE, empty for CNES master."""

    policies: tuple[str, ...]
    """Accepted ``ImportPolicy`` values; families outside the manifest append only."""

    reconcile_by: ReconcileBy
    """How an interrupted run is reconciled: ``Lake.publications(run_id=)``, the
    returned ``publication_id`` in ``ibge_population_manifest``, or a rerun
    (CNES master is an idempotent upsert)."""

    inventory: bool
    """Whether :func:`omnisus.available` can list the source's scopes."""


def datasets() -> tuple[Dataset, ...]:
    """Every DATASUS FTP dataset the package curates, in registry order.

    Returns:
        :class:`~omnisus.Dataset` values; ``.name`` is what :func:`~omnisus.load`
        and the other functions accept. :func:`~omnisus.describe_datasets` gives the
        same datasets as a table, with titles and coverage.

    Examples:
        >>> import omnisus as sus
        >>> "sim_obitos" in [d.name for d in sus.datasets()]
        True
    """
    return tuple(REGISTRY.values())


_TABLE = pl.Schema(
    {
        "name": pl.String(),
        "category": pl.String(),
        "title": pl.String(),
        "geography": pl.String(),
        "cadence": pl.String(),
        "coverage_start": pl.String(),
        "coverage_end": pl.String(),
        "prefix": pl.String(),
        "ftp_dir": pl.String(),
        "prelim_dir": pl.String(),
        "fields": pl.Int64(),
        "labelled_fields": pl.Int64(),
        "validated_scopes": pl.List(pl.String()),
    }
)


def _period(ym: YM, d: Dataset) -> str:
    return f"{ym[0]}-{ym[1]:02d}" if d.monthly else str(ym[0])


def describe_datasets() -> pl.DataFrame:
    """Every DATASUS FTP dataset the package curates, as one table.

    What each dataset is, how it is published and since when. DATASUS publishes other
    datasets that the package does not import. Works offline: it reads only the
    registry and :func:`~omnisus.describe_dataset`. Coverage is the window the registry
    declares, not what the server lists today; ask :func:`~omnisus.available` for that.

    Returns:
        One row per :func:`~omnisus.datasets` entry, sorted by ``name``, with columns
        ``name``, ``category`` (the system: ``SIM``, ``SIA``...; the same value as
        ``describe_dataset(name)["fields"][i]["dataset"]["category"]``), ``title``,
        ``geography`` (``state`` or ``national``), ``cadence`` (``yearly`` or
        ``monthly``), ``coverage_start`` and ``coverage_end`` (``"1996"`` for yearly
        datasets, ``"2014-08"`` for monthly ones; ``coverage_end`` is ``None`` when
        no end is declared), ``prefix``, ``ftp_dir``, ``prelim_dir`` (``None`` when
        DATASUS publishes no preliminary files), ``fields`` (columns in the
        dictionary), ``labelled_fields`` (those :func:`~omnisus.label` can label)
        and ``validated_scopes``: the scopes, such as ``RR_2023``, whose audited file
        (release and SHA-256) is listed in
        ``describe_dataset(name)["analytics"]["validated_sources"]`` (empty for most
        datasets). :func:`~omnisus.load` adds the harmonised categories the
        dictionary defines only when every scope it returns is that same file
        (ADR 0003). Coverage columns are strings, not dates; ``fields`` and
        ``labelled_fields`` are ``Int64``; ``validated_scopes`` is
        ``List(String)``; only ``coverage_end`` and ``prelim_dir`` are nullable.

    Examples:
        >>> import omnisus as sus
        >>> bases = sus.describe_datasets()
        >>> atd = bases.filter(name="sia_apac_tratamento_dialitico")
        >>> atd.select("category", "coverage_start", "coverage_end").row(0)
        ('SIA', '2014-08', None)
    """
    rows = []
    for d in sorted(datasets(), key=lambda d: d.name):
        metadata = describe_dataset(d.name)
        fields = metadata["schema"]["fields"]
        first, last = d.coverage
        validated = (metadata["analytics"] or {}).get("validated_sources", [])
        rows.append(
            {
                "name": d.name,
                "category": category(d.name),
                "title": metadata["title"],
                "geography": d.geography,
                "cadence": d.cadence,
                "coverage_start": _period(first, d),
                "coverage_end": None if last is None else _period(last, d),
                "prefix": d.prefix,
                "ftp_dir": d.ftp_dir,
                "prelim_dir": d.prelim_dir,
                "fields": len(fields),
                "labelled_fields": sum(1 for f in fields if f.get("x-decode")),
                "validated_scopes": [
                    str(ScopeKey(s.get("uf"), s["ano"], s.get("mes"))) for s in validated
                ],
            }
        )
    return pl.DataFrame(rows, schema=_TABLE)


def products() -> tuple[Product, ...]:
    """Every importer family except SIGTAP: the FTP datasets, IBGE population, CNES master.

    Returns:
        One :class:`~omnisus.Product` per family, with its scope fields, accepted
        policies and how an interrupted run is reconciled.

    Examples:
        >>> import omnisus as sus
        >>> [(p.name, p.reconcile_by) for p in sus.products()[-2:]]
        [('ibge_populacao', 'publication_id'), ('cnes_master', 'rerun')]
    """
    ftp = tuple(
        Product(
            d.name,
            d,
            ("ano",)
            if d.geography == "national"
            else ("uf", "ano", "mes")
            if d.monthly
            else ("uf", "ano"),
            POLICIES,
            "run_id",
            True,
        )
        for d in datasets()
    )
    return (
        *ftp,
        Product("ibge_populacao", None, ("product", "ano"), ("append",), "publication_id", False),
        Product("cnes_master", None, (), ("append",), "rerun", False),
    )
