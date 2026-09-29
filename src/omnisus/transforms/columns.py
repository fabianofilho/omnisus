"""One row per column: what the dictionary says about it and what the rows show."""

from __future__ import annotations

from typing import Any

import polars as pl

from omnisus.transforms.dictionaries import DATE_FORMATS, _lookup_decode, load_dicionario

_SCHEMA: dict[str, pl.DataType] = {
    "column": pl.String(),
    "label": pl.String(),
    "rule": pl.String(),
    "pct_empty": pl.Float64(),
    "distinct": pl.Int64(),
    "example_code": pl.String(),
    "example_label": pl.String(),
    "unlabelled_codes": pl.List(pl.String()),
    "unlabelled_rows": pl.Int64(),
    "pct_invalid_dates": pl.Float64(),
    "date_min": pl.Date(),
    "date_max": pl.Date(),
}


def _rule(field: dict[str, Any] | None) -> str | None:
    if field is None:
        return "not in dictionary"
    if field.get("x-decode"):
        return f"code map ({len(field['x-decode'])} codes)"
    if field.get("type") == "date" and field.get("x-format") in DATE_FORMATS:
        return f"date {field['x-format']}"
    return None


def _percent(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def check_columns(dataset: str, df: pl.DataFrame) -> pl.DataFrame:
    """Report, per column, the dictionary's description and what the rows show.

    Answers "can I trust this column?" before an analysis: how much is empty,
    which published codes have no label, and whether dates parse and fall in a
    plausible range (impossible dates such as ``1899-12-30`` parse, so look at
    ``date_min``). A value counts as empty when it is null or an empty string.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``; see ``sus.datasets()``.
        df: Rows of that dataset, e.g. from :func:`omnisus.load`.

    Returns:
        One row per column of ``df``, in order, with columns:
        ``column``; ``label`` (the dictionary's, ``None`` when undeclared);
        ``rule`` (``"code map (n codes)"``, ``"date ddMMyyyy"``, ``"not in
        dictionary"`` or ``None``); ``pct_empty``; ``distinct`` (filled values);
        ``example_code`` and ``example_label`` (the first filled value and its
        label); ``unlabelled_codes`` (list of filled codes the code map does not
        label) and ``unlabelled_rows``; ``pct_invalid_dates``, ``date_min`` and
        ``date_max`` (``Date``) for date fields, ``None`` otherwise.

    Raises:
        FileNotFoundError: ``dataset`` has no packaged dictionary.

    Examples:
        SIH publishes ``homonimo`` ``2``, which no DATASUS table labels:

        >>> import polars as pl
        >>> import omnisus as sus
        >>> dados = pl.DataFrame({"homonimo": ["0", "2", ""], "nasc": ["19850320", "18991230", ""]})
        >>> relatorio = sus.check_columns("sih_aih_reduzida", dados)
        >>> relatorio.select("column", "pct_empty", "unlabelled_codes", "date_min").rows()
        [('homonimo', 33.3, ['2'], None), ('nasc', 33.3, [], datetime.date(1899, 12, 30))]
    """
    dicionario = load_dicionario(dataset)
    rows = []
    for column in df.columns:
        field = dicionario.field_def(column)
        text = df[column].cast(pl.String)
        filled = text.filter(text.is_not_null() & (text != ""))
        example = filled[0] if filled.len() else None
        decode_map = (field or {}).get("x-decode")
        unlabelled: list[str] = []
        unlabelled_rows = 0
        if decode_map:
            for code, count in filled.value_counts(sort=True).rows():
                if _lookup_decode(decode_map, code) is None:
                    unlabelled.append(code)
                    unlabelled_rows += count
        invalid = date_min = date_max = None
        pattern = DATE_FORMATS.get(field.get("x-format", "")) if field else None
        if field and field.get("type") == "date" and pattern:
            dates = filled.str.strptime(pl.Date, pattern, strict=False)
            invalid = _percent(dates.null_count(), filled.len())
            date_min, date_max = dates.min(), dates.max()
        rows.append(
            {
                "column": column,
                "label": field.get("label") if field else None,
                "rule": _rule(field),
                "pct_empty": _percent(df.height - filled.len(), df.height),
                "distinct": filled.n_unique(),
                "example_code": example,
                "example_label": _lookup_decode(decode_map, example) if decode_map else None,
                "unlabelled_codes": unlabelled,
                "unlabelled_rows": unlabelled_rows,
                "pct_invalid_dates": invalid,
                "date_min": date_min,
                "date_max": date_max,
            }
        )
    return pl.DataFrame(rows, schema=_SCHEMA)
