"""Audit a batch of sources for a dataset's analytical rules; with --accept, record them.

    uv run python scripts/metadados/validar_fonte.py sim_obitos --ufs ALL --inicio 2020 --fim 2024
    uv run python scripts/metadados/validar_fonte.py sih_aih_reduzida --ufs ALL \
        --inicio 2020-01 --fim 2025-02 --accept
    uv run python scripts/metadados/validar_fonte.py sinan_chagas --inicio 2023 --fim 2023 \
        --referencia national_2023

The server is listed once. The reference scope (``--referencia``, or ``REFERENCIAS``
for SIM and SIH) is audited first and must be the file validated by hand: its scope,
release and SHA-256 are in ``x-analytics.validated_sources``. Then every scope of the
window (``--ufs`` only for a dataset published per UF): the file the server lists is
downloaded, hashed, run through the candidate audit of ``auditar_arquivos.py`` (every
rule applied, SQL checked against the scalar decoder) and deleted. A run that stops
resumes from ``<downloads>/parcial-*.jsonl`` without downloading again what it audited;
a failed audit, or one made under another dictionary version, is done again.

The evidence goes to ``evidence/<date>-validacao-<dataset>-<inicio>-<fim>/``:
``manifest.json`` (url, SHA-256, size and server time of every file), ``escopos.csv``
(decision and reasons per scope), ``estados.csv`` (each status column), ``idades.csv``
(age codes the rule leaves uninterpreted, and why), ``datas.csv`` (age against dates,
not an authority) and ``referencia.json`` (schema, expressions and queries of the
reference, and the run's provenance). No local path is recorded, and a run never
replaces an existing folder.

The acceptance rule (ADR 0003, Consequences) blocks a scope whose audit raised, whose
schema differs from the reference's, with a sex code the rule does not know, or with an
age whose unit the rule does not declare: those are the signs of a code that changed
meaning. Ages outside a declared unit's bounds, invalid composites and malformed text
are reported, not blocked: the rule already keeps them null.

``--accept`` appends every accepted scope to ``x-analytics.validated_sources`` in one
edit. Exit code: 0 when no scope is blocked, 2 when some are, 1 when nothing could be
audited (an empty window, a scope not listed, no reference, the reference failing or not
the validated file, or the evidence folder already there). A scope the server splits into
several files is blocked without download; its reason names each part and its size.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

import omnisus as sus
from omnisus._loop import run_sync
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._ftp import ftp_host
from omnisus.sources.datasus_ftp.datasets import Dataset, resolve
from omnisus.sources.datasus_ftp.fetch import fetch_dbc_bytes
from omnisus.sources.datasus_ftp.inventory import ResolvedSource, list_sources
from omnisus.transforms.age import decode_age

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auditar_arquivos import audit

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = ROOT / "src" / "omnisus" / "data" / "dicionarios"

REFERENCIAS = {
    # The scopes validated by hand on 2026-09-14 (evidence/2026-09-14-*): every other
    # scope of the batch must have the same staged schema.
    "sim_obitos": ScopeKey(uf="RR", ano=2023),
    "sih_aih_reduzida": ScopeKey(uf="RR", ano=2023, mes=1),
}


def _entry_lines(entry: dict) -> list[str]:
    values = {key: "null" if value is None else value for key, value in entry.items()}
    lines = [
        f"  - {key}: {value}" if i == 0 else f"    {key}: {value}"
        for i, (key, value) in enumerate(values.items())
    ]
    return [line + "\n" for line in lines]


def _identidade(entry: Mapping) -> tuple:
    """Scope, release and SHA-256 of a ``validated_sources`` entry; ``uf: null`` = no uf."""
    return (
        entry.get("uf"),
        entry["ano"],
        entry.get("mes"),
        entry["release"],
        entry["source_sha256"],
    )


def _entrada(fonte: Mapping) -> dict:
    """The ``validated_sources`` entry of one audited file of the manifest: ``uf: null``
    for a national scope, as the dictionaries write it; ``mes`` only for a monthly one."""
    entry = {k: v for k, v in fonte["scope"].items() if k == "uf" or v is not None}
    return entry | {"release": fonte["release"], "source_sha256": fonte["sha256"]}


def append_validated_sources(yaml_path: Path, entries: Sequence[dict]) -> int:
    """Append the new ``entries`` to ``x-analytics.validated_sources``; how many were new.

    The file is edited as text, so comments and key order survive; the parsed result is
    checked to differ from the original by those entries only.
    """
    text = yaml_path.read_text(encoding="utf-8")
    before = yaml.load(text, Loader=yaml.CSafeLoader)
    known = before["x-analytics"]["validated_sources"]
    vistas = {_identidade(entry) for entry in known}
    new = []
    for entry in entries:
        if _identidade(entry) not in vistas:
            vistas.add(_identidade(entry))
            new.append(entry)
    if not new:
        return 0
    lines = text.splitlines(keepends=True)
    start = next(
        i
        for i, line in enumerate(lines)
        if line == "  validated_sources:\n" and "x-analytics:\n" in lines[:i]
    )
    end = start + 1
    while end < len(lines) and lines[end].startswith(("  - ", "    ")):
        end += 1
    lines[end:end] = [line for entry in new for line in _entry_lines(entry)]
    new_text = "".join(lines)
    after = yaml.load(new_text, Loader=yaml.CSafeLoader)
    added = after["x-analytics"]["validated_sources"][len(known) :]
    del after["x-analytics"]["validated_sources"][len(known) :]
    if added != new or after != before:
        raise RuntimeError(f"{yaml_path.name}: the edit changed more than validated_sources")
    yaml_path.write_text(new_text, encoding="utf-8")
    return len(new)


def _periodo(text: str) -> tuple[int, int | None]:
    """``"2020"`` -> ``(2020, None)``; ``"2020-01"`` -> ``(2020, 1)``."""
    ano, _, mes = text.partition("-")
    return int(ano), int(mes) if mes else None


def _escopo(text: str) -> ScopeKey:
    """``"RR_2023"``, ``"RR_2023_01"`` or ``"national_2023"`` as a scope."""
    uf, ano, *mes = text.split("_")
    return ScopeKey(
        uf=None if uf == "national" else uf, ano=int(ano), mes=int(mes[0]) if mes else None
    )


def janela(
    d: Dataset,
    ufs: Sequence[str] | None,
    inicio: tuple[int, int | None],
    fim: tuple[int, int | None],
) -> list[ScopeKey]:
    """Every scope of ``ufs`` (``None``: every UF, or a national dataset), ``inicio`` to ``fim``."""
    mensal = d.monthly
    if mensal != (inicio[1] is not None) or mensal != (fim[1] is not None):
        raise ValueError(f"{d.name}: use {'AAAA-MM' if mensal else 'AAAA'} em --inicio e --fim")
    escopos = sus.scopes_for(d, years=range(inicio[0], fim[0] + 1), ufs=ufs)
    return [
        s
        for s in escopos
        if (inicio[0], inicio[1] or 0) <= (s.ano, s.mes or 0) <= (fim[0], fim[1] or 0)
    ]


def motivo_idade(regra: Mapping, valor: object, unidade: object) -> str:
    """Why the age rule leaves one code uninterpreted (``unsupported`` or ``invalid``)."""
    idade = decode_age(regra, valor, unidade)
    if idade.status == "invalid":
        return "composta inválida" if idade.value is not None else "texto malformado"
    return "fora da faixa da unidade" if idade.unit is not None else "unidade não declarada"


def bloqueios(resultado: Mapping, referencia: Mapping, regra_idade: Mapping) -> list[str]:
    """The acceptance rule: the reasons that keep one audited scope out (empty = accepted)."""
    motivos = []
    if resultado["schema"] != referencia["schema"]:
        ref, novo = referencia["schema"], resultado["schema"]
        faltam = sorted(set(ref) - set(novo))
        sobram = sorted(set(novo) - set(ref))
        tipos = sorted(c for c in set(ref) & set(novo) if ref[c] != novo[c])
        motivos.append(
            f"schema difere da referência: faltam {faltam}, sobram {sobram}, tipos {tipos}"
        )
    sexo = {s["status"]: s["n"] for s in resultado["states"].get("sexo_status", [])}
    if sexo.get("unsupported"):
        motivos.append(f"sexo não suportado em {sexo['unsupported']} linhas")
    for linha in resultado["uninterpreted_age_codes"]:
        if motivo_idade(regra_idade, linha["value"], linha["unit"]) == "unidade não declarada":
            motivos.append(f"idade {linha['value']!r} com unidade não declarada ({linha['n']})")
    return motivos


def _chave(entry) -> dict:
    return {"path": entry.path, "size": entry.size_bytes, "modified": entry.modified.isoformat()}


def _ler_parcial(parcial: Path) -> dict[str, dict]:
    if not parcial.exists():
        return {}
    linhas = [json.loads(x) for x in parcial.read_text(encoding="utf-8").splitlines() if x]
    return {linha["escopo"]: linha for linha in linhas}


def _auditar(d: Dataset, scope: ScopeKey, listed: ResolvedSource, downloads: Path) -> dict:
    (entry,) = listed.files
    raw = run_sync(lambda: fetch_dbc_bytes(entry))
    path = downloads / entry.name
    path.write_bytes(raw)
    fonte = {
        "dataset": d.name,
        "url": f"ftp://{ftp_host()}{entry.path}",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "server_modified": entry.modified.isoformat(),
        "scope": {"uf": scope.uf, "ano": scope.ano, "mes": scope.mes},
        "release": listed.release,
    }
    try:
        resultado, erro = audit({**fonte, "path": str(path)}, candidate=True), None
        resultado.pop("source")
    except Exception as exc:  # recorded and blocked; never accepted
        resultado, erro = None, f"auditoria falhou: {type(exc).__name__}: {exc}"
    path.unlink()
    return {
        "escopo": str(scope),
        "chave": _chave(entry),
        "fonte": fonte,
        "resultado": resultado,
        "erro": erro,
    }


def _csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _escrever(
    pasta: Path,
    registros: dict[ScopeKey, dict],
    decisoes: dict[ScopeKey, list[str]],
    ref: dict,
    regra_idade: Mapping,
) -> None:
    """The evidence of one run; ``decisoes`` is in window order, the reference may be outside."""
    pasta.mkdir(parents=True, exist_ok=True)
    fontes = [r["fonte"] for r in registros.values() if r["fonte"]]
    manifest = json.dumps(fontes, ensure_ascii=False, indent=2) + "\n"
    (pasta / "manifest.json").write_text(manifest, encoding="utf-8")
    auditados = [registros[e] for e in decisoes if registros[e]["resultado"]]
    _csv(
        pasta / "escopos.csv",
        ["escopo", "sha256", "linhas", "decisao", "motivos"],
        [
            [
                str(escopo),
                registros[escopo]["fonte"]["sha256"] if registros[escopo]["fonte"] else "",
                registros[escopo]["resultado"]["rows"] if registros[escopo]["resultado"] else "",
                "bloqueado" if motivos else "aceito",
                "; ".join(motivos),
            ]
            for escopo, motivos in decisoes.items()
        ],
    )
    _csv(
        pasta / "estados.csv",
        ["escopo", "coluna", "status", "n"],
        [
            [r["escopo"], coluna, s["status"], s["n"]]
            for r in auditados
            for coluna, estados in r["resultado"]["states"].items()
            for s in estados
        ],
    )
    _csv(
        pasta / "idades.csv",
        ["escopo", "valor", "unidade", "status", "n", "motivo"],
        [
            [
                r["escopo"],
                x["value"],
                x["unit"],
                x["status"],
                x["n"],
                motivo_idade(regra_idade, x["value"], x["unit"]),
            ]
            for r in auditados
            for x in r["resultado"]["uninterpreted_age_codes"]
        ],
    )
    _csv(
        pasta / "datas.csv",
        ["escopo", "total", "comparable", "equal", "different"],
        [
            [r["escopo"], *r["resultado"]["date_consistency_not_authority"].values()]
            for r in auditados
            if "date_consistency_not_authority" in r["resultado"]
        ],
    )
    referencia = {
        "audited_at": datetime.now(UTC).isoformat(),
        "library_version": sus.__version__,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest.encode()).hexdigest(),
        "backends": {
            k: os.environ.get(k, "auto") for k in ["OMNISUS_DBC_BACKEND", "OMNISUS_DBF_BACKEND"]
        },
        "referencia": ref["escopo"],
        **{
            k: ref["resultado"][k]
            for k in [
                "rule_version",
                "metadata_hash",
                "schema",
                "unavailable",
                "expressions",
                "queries",
            ]
        },
    }
    (pasta / "referencia.json").write_text(
        json.dumps(referencia, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    dictionaries: Path = DICTIONARIES,
    evidence: Path = ROOT / "evidence",
    downloads: Path = ROOT / "data" / "raw" / "auditoria",
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset")
    parser.add_argument(
        "--ufs", help="ALL, ou siglas separadas por vírgula; não numa base nacional"
    )
    parser.add_argument("--inicio", required=True, help="AAAA (anual) ou AAAA-MM (mensal)")
    parser.add_argument("--fim", required=True, help="AAAA (anual) ou AAAA-MM (mensal)")
    parser.add_argument(
        "--referencia", help="escopo validado à mão (RR_2023, RR_2023_01, national_2023)"
    )
    parser.add_argument("--accept", action="store_true", help="record the accepted sources")
    args = parser.parse_args(argv)

    d = resolve(args.dataset)
    if d.geography == "national" and args.ufs:
        print(f"{d.name}: base nacional, sem --ufs", file=sys.stderr)
        return 1
    if d.geography != "national" and not args.ufs:
        print(f"{d.name}: --ufs é obrigatório (ALL ou siglas)", file=sys.stderr)
        return 1
    ufs = None
    if args.ufs and args.ufs != "ALL":
        ufs = [u.strip() for u in args.ufs.split(",")]
    referencia = _escopo(args.referencia) if args.referencia else REFERENCIAS.get(d.name)
    if referencia is None:
        print(
            f"{d.name}: no reference scope; pass --referencia with a scope validated by hand",
            file=sys.stderr,
        )
        return 1
    escopos = janela(d, ufs, _periodo(args.inicio), _periodo(args.fim))
    if not escopos:
        print(f"{d.name}: nenhum escopo de {args.inicio} a {args.fim}", file=sys.stderr)
        return 1
    hoje = datetime.now(UTC)
    pasta = evidence / f"{hoje:%Y-%m-%d}-validacao-{d.name}-{args.inicio}-{args.fim}"
    if pasta.exists():
        print(f"{d.name}: {pasta} already exists; move it before another run", file=sys.stderr)
        return 1
    listing = list_sources(d, refresh=True)
    faltam = [str(s) for s in [referencia, *escopos] if s not in listing]
    if faltam:
        print(f"{d.name}: the server lists no file for {', '.join(faltam)}", file=sys.stderr)
        return 1

    yaml_path = dictionaries / f"{d.name}.yaml"
    dicionario = yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
    validadas = {_identidade(entry) for entry in dicionario["x-analytics"]["validated_sources"]}
    metadados = sus.describe_dataset(d.name)
    metadata_hash = metadados["metadata_hash"]
    downloads.mkdir(parents=True, exist_ok=True)
    parcial = downloads / f"parcial-{d.name}-{args.inicio}-{args.fim}.jsonl"
    feitos = _ler_parcial(parcial)
    registros = {}
    for i, scope in enumerate(dict.fromkeys([referencia, *escopos]), start=1):
        listed = listing[scope]
        feito = feitos.get(str(scope))
        if len(listed.files) != 1:
            partes = "; ".join(f"{f.path}, {f.size_bytes} bytes" for f in listed.files)
            registro = {
                "escopo": str(scope),
                "fonte": None,
                "resultado": None,
                "erro": f"dividido em {len(listed.files)} arquivos ({partes}); audite à mão",
            }
        elif (
            feito
            and feito["erro"] is None
            and feito["chave"] == _chave(listed.files[0])
            and feito["resultado"]["metadata_hash"] == metadata_hash
        ):
            registro = feito
        else:
            registro = _auditar(d, scope, listed, downloads)
            with parcial.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
            linhas = registro["erro"] or f"{registro['resultado']['rows']} linhas"
            print(f"[{i}] {scope}: {linhas}")
        registros[scope] = registro
        if scope != referencia:
            continue
        if registro["erro"]:
            print(f"{d.name}: the reference {scope} failed: {registro['erro']}", file=sys.stderr)
            return 1
        if _identidade(_entrada(registro["fonte"])) not in validadas:
            print(
                f"{d.name}: the reference {scope} on the server "
                f"({registro['fonte']['sha256'][:12]}…) is not the source validated by hand; "
                "validate it by hand first (ADR 0003)",
                file=sys.stderr,
            )
            return 1

    ref = registros[referencia]
    regra_idade = metadados["analytics"]["age"]
    decisoes = {
        s: [registros[s]["erro"]]
        if registros[s]["erro"]
        else bloqueios(registros[s]["resultado"], ref["resultado"], regra_idade)
        for s in escopos
    }
    _escrever(pasta, registros, decisoes, ref, regra_idade)
    parcial.unlink(missing_ok=True)
    bloqueados = [s for s, motivos in decisoes.items() if motivos]
    print(
        f"{d.name}: {len(escopos) - len(bloqueados)} aceitos, {len(bloqueados)} bloqueados; evidência em {pasta.relative_to(evidence.parent)}"
    )
    for s in bloqueados:
        print(f"  {s}: {'; '.join(decisoes[s])}")

    if args.accept:
        aceitos = [_entrada(registros[s]["fonte"]) for s in escopos if not decisoes[s]]
        print(f"{append_validated_sources(yaml_path, aceitos)} new sources in {yaml_path.name}")
    return 2 if bloqueados else 0


if __name__ == "__main__":
    raise SystemExit(main())
