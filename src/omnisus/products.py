"""Every importer family except SIGTAP, stated once: the FTP registry, IBGE and CNES master.

Facts, not forms. Year rules for IBGE stay in ``sources.ibge.products``
(``CENSUS_YEARS``, ``ESTIMATE_UNAVAILABLE_YEARS``); an estimate is importable
only as its latest edition, checked live at import, so there is no floor year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from omnisus.lake.publication import POLICIES
from omnisus.sources.datasus_ftp.datasets import REGISTRY, Dataset

ReconcileBy = Literal["run_id", "publication_id", "rerun"]


@dataclass(frozen=True)
class Product:
    """One importer family and what it supports."""

    name: str
    """Registry key or importer name: ``sim_obitos``, ``ibge_populacao``, ``cnes_master``."""

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
        and the other functions accept.

    Examples:
        >>> import omnisus as sus
        >>> "sim_obitos" in [d.name for d in sus.datasets()]
        True
    """
    return tuple(REGISTRY.values())


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
