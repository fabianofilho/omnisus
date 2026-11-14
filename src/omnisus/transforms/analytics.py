"""Finite native SQL projections over an explicitly identified source snapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from omnisus.lake.publication import scope_from_fields
from omnisus.lake.sql import quote_identifier, quote_literal
from omnisus.metadata import describe_dataset
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.datasets import release_from_uri
from omnisus.transforms.age import age_expressions
from omnisus.transforms.dictionaries import DATE_FORMATS


@dataclass(frozen=True)
class SourceContext:
    """Source identity, read from the same snapshot as the queried records."""

    scope: ScopeKey
    release: str | None = None
    source_sha256: str | None = None

    @classmethod
    def from_publication(cls, row: Mapping[str, Any]) -> SourceContext:
        """The source identity recorded by one ``Lake.publications()`` row.

        Args:
            row: A publication row with ``dataset``, ``scope_json``, ``source_uri``
                and ``source_sha256``.

        Returns:
            Scope, release (from the file's directory) and aggregate SHA-256.

        Raises:
            ValueError: the row lacks one of those keys or has no supported scope.

        Examples:
            >>> import omnisus as sus
            >>> sus.SourceContext.from_publication({
            ...     "dataset": "sim_obitos",
            ...     "scope_json": '{"ano": 2023, "uf": "RR"}',
            ...     "source_uri": "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc",
            ...     "source_sha256": "15b5203507161b7c35f9c69a52c955bdac133629549099b85a88e03a9a45baf0",
            ... }).release
            'final'
        """
        try:
            fields = json.loads(row["scope_json"])
            if not isinstance(fields, dict):
                raise ValueError("Publication scope must be an object")
            scope = scope_from_fields(fields)
            if scope is None:
                raise ValueError("Publication has no supported scope")
            return cls(
                scope,
                release_from_uri(row["dataset"], row.get("source_uri")),
                row.get("source_sha256"),
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Incomplete publication identity") from exc


@dataclass(frozen=True)
class DerivedColumn:
    name: str
    sql_type: str
    expression: str


@dataclass(frozen=True)
class UnavailableField:
    field: str
    reason: str


@dataclass(frozen=True)
class AnalyticalProjection:
    columns: tuple[DerivedColumn, ...]
    unavailable: tuple[UnavailableField, ...]
    rule_version: str | None
    metadata_hash: str


_AGE_OUTPUTS = ("idade_anos_completos", "idade_status", "idade_quantidade", "idade_unidade")
_SEX_OUTPUTS = ("sexo_categoria", "sexo_status")


def _date_outputs(name: str) -> tuple[str, str]:
    return f"{name}_data", f"{name}_data_status"


def _age_inputs(age: Mapping[str, Any]) -> list[str]:
    return [age["field"]] + ([age["unit_field"]] if age.get("unit_field") else [])


def harmonised_inputs(rules: Mapping[str, Any] | None) -> dict[str, tuple[str, ...]]:
    """``{harmonised column: the published fields it is derived from}`` under ``rules``.

    ``rules`` is a dictionary's ``x-analytics``. These are every column
    :func:`analytical_projection` can add, whether or not a given source is validated.
    """
    rules = rules or {}
    columns: dict[str, tuple[str, ...]] = {}
    if rules.get("age"):
        columns |= dict.fromkeys(_AGE_OUTPUTS, tuple(_age_inputs(rules["age"])))
    if rules.get("sex"):
        columns |= dict.fromkeys(_SEX_OUTPUTS, (rules["sex"]["field"],))
    for name in rules.get("dates", []):
        columns |= dict.fromkeys(_date_outputs(name), (name,))
    return columns


def _confirmed(contexts: Sequence[SourceContext], validated: Sequence[dict[str, Any]]) -> bool:
    return bool(contexts) and all(
        any(
            context.scope == ScopeKey(uf=source["uf"], ano=source["ano"], mes=source.get("mes"))
            and context.release == source["release"]
            and context.source_sha256 == source["source_sha256"]
            for source in validated
        )
        for context in contexts
    )


def _sex_expressions(rule: Mapping[str, Any], expression: str) -> tuple[str, str]:
    raw = f"trim(CAST({expression} AS VARCHAR))"
    cases = []
    statuses = [f"WHEN {raw} IS NULL OR {raw} = '' THEN 'missing'"]
    for code, category in rule["categories"].items():
        predicate = f"{raw} = {quote_literal(code)}"
        if category is not None:
            cases.append(f"WHEN {predicate} THEN {quote_literal(category)}")
        statuses.append(
            f"WHEN {predicate} THEN '{'valid' if category is not None else 'ignored'}'"
        )
    value = "CASE " + " ".join(cases) + " ELSE NULL END"
    status = "CASE " + " ".join(statuses) + " ELSE 'unsupported' END"
    return value, status


def _date_expressions(expression: str, physical_type: str, format_: str) -> tuple[str, str]:
    if physical_type.upper() == "DATE":
        return expression, f"CASE WHEN {expression} IS NULL THEN 'missing' ELSE 'valid' END"
    raw = f"trim(CAST({expression} AS VARCHAR))"
    parsed = f"TRY_STRPTIME({raw}, {quote_literal(DATE_FORMATS[format_])})::DATE"
    guard = f"regexp_full_match({raw}, '[0-9]{{8}}')"
    value = f"CASE WHEN {guard} THEN {parsed} ELSE NULL END"
    status = (
        f"CASE WHEN {raw} IS NULL OR {raw} = '' THEN 'missing' "
        f"WHEN ({value}) IS NULL THEN 'invalid' ELSE 'valid' END"
    )
    return value, status


def analytical_projection(
    dataset: str,
    *,
    observed_schema: Mapping[str, str],
    scopes: Sequence[SourceContext],
    rule_version: str | None = None,
) -> AnalyticalProjection:
    """SQL for the harmonised categories of a dataset, enabled only for validated sources.

    Opens no lake and changes no stored record: it returns expressions to put in a
    ``SELECT``. :func:`~omnisus.load` already does this for you. Each category is
    enabled only when every source in ``scopes`` is listed, by scope, release and
    SHA-256, in the rule's ``validated_sources`` (ADR 0003); otherwise it is
    reported in ``unavailable`` with the reason. Take the schema and the sources from
    the same snapshot as the rows you select.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``.
        observed_schema: ``{column: DuckDB type}`` of the relation you will select
            from, e.g. from ``DESCRIBE``. Names match case-insensitively.
        scopes: The :class:`SourceContext` of every source in that relation, e.g.
            ``SourceContext.from_publication(row)`` for each active publication.
        rule_version: Require this rules edition, e.g. ``"1.1.0"``; ``None``
            (default) takes the packaged one.

    Returns:
        ``columns`` (name, DuckDB type, expression), ``unavailable`` (field, reason:
        ``missing_source_field``, ``unconfirmed_source_scope``,
        ``unsupported_dataset``, ...), the rule version and the metadata hash.

    Raises:
        ValueError: ``rule_version`` is not the packaged one, two observed columns
            differ only by case, or a derived name collides with a source column.

    Examples:
        >>> import omnisus as sus
        >>> dorr2023 = sus.SourceContext(
        ...     sus.ScopeKey("RR", 2023),
        ...     "final",
        ...     "15b5203507161b7c35f9c69a52c955bdac133629549099b85a88e03a9a45baf0",
        ... )
        >>> projection = sus.analytical_projection(
        ...     "sim_obitos", observed_schema={"sexo": "VARCHAR"}, scopes=[dorr2023]
        ... )
        >>> [column.name for column in projection.columns]
        ['sexo_categoria', 'sexo_status']
    """
    metadata = describe_dataset(dataset)
    rules = metadata["analytics"]
    version = rules["version"] if rules else None
    if rule_version is not None and rule_version != version:
        raise ValueError(f"Unavailable analytical rule version: {rule_version}")
    columns: list[DerivedColumn] = []
    unavailable: list[UnavailableField] = []
    names = {name.lower(): name for name in observed_schema}
    if len(names) != len(observed_schema):
        raise ValueError("Ambiguous case-insensitive source columns")
    definitions = {field["name"]: field for field in metadata["schema"]["fields"]}

    def available(output: str, inputs: Sequence[str], rule: Mapping[str, Any]) -> bool:
        if any(name not in names for name in inputs):
            unavailable.append(UnavailableField(output, "missing_source_field"))
            return False
        if not _confirmed(
            scopes, rule.get("validated_sources", rules.get("validated_sources", []))
        ):
            unavailable.append(UnavailableField(output, "unconfirmed_source_scope"))
            return False
        return True

    def add(name: str, dtype: str, expression: str) -> None:
        if name.lower() in names or any(column.name == name for column in columns):
            raise ValueError(f"Analytical column collision: {name}")
        columns.append(DerivedColumn(name, dtype, expression))

    if not rules:
        return AnalyticalProjection(
            (),
            (
                UnavailableField(_AGE_OUTPUTS[0], "unsupported_dataset"),
                UnavailableField(_SEX_OUTPUTS[0], "unsupported_dataset"),
            ),
            None,
            metadata["metadata_hash"],
        )
    age = rules.get("age")
    if age is not None:
        inputs = _age_inputs(age)
        years, age_status, quantity, unit = _AGE_OUTPUTS
        if available(years, inputs, age):
            sql = age_expressions(
                age,
                quote_identifier(names[inputs[0]]),
                quote_identifier(names[inputs[1]]) if len(inputs) > 1 else None,
            )
            add(years, "INTEGER", sql.years)
            add(age_status, "VARCHAR", sql.status)
            add(quantity, "INTEGER", sql.quantity)
            add(unit, "VARCHAR", sql.unit)
    else:
        unavailable.append(UnavailableField(_AGE_OUTPUTS[0], "unsupported_field"))
    sex = rules.get("sex")
    category, sex_status = _SEX_OUTPUTS
    if sex is not None and available(category, [sex["field"]], sex):
        value, status = _sex_expressions(sex, quote_identifier(names[sex["field"]]))
        add(category, "VARCHAR", value)
        add(sex_status, "VARCHAR", status)
    for name in rules.get("dates", []):
        output, output_status = _date_outputs(name)
        if not available(output, [name], rules):
            continue
        definition = definitions[name]
        format_ = definition.get("x-format")
        if format_ not in DATE_FORMATS:
            unavailable.append(UnavailableField(output, "unsupported_date_format"))
            continue
        source_name = names[name]
        value, status = _date_expressions(
            quote_identifier(source_name), observed_schema[source_name], format_
        )
        add(output, "DATE", value)
        add(output_status, "VARCHAR", status)
    return AnalyticalProjection(
        tuple(columns), tuple(unavailable), version, metadata["metadata_hash"]
    )
