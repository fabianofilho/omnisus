"""Frictionless Table Schema YAML loader and the one code-to-label lookup.

The dictionary describes logical fields. Ingestion uses the DBF physical schema
and dictionary encoding; declared logical types and normalization hints do not
cast or transform stored columns.

A **label** is the text a field's ``x-decode`` map gives to a code. The lookup is
type- and whitespace-tolerant: the key as written, the code stripped of the
spaces DBF files pad it with, or the code as an integer. A code that matches no
key has no label (``None``); it is never guessed. :func:`label` (DataFrames) and
:func:`display_row` (one row) both use it. Dates, ages and sexes become
comparable values only through the audited rules of
:func:`~omnisus.transforms.analytics.analytical_projection`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import yaml

from omnisus.lake.sql import quote_identifier

if TYPE_CHECKING:
    import duckdb

DATE_FORMATS: dict[str, str] = {"ddMMyyyy": "%d%m%Y", "yyyyMMdd": "%Y%m%d"}
"""``x-format`` of a date field → ``strptime`` pattern (DuckDB and polars share it)."""


def _lookup_decode(decode_map: Mapping[Any, Any], value: Any) -> str | None:
    """The label ``decode_map`` gives to ``value``, or ``None`` when no key matches.

    The lake stores VARCHAR but YAMLs may declare ``type: integer`` and use int
    keys, and DBF/DBC sources pad codes with spaces, so the code is tried as
    written, stripped, and as an integer.
    """
    if value is None:
        return None
    if value in decode_map:
        return str(decode_map[value])
    text = str(value).strip()
    if text in decode_map:
        return str(decode_map[text])
    if text.isdigit() and int(text) in decode_map:
        return str(decode_map[int(text)])
    return None


# ---------------------------------------------------------------------------
# Dicionario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dicionario:
    """Loaded Frictionless schema with omnisus extensions."""

    name: str
    title: str
    encoding: str
    fields: list[dict[str, Any]]
    primary_key: list[str]
    partitions: list[str]
    source_format: str
    version: str
    raw: dict[str, Any]

    def field_def(self, name: str) -> dict[str, Any] | None:
        """Return the field definition for ``name`` (case-insensitive)."""
        lname = name.lower() if isinstance(name, str) else name
        for f in self.fields:
            if f["name"] == lname:
                return f
        return None

    def decode(self, field: str, value: Any) -> str | None:
        """The label of ``value`` in ``field``'s code map; ``None`` when there is none."""
        f = self.field_def(field)
        if f is None or not f.get("x-decode"):
            return None
        return _lookup_decode(f["x-decode"], value)

    def decode_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """``row`` with each coded field's code replaced by its label (``None`` if unknown).

        Fields without a code map, and keys the dictionary does not declare, pass
        through as published. Row keys match case-insensitively (``SEXO``, ``sexo``).
        """
        result = dict(row)
        for key, value in row.items():
            f = self.field_def(key)
            if f is not None and f.get("x-decode"):
                result[key] = _lookup_decode(f["x-decode"], value)
        return result


@cache
def load_dicionario(name_or_path: str | Path) -> Dicionario:
    """Load and cache a Dicionario.

    ``str`` is a dataset name resolved to the packaged
    ``dicionarios/<name>.yaml``. ``Path`` is an explicit YAML file — how an
    ad-hoc dataset supplies its own schema.
    """
    if isinstance(name_or_path, Path):
        if not name_or_path.is_file():
            raise FileNotFoundError(f"dicionario not found: {name_or_path}")
        text = name_or_path.read_text(encoding="utf-8")
    else:
        yaml_path = files("omnisus.data.dicionarios") / f"{name_or_path}.yaml"
        if not yaml_path.is_file():
            raise FileNotFoundError(f"dicionario not found: {name_or_path}")
        text = yaml_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    schema = raw.get("schema", {})
    return Dicionario(
        name=raw["name"],
        title=raw.get("title", raw["name"]),
        encoding=raw.get("encoding", "utf-8"),
        fields=schema.get("fields", []),
        primary_key=schema.get("primaryKey", []),
        partitions=raw.get("x-partitions", []),
        source_format=raw.get("x-source-format", ""),
        version=raw.get("x-version", "0.0.0"),
        raw=raw,
    )


