"""The columns the import adds to every DATASUS file, and their types.

``ano``, ``uf``, ``mes``, ``_source_ano`` and ``_source_release`` are not fields of
the DBF: staging writes them from the file's name and directory. This is the one place
that says which of them a dataset gets and what type the lake stores. The runner reads
the names, staging the arrow types, and ``scripts/metadados/gerar_colunas_lib.py``
writes each column into the dataset's dictionary with a ``derivation``;
``is_library_field`` tells those from the fields the DBF publishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa

from omnisus.sources.datasus_ftp.datasets import Dataset

ARROW_TYPES: dict[str, pa.DataType] = {
    "ano": pa.uint16(),
    "uf": pa.string(),
    "mes": pa.uint8(),
    "_source_ano": pa.uint16(),
    "_source_release": pa.string(),
}
"""Type the lake stores for each library column, whatever the dataset."""

_SCOPE = {"kind": "source_partition", "input": "source_uri", "rule": "DATASUS filename scope"}
_RELEASE = {"kind": "publication", "input": "source_uri", "rule": "release_from_uri"}


def is_library_field(field: dict[str, Any]) -> bool:
    """Whether a dictionary field is a column the import writes, whatever the DBF holds.

    Such a field is declared with a ``derivation`` of kind ``source_partition`` or
    ``publication``. The ER's ``ano`` and ``mes`` are one: the DBF publishes them as text
    and staging replaces them with the scope. Other kinds (``coded_age``...) derive a
    harmonised column from a published one and leave the published field physical.
    """
    derivation = field.get("x-metadata", {}).get("derivation") or {}
    return derivation.get("kind") in {_SCOPE["kind"], _RELEASE["kind"]}


@dataclass(frozen=True)
class LibraryColumn:
    """One column of a dataset the import adds, as its dictionary declares it."""

    name: str
    type: str
    """Logical type of the dictionary field (``integer`` or ``string``)."""
    label: str
    derivation: dict[str, str]
    constraints: dict[str, Any] = field(default_factory=dict)

    @property
    def arrow(self) -> pa.DataType:
        return ARROW_TYPES[self.name]


def library_columns(d: Dataset) -> tuple[LibraryColumn, ...]:
    """The columns the import adds to ``d``, in the order staging appends them.

    ``ano`` and ``uf`` are the scope of a state file, ``mes`` of a monthly one; a
    national file has no UF and carries the file's year in ``_source_ano``;
    ``_source_release`` says which directory the file came from.
    """
    first_year = d.coverage[0][0]
    columns: list[LibraryColumn] = []
    if d.geography == "state":
        columns.append(
            LibraryColumn(
                "ano", "integer", "Ano", _SCOPE, {"required": True, "minimum": first_year}
            )
        )
        columns.append(
            LibraryColumn(
                "uf", "string", "UF", _SCOPE, {"required": True, "pattern": "^[A-Z]{2}$"}
            )
        )
    if d.monthly:
        columns.append(
            LibraryColumn(
                "mes", "integer", "Mês", _SCOPE, {"required": True, "minimum": 1, "maximum": 12}
            )
        )
    if d.geography == "national":
        columns.append(
            LibraryColumn(
                "_source_ano",
                "integer",
                "Ano do arquivo de origem",
                _SCOPE,
                {"required": True, "minimum": first_year},
            )
        )
    columns.append(
        LibraryColumn(
            "_source_release", "string", "Modalidade da fonte", _RELEASE, {"required": True}
        )
    )
    return tuple(columns)
