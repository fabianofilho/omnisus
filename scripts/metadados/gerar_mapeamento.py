"""Escreve as tabelas do painel de mapeamento: o estado da revisão de cada base.

Nada é digitado à mão. Cada linha repete o que o pacote já devolve em
``sus.describe_datasets`` e no contrato resolvido de ``sus.describe_dataset``, no commit
em que o script roda. Os status são os do contrato (docs/dicionario/contrato.md), como
publicados.

    uv run python scripts/metadados/gerar_mapeamento.py <diretorio_de_saida>

Escreve ``bases.json`` (uma linha por base), ``campos.json`` (uma por campo) e
``issues.json`` (uma por issue), cada um como ``{"rows": [...], "meta": [...]}``.
``meta`` traz este código, a versão do pacote e o commit, para quem lê o painel conferir
de onde o número saiu.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import omnisus as sus

ROOT = Path(__file__).resolve().parents[2]
STATUSES = ("verified_in_source", "conflicting", "unreviewed", "not_found")
"""Os status de uma afirmação, na ordem do contrato."""


def _claim(item: dict, target: str) -> dict:
    return next(claim for claim in item["claims"] if claim["target"] == target)


def build() -> dict[str, list[dict]]:
    """As três tabelas. Um campo "com rótulo" tem códigos no contrato (``x-decode``)."""
    bases: list[dict] = []
    campos: list[dict] = []
    issues: list[dict] = []
    for row in sus.describe_datasets().sort("category", "name").iter_rows(named=True):
        name = row["name"]
        contract = sus.describe_dataset(name)
        analytics = contract.get("analytics") or {}
        base = {
            "base": name,
            "sistema": row["category"],
            "titulo": row["title"],
            "versao_dicionario": contract["dictionary_version"],
            "campos": len(contract["fields"]),
            "com_rotulo": 0,
            **{f"rotulo_{status}": 0 for status in STATUSES},
            "com_formato": 0,
            "formato_verified_in_source": 0,
            "aplicabilidade_confirmed": 0,
            "issues_open": 0,
            "issues_resolved": 0,
            "categorias_harmonizadas": ", ".join(
                key for key in ("age", "sex", "dates") if analytics.get(key)
            ),
            "fontes_validadas": len(analytics.get("validated_sources") or []),
            "documentos_fonte": len(contract["sources"]),
        }
        for item in contract["fields"]:
            field = item["field"]
            codes, fmt = _claim(item, "/field/codes"), _claim(item, "/field/format")
            n_codes = len(field["codes"])
            if n_codes:
                base["com_rotulo"] += 1
                base[f"rotulo_{codes['status']}"] += 1
            if field["format"]:
                base["com_formato"] += 1
                base["formato_verified_in_source"] += fmt["status"] == "verified_in_source"
            base["aplicabilidade_confirmed"] += item["applicability"]["status"] == "confirmed"
            campos.append(
                {
                    "chave": f"{name}.{field['name']}",
                    "base": name,
                    "campo": field["name"],
                    "rotulo_do_campo": field["label"],
                    "tipo": field["logical_type"],
                    "codigos": n_codes,
                    "status_codigos": codes["status"] if n_codes else None,
                    "metodo_codigos": codes["method"] if n_codes else None,
                    "revisor_codigos": codes["reviewer"] if n_codes else None,
                    "formato": field["format"],
                    "status_formato": fmt["status"] if field["format"] else None,
                    "aplicabilidade": item["applicability"]["status"],
                    "issues_open": ", ".join(
                        issue["id"] for issue in item["issues"] if issue["status"] == "open"
                    ),
                }
            )
            for issue in item["issues"]:
                base[f"issues_{issue['status']}"] += 1
                issues.append(
                    {
                        "chave": f"{name}.{field['name']}.{issue['id']}",
                        "base": name,
                        "campo": field["name"],
                        "id": issue["id"],
                        "status": issue["status"],
                        "descricao": issue.get("description"),
                    }
                )
        bases.append(base)
    return {"bases": bases, "campos": campos, "issues": issues}


def main(out: Path) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    meta = [
        {
            "label": Path(__file__).name,
            "value": Path(__file__).read_text(encoding="utf-8"),
            "type": "code",
            "lang": "python",
        },
        {"label": "Entrada", "value": f"omnisus {sus.__version__}, commit {commit}"},
        {"label": "Gerado em (UTC)", "value": datetime.now(UTC).strftime("%Y-%m-%d %H:%M")},
    ]
    out.mkdir(parents=True, exist_ok=True)
    for stem, rows in build().items():
        document = {"rows": rows, "meta": meta}
        (out / f"{stem}.json").write_text(
            json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
