"""TabWin DEF and CNV files, parsed as the TabWin manual describes them.

Source of the format: ``TabWin.pdf`` (DATASUS, 2011; registry ``tabwin-bb98cff14765``),
pp. 87-92 of the PDF, and ``ManualTabnet.pdf`` (DATASUS, 2008; registry
``tabnet-5a97b03fe23a``), p. 21, whose CNV chapter repeats the TabWin text and adds
which line wins.

* A DEF line binds a field to a conversion table: letter in column 1, then
  ``description, FIELD, start, TABLE.CNV`` separated by commas (p. 88). The
  manual also documents a second S/L/C form that relates a DBF field to another
  *DBF* file, identified "pela extensão do nome do arquivo" (p. 87); a line whose
  third part is not numeric but whose last part still names a *.CNV* (not a
  *.DBF*) fits neither documented form, so its start column is unknown (p. 88,
  RD2008.DEF ``FAEC_TP``/``PROC_REA``).
* A CNV starts with ``<categories> <characters> [flag]``; each later line has the
  category number in columns 4-7, the description in columns 10-59 and the
  comma-separated code list from column 61 on (p. 90). Short codes may be written
  as ``first-last`` ranges (p. 90). ``;`` starts a comment (p. 91).
* Column 60 may hold a 51st description character when codes follow from column
  61: ``CBO2002.CNV`` (SIM) does so on 246 of its 2,429 lines. A line whose column
  60 is filled and that holds nothing from column 61 (``DNNOVA.CNV`` writes its
  code there) is outside the layout.
* The header's second number is the code width; a longer code, or a range whose
  bounds are not digits (``A00-A09``), raises instead of becoming a literal key.
* A short code (width up to 4) listed on two lines takes the later line: in the
  manual's MESES.CNV, ``01`` is first "Ignorado" (``00-99``), then "Janeiro", which
  "prevalece, por aparecer por último" (ManualTabnet.pdf p. 21). A long code keeps
  its first reference (TabWin.pdf p. 91); no packaged CNV repeats one, so it raises.
* Tables whose header starts with ``N`` (e.g. ``N 41 2 L``) use a 100-column
  description: category in columns 1-9, description 12-111, codes from 113.
  The manual does not describe them; the layout is read from the packaged
  member that uses it (LEITOS.CNV).

Codes are kept exactly as written, spaces included. Structure that does not fit
the layout raises ``CnvFormatError`` instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from omnisus.sources.datasus_ftp.dbf_contract import _read_field_descriptors
from omnisus.sources.datasus_ftp.parse import _stream_records


class CnvFormatError(ValueError):
    """A DEF or CNV line does not follow the documented layout."""


@dataclass(frozen=True)
class DefBinding:
    kind: str  # the letter in column 1 (L, C, S, T, X, ...), as written
    label: str
    field: str
    start: int | None  # 1-based position in the DBF field; None if undocumented
    table: str  # as written, e.g. "CNV\\SAIDAPERM.CNV"


@dataclass(frozen=True)
class DefLookup:
    kind: str  # the letter in column 1, as written
    label: str
    field: str
    column: str  # the related DBF's column holding the description (p. 88, "Campo D")
    table: str  # the related *.DBF, as written


@dataclass(frozen=True)
class CnvLine:
    category: int
    label: str
    codes: tuple[str, ...]  # listed one by one, exactly as written
    ranged: tuple[str, ...]  # expanded from equal-width numeric "first-last"


_NOT_BINDINGS = frozenset("AIGR")  # file pattern, increment, grouped data, report
_HEADER = re.compile(r"(N\s+)?(\d+)\s+(\d+)(\s+\S+)?")
_RANGE = re.compile(r"(\d+)-(\d+)")
_OTHER_RANGE = re.compile(r"\s*\S+-\S+\s*")


def parse_def(text: str) -> list[DefBinding]:
    """Every ``letter + description, FIELD, start, *.CNV`` line, in file order.

    The third field is usually a numeric start column (p. 88). A handful of real
    lines (RD2008.DEF ``FAEC_TP``, ``PROC_REA``) put a field name there instead,
    a shape the manual does not document for a *.CNV* target; the binding is
    still returned, with ``start=None``, rather than dropped. A line that names a
    *.CNV* but does not fit either shape (wrong field count) raises instead of
    being silently skipped.
    """
    bindings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line[:1].isalpha() or line[0].upper() in _NOT_BINDINGS:
            continue
        parts = [part.strip() for part in line[1:].split(",")]
        names_cnv = bool(parts) and parts[-1].lower().endswith(".cnv")
        if not names_cnv:
            continue  # DBF lookups and other functions
        if len(parts) != 4:
            raise CnvFormatError(
                f"DEF line {lineno} names a CNV outside the known layouts: {line!r}"
            )
        label, field, third, table = parts
        start = int(third) if third.isdigit() else None
        bindings.append(DefBinding(line[0], label, field.upper(), start, table))
    return bindings


def parse_def_lookups(text: str) -> list[DefLookup]:
    """Every ``letter + description, FIELD, COLUMN, *.DBF`` line, in file order.

    The second documented S/L/C form (p. 88) relates a DBF field to another DBF:
    ``COLUMN`` holds the description, and TabWin recognises the DBF "pela extensão do
    nome do arquivo". A line that names a *.DBF* in another shape raises.
    """
    lookups = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line[:1].isalpha() or line[0].upper() in _NOT_BINDINGS:
            continue
        parts = [part.strip() for part in line[1:].split(",")]
        if not parts[-1].lower().endswith(".dbf"):
            continue
        if len(parts) != 4:
            raise CnvFormatError(
                f"DEF line {lineno} names a DBF outside the known layouts: {line!r}"
            )
        label, field, column, table = parts
        lookups.append(DefLookup(line[0], label, field.upper(), column.upper(), table))
    return lookups


def dbf_lookup_map(dbf: bytes, field: str, column: str) -> dict[str, str]:
    """Code -> description from a related DBF, as TabWin reads it (p. 88).

    The key is the DBF's field named like ``field`` or, when it has none, its first
    field ("o DBF será indexado pelo primeiro campo de sua estrutura"). Keys are
    right-stripped as the lake stores a DBF ``C`` value; a key listed twice raises.
    """
    names = [f.name.upper() for f in _read_field_descriptors(dbf)]
    key = field if field in names else names[0]
    labels: dict[str, str] = {}
    for record in _stream_records(dbf, encoding="latin-1"):
        values = {name.upper(): value for name, value in record.items()}
        code = str(values[key]).rstrip()
        if code in labels:
            raise CnvFormatError(f"{key} {code!r} is listed twice in the related DBF")
        labels[code] = str(values[column]).strip()
    return labels


def parse_cnv(text: str) -> list[CnvLine]:
    """Lines of a CNV table; each code stays only on the last line that lists it.

    "Lists" counts explicit codes and every code a range expands to, so SIH SEXO.CNV
    (``Ignorado 0-9``, then ``Masculino 1``) keeps ``1`` on the Masculino line. A long
    code (width over 4) listed twice raises ``CnvFormatError``.
    """
    lines = [line.split(";", 1)[0].rstrip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    header = _HEADER.fullmatch(lines[0].strip()) if lines else None
    if header is None:
        raise CnvFormatError(f"CNV header is not '<categories> <characters>': {lines[:1]!r}")
    wide = header.group(1) is not None
    number, gap, label, codes_at = (9, 11, 111, 112) if wide else (7, 9, 59, 60)
    parsed: list[CnvLine] = []
    claimed: dict[str, str] = {}  # code -> how it was claimed, for the error message
    owner: dict[str, int] = {}  # code -> index in `parsed` of the last line listing it
    width = int(header.group(3))
    for line in lines[1:]:
        if (
            not line[:number].strip().isdigit()
            or line[number:gap].strip()
            or (line[label:codes_at].strip() and not line[codes_at:].strip())
        ):
            raise CnvFormatError(f"CNV line outside the column layout: {line!r}")
        tokens = line[codes_at:].split(",")
        if tokens[-1] == "":
            tokens.pop()  # the comma that ends a list
        if not tokens:
            raise CnvFormatError(f"CNV line without codes: {line!r}")
        codes, expanded = [], []
        for token in tokens:
            bounds = _RANGE.fullmatch(token)
            if bounds is None and _OTHER_RANGE.fullmatch(token):
                raise CnvFormatError(f"CNV non-numeric range: {token!r}")
            if any(len(bound) > width for bound in token.split("-")):
                raise CnvFormatError(f"CNV code {token!r} wider than the declared {width}")
            if bounds is None:
                codes.append(token)
                _claim(claimed, token, "explicit", width)
                continue
            first, last = bounds.groups()
            if len(first) != len(last):
                raise CnvFormatError(f"CNV range of unequal width: {token!r}")
            for n in range(int(first), int(last) + 1):
                expanded.append(str(n).zfill(len(first)))
                _claim(claimed, expanded[-1], f"in range {token}", width)
        owner.update(dict.fromkeys((*codes, *expanded), len(parsed)))
        parsed.append(
            CnvLine(int(line[:number]), line[gap:codes_at].rstrip(), tuple(codes), tuple(expanded))
        )
    return [
        CnvLine(
            line.category,
            line.label,
            tuple(code for code in line.codes if owner[code] == index),
            tuple(code for code in line.ranged if owner[code] == index),
        )
        for index, line in enumerate(parsed)
    ]


def _claim(claimed: dict[str, str], code: str, how: str, width: int) -> None:
    if code in claimed and width > 4:
        raise CnvFormatError(f"CNV claims long code {code!r} twice: {claimed[code]} and {how}")
    claimed[code] = how


def cnv_map(lines: list[CnvLine]) -> dict[str, str]:
    """Code -> label, keyed as the lake stores a DBF ``C`` value.

    Ingestion right-strips blanks from character fields (dbfread2 ``parseC``:
    ``data.rstrip(b'\\0 ')``), so the key is the written code right-stripped:
    ``"0 "`` becomes ``"0"`` and the blank code ``" "`` becomes ``""``.
    """
    decode: dict[str, str] = {}
    for line in lines:
        for code in (*line.codes, *line.ranged):
            key = code.rstrip(" ")
            if key in decode:
                raise CnvFormatError(f"CNV codes collide once blanks are stripped: {key!r}")
            decode[key] = line.label
    return decode


def range_keys(lines: list[CnvLine]) -> frozenset[str]:
    """Keys of :func:`cnv_map` whose label comes only from a ``first-last`` range.

    A range can reserve every code of the width for one label, as SIH SEXO.CNV does
    with ``Ignorado 0-9``: a published code it labels is not one the table names.
    :func:`parse_cnv` leaves each code on the last line that lists it, so a code a
    later line lists by itself is not a range key. A range code is digits only, so it
    is a :func:`cnv_map` key as written.
    """
    return frozenset(code for line in lines for code in line.ranged)
