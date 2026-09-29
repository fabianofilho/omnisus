"""Audit one more source for a dataset's analytical rules; with --accept, record it.

    uv run python scripts/metadados/validar_fonte.py sih_aih_reduzida --uf RR --year 2024 --month 1

Downloads the file the server lists for that scope, hashes it and runs the candidate
audit of ``auditar_arquivos.py`` (every rule applied, SQL checked against the scalar
decoder). The evidence goes to ``evidence/<date>-validacao-<dataset>-<scope>/``
and a summary of each status column is printed. Read it: ``unsupported`` and
``invalid`` rows stay null in the harmonised columns, and deciding whether the rule
reads this file correctly is a reviewer's call (ADR 0003).

``--accept`` then appends the source to ``x-analytics.validated_sources`` of the
packaged dictionary. Commit the evidence and the dictionary in one PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

import omnisus as sus
from omnisus._loop import run_sync
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._ftp import ftp_host
from omnisus.sources.datasus_ftp.datasets import resolve
from omnisus.sources.datasus_ftp.fetch import fetch_dbc_bytes
from omnisus.sources.datasus_ftp.inventory import list_sources

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auditar_arquivos import audit

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = ROOT / "src" / "omnisus" / "data" / "dicionarios"


def _entry_lines(entry: dict) -> list[str]:
    lines = [
        f"  - {key}: {value}" if i == 0 else f"    {key}: {value}"
        for i, (key, value) in enumerate(entry.items())
    ]
    return [line + "\n" for line in lines]


def append_validated_source(yaml_path: Path, entry: dict) -> bool:
    """Append ``entry`` to ``x-analytics.validated_sources``; ``False`` if already there.

    The file is edited as text, so comments and key order survive; the parsed
    result is checked to differ from the original by that one entry only.
    """
    text = yaml_path.read_text(encoding="utf-8")
    before = yaml.safe_load(text)
    if entry in before["x-analytics"]["validated_sources"]:
        return False
    lines = text.splitlines(keepends=True)
    start = next(
        i
        for i, line in enumerate(lines)
        if line == "  validated_sources:\n" and "x-analytics:\n" in lines[:i]
    )
    end = start + 1
    while end < len(lines) and lines[end].startswith(("  - ", "    ")):
        end += 1
    lines[end:end] = _entry_lines(entry)
    new_text = "".join(lines)
    after = yaml.safe_load(new_text)
    if after["x-analytics"]["validated_sources"].pop() != entry or after != before:
        raise RuntimeError(f"{yaml_path.name}: the edit changed more than validated_sources")
    yaml_path.write_text(new_text, encoding="utf-8")
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    dictionaries: Path = DICTIONARIES,
    evidence: Path = ROOT / "reports" / "evidence",
    downloads: Path = ROOT / "data" / "raw" / "auditoria",
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset")
    parser.add_argument("--uf")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int)
    parser.add_argument("--accept", action="store_true", help="record the source as validated")
    args = parser.parse_args(argv)

    d = resolve(args.dataset)
    scope = ScopeKey(uf=args.uf, ano=args.year, mes=args.month)
    listed = list_sources(d, refresh=True).get(scope)
    if listed is None:
        print(f"{d.name}: the server lists no file for {scope}", file=sys.stderr)
        return 1
    if len(listed.files) != 1:
        print(f"{d.name} {scope} is split into {len(listed.files)} files; audit it by hand")
        return 1
    (entry,) = listed.files
    raw = run_sync(lambda: fetch_dbc_bytes(entry))
    downloads.mkdir(parents=True, exist_ok=True)
    path = downloads / entry.name
    path.write_bytes(raw)
    item = {
        "dataset": d.name,
        "path": str(path),
        "url": f"ftp://{ftp_host()}{entry.path}",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "scope": {"uf": scope.uf, "ano": scope.ano, "mes": scope.mes},
        "release": listed.release,
    }
    result = audit(item, candidate=True)

    now = datetime.now(UTC)
    folder = evidence / f"{now:%Y-%m-%d}" / f"validacao-{d.name}-{scope}"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = json.dumps([item], ensure_ascii=False, indent=2) + "\n"
    (folder / "manifest.json").write_text(manifest, encoding="utf-8")
    report = {
        "audited_at": now.isoformat(),
        "library_version": sus.__version__,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
        "backends": {
            k: os.environ.get(k, "auto") for k in ["OMNISUS_DBC_BACKEND", "OMNISUS_DBF_BACKEND"]
        },
        "files": [result],
    }
    (folder / "acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"{d.name} {scope}: {result['rows']} rows, evidence in {folder}")
    for column, states in result["states"].items():
        print(f"  {column}: " + ", ".join(f"{s['status']} {s['n']}" for s in states))

    if args.accept:
        source = {**{k: v for k, v in item["scope"].items() if v is not None}}
        source |= {"release": item["release"], "source_sha256": item["sha256"]}
        yaml_path = dictionaries / f"{d.name}.yaml"
        if append_validated_source(yaml_path, source):
            print(f"recorded in {yaml_path}")
        else:
            print(f"already in {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