def display_row(dataset: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Replace each code in one row by its dictionary label, without mutating the input.

    The per-row door to the same lookup as :func:`label`: a coded field gets its
    label, or ``None`` when the dictionary does not know the code; every other
    field is returned as published.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``; see ``sus.datasets()``.
        row: One record as ``{column: value}``. Keys match case-insensitively.

    Returns:
        A new dict with the same keys.

    Raises:
        FileNotFoundError: ``dataset`` has no packaged dictionary.

    Examples:
        >>> import omnisus as sus
        >>> sus.display_row("sim_obitos", {"sexo": "2", "dtobito": "01012023"})
        {'sexo': 'Feminino', 'dtobito': '01012023'}
    """
    return load_dicionario(dataset).decode_row(dict(row))


def label(dataset: str, df: pl.DataFrame, *, columns: Sequence[str] | None = None) -> pl.DataFrame:
    """Add the dictionary's label next to each coded column, keeping the code.

    Each coded column ``c`` gains ``c_rotulo`` right after it. A code the
    dictionary does not know gets a null label, and so do a null and a blank the
    map does not declare: nothing is guessed, and the code stays in ``c``.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``; see ``sus.datasets()``.
        df: Rows of that dataset, e.g. from :func:`omnisus.load`.
        columns: Columns to label, e.g. ``["sexo", "racacor"]``. ``None`` (the
            default) labels every column of ``df`` that has a code map.

    Returns:
        ``df`` with one ``<column>_rotulo`` (``String``) column after each labelled column.

    Raises:
        ValueError: a name in ``columns`` is not in ``df`` or has no code map.
        FileNotFoundError: ``dataset`` has no packaged dictionary.

    Examples:
        >>> import polars as pl
        >>> import omnisus as sus
        >>> dados = pl.DataFrame({"sexo": ["1", "2", " "], "idade": ["435", "450", "401"]})
        >>> sus.label("sim_obitos", dados)
        shape: (3, 3)
        ┌──────┬─────────────┬───────┐
        │ sexo ┆ sexo_rotulo ┆ idade │
        │ ---  ┆ ---         ┆ ---   │
        │ str  ┆ str         ┆ str   │
        ╞══════╪═════════════╪═══════╡
        │ 1    ┆ Masculino   ┆ 435   │
        │ 2    ┆ Feminino    ┆ 450   │
        │      ┆ null        ┆ 401   │
        └──────┴─────────────┴───────┘
    """
    dicionario = load_dicionario(dataset)
    maps = {
        column: definition["x-decode"]
        for column in df.columns
        if (definition := dicionario.field_def(column)) and definition.get("x-decode")
    }
    if columns is not None:
        missing = [column for column in columns if column not in maps]
        if missing:
            raise ValueError(
                f"{dataset}: no code map for {', '.join(missing)} in this DataFrame; "
                f"columns with one: {', '.join(maps) or 'none'}"
            )
        maps = {column: maps[column] for column in columns}
    selection: list[pl.Expr] = []
    for column in df.columns:
        selection.append(pl.col(column))
        if column in maps:
            codes = df[column].drop_nulls().unique().to_list()
            labels = {code: _lookup_decode(maps[column], code) for code in codes}
            selection.append(
                pl.col(column)
                .replace_strict(labels, default=None, return_dtype=pl.String)
                .alias(f"{column}_rotulo")
            )
    return df.select(selection)


@dataclass(frozen=True)
class Uncovered:
    """A value of ``field`` that no ``x-decode`` key matches, and how many rows hold it."""

    field: str
    value: str
    rows: int


def decode_coverage(dataset: str, relation: duckdb.DuckDBPyRelation) -> list[Uncovered]:
    """Values of ``relation`` that no ``x-decode`` key of ``dataset`` matches exactly.

    Each non-NULL value is compared as text (``CAST(... AS VARCHAR)``) with the keys as
    written. Unlike :func:`_lookup_decode` there is no trimming and no integer
    fallback, so every value listed here is a code the map does not publish.
    """
    uncovered = []
    for field in load_dicionario(dataset).fields:
        keys = {str(key) for key in field.get("x-decode") or {}}
        if not keys or field["name"] not in relation.columns:
            continue
        column = quote_identifier(field["name"])
        counts = relation.query(
            "coverage",
            f"SELECT CAST({column} AS VARCHAR), count(*) FROM coverage "
            f"WHERE {column} IS NOT NULL GROUP BY 1 ORDER BY 1",
        ).fetchall()
        uncovered += [Uncovered(field["name"], v, n) for v, n in counts if v not in keys]
    return uncovered
