"""DATASUS DBC file names: what a listed name says about its scope and part.

Pure — no network, no cache. Decoding is always *for one row*: a directory
holds files of many datasets (SIASUS/200801_/Dados carries PA*, SAD* and the
APAC family), and the same prefix may be registered by an ad-hoc ``Dataset``,
so there is no global "which dataset owns this name" map.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from omnisus.sources._base import ALL_UFS, ScopeKey
from omnisus.sources.datasus_ftp.datasets import Dataset, in_coverage


def _yy_to_year(d: Dataset, yy: int) -> int:
    """The year ending in ``yy`` in the hundred years from the row's first covered year.

    A fixed pivot cannot serve SIM CID-9 (``79`` is 1979) and the SIM subsets (``25``
    is 2025) at once; each row's listing-read coverage settles the century.
    """
    first = d.coverage[0][0]
    return first + (yy - first) % 100


@dataclass(frozen=True)
class SourceName:
    """What one DATASUS file name says: its scope, and its part when the month is split."""

    scope: ScopeKey
    part: str | None
    """``"1"``, ``"2"``… for ``_1``/``_2`` names, ``"a"``… for letter names, ``None`` for a whole file."""


def parse_name(d: Dataset, name: str) -> SourceName | None:
    """Read ``name`` as a file of row ``d``, or ``None`` when it is not one.

    Case-insensitive, like the server, except the letter of a part, which is
    one lowercase letter. Yearly state rows take the row's
    ``year_digits`` (``DORR2023.dbc``, SIM CID-9's ``DORRR79.DBC``). National rows read
    ``PREFIX + national_code + YY``. State rows accept only the 27 UFs, so
    national aggregates such as ``DOBR2022.dbc`` or ``DNEX2025.dbc`` are never
    read as a state. Monthly rows accept the two part shapes DATASUS uses when
    it splits a month: ``BIMG2412_1.dbc`` and ``PASP2401a.dbc``. A shorter
    prefix never swallows a longer family's file: the groups are fixed width.

    A name whose scope falls outside the row's ``coverage`` is not a file of the row: two
    rows of one directory and prefix (RD 1992-1997 and 1998-2007, ADR 0002) each read
    only their own months, and neither claims the other's.
    """
    parsed = _parse_name(d, name)
    return parsed if parsed is not None and in_coverage(d, parsed.scope) else None


def _parse_name(d: Dataset, name: str) -> SourceName | None:
    prefix = re.escape(d.prefix)
    if d.geography == "national":
        m = re.fullmatch(
            prefix + re.escape(d.national_code) + r"(\d{2})\.dbc", name, re.IGNORECASE
        )
        return SourceName(ScopeKey(uf=None, ano=_yy_to_year(d, int(m[1]))), None) if m else None
    if d.monthly:
        m = re.fullmatch(
            prefix + r"([A-Z]{2})(\d{2})(\d{2})(?:_(\d+)|((?-i:[a-z])))?\.dbc", name, re.IGNORECASE
        )
        if m is None or m[1].upper() not in ALL_UFS or not 1 <= int(m[3]) <= 12:
            return None
        part = m[4] or m[5]
        scope = ScopeKey(uf=m[1].upper(), ano=_yy_to_year(d, int(m[2])), mes=int(m[3]))
        return SourceName(scope, part)
    digits = r"(\d{4})" if d.year_digits == 4 else r"(\d{2})"
    m = re.fullmatch(prefix + r"([A-Z]{2})" + digits + r"\.dbc", name, re.IGNORECASE)
    if m is None or m[1].upper() not in ALL_UFS:
        return None
    year = int(m[2]) if d.year_digits == 4 else _yy_to_year(d, int(m[2]))
    return SourceName(ScopeKey(uf=m[1].upper(), ano=year), None)


def decode_for(d: Dataset, name: str) -> ScopeKey | None:
    """The scope of ``name`` for row ``d`` (a whole file or one of its parts), or ``None``."""
    parsed = parse_name(d, name)
    return None if parsed is None else parsed.scope


def national_variant(d: Dataset, name: str) -> bool:
    """Whether ``name`` is a national aggregate published beside ``d``'s state files.

    DATASUS publishes ``DOBR2022.dbc`` (Brazil) and ``DNEX2025.dbc`` next to
    the per-UF files of SIM and SINASC. They are not states; this names them
    so the weekly probe can tell them from a file it does not understand.

    The year is 2 or 4 digits: the live SINASC/PRELIM/DNRES directory carries
    both ``DNEX2025.dbc`` and a same-family ``DNEX25.dbc`` (confirmed live
    2026-09-21) — DATASUS is not consistent about which width it uses here.
    """
    return (
        d.geography == "state"
        and not d.monthly
        and re.fullmatch(
            re.escape(d.prefix) + r"(?:BR|EX)\d{2}(?:\d{2})?\.dbc", name, re.IGNORECASE
        )
        is not None
    )
