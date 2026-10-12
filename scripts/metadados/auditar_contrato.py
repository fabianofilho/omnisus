"""Audita SIM/SIH via LakeReader fixado; exporta somente metadados e agregados.

Três modos, mutuamente exclusivos: auditoria padrão (schemas, publicações,
SQL e agregados de referência), `--acceptance-only` (projeção pública) e
`--decode-coverage` (cobertura de `x-decode` por dataset do snapshot).

As expressões de referência reproduzem hipóteses avaliadas no plano. Não são
regras de produção nem prova de vigência documental; consulte regras.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import yaml

import omnisus
from omnisus import LakeReader
from omnisus.lake.sql import qualified, quote_identifier

DATASETS = ("sim_obitos", "sih_aih_reduzida")
ROOT = Path(__file__).resolve().parents[2]


def reference_age(dataset: str) -> str:
    """Hipótese histórica do plano, deliberadamente independente do runtime."""
    if dataset == "sim_obitos":
        return """CASE WHEN regexp_full_match(trim(idade), '[0-9]{3}')
          AND trim(idade) <> '000' THEN CASE
            WHEN substr(trim(idade),1,1) IN ('0','1','2','3') THEN 0
            WHEN substr(trim(idade),1,1) = '4' THEN try_cast(substr(idade,2) AS INTEGER)
            WHEN substr(trim(idade),1,1) = '5' THEN 100 + try_cast(substr(idade,2) AS INTEGER)
          END END"""
    return """CASE WHEN try_cast(idade AS INTEGER) BETWEEN 0 AND 99 THEN CASE
        WHEN trim(cod_idade) IN ('2','3') THEN 0
        WHEN trim(cod_idade) = '4' THEN try_cast(idade AS INTEGER)
        WHEN trim(cod_idade) = '5' THEN 100 + try_cast(idade AS INTEGER)
      END END"""


def age_band() -> str:
    return """CASE WHEN age IS NULL THEN 'Desconhecida'
       WHEN age < 5 THEN '0-4' WHEN age < 15 THEN '5-14'
       WHEN age < 25 THEN '15-24' WHEN age < 35 THEN '25-34'
       WHEN age < 45 THEN '35-44' WHEN age < 55 THEN '45-54'
       WHEN age < 65 THEN '55-64' WHEN age < 75 THEN '65-74'
       ELSE '75+' END"""


def audit(target: str, snapshot_id: int, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    queries: list[dict] = []
    evidence: dict = {
        "audited_at": datetime.now(UTC).isoformat(),
        "target_kind": "postgresql" if "postgresql:" in target else "local",
        "snapshot_id": snapshot_id,
        "library_version": omnisus.__version__,
        "library_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "interpretation": "reference_hypothesis_not_universal_documentary_authority",
        "datasets": {},
    }
    with LakeReader(target, snapshot_id=snapshot_id) as reader:
        con = reader.connect()

        def query(name: str, sql: str) -> list[dict]:
            queries.append({"name": name, "sql": sql})
            cur = con.execute(sql)
            columns = [item[0] for item in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]

        evidence["snapshots_before"] = query(
            "snapshots_before",
            """SELECT snapshot_id,
            snapshot_time::VARCHAR AS snapshot_time, changes::VARCHAR AS changes
            FROM ducklake_snapshots('lake') ORDER BY snapshot_id""",
        )
        evidence["publications"] = query(
            "publications",
            """SELECT publication_id,
            dataset, scope_json, source_sha256, parser_version, run_id, batch_id,
            published_at, rows, active, managed, source_uri
            FROM lake._omnisus_publications ORDER BY dataset, scope_json, publication_id""",
        )
        for dataset in DATASETS:
            table = qualified(reader.alias, dataset)
            resource = files("omnisus.data.dicionarios").joinpath(f"{dataset}.yaml")
            raw = resource.read_bytes()
            declared = {
                f["name"] for f in yaml.load(raw, Loader=yaml.CSafeLoader)["schema"]["fields"]
            }
            schema = query(f"{dataset}.schema", f"DESCRIBE SELECT * FROM {table}")
            observed = {row["column_name"] for row in schema}
            result = {
                "dictionary_sha256": hashlib.sha256(raw).hexdigest(),
                "schema": schema,
                "declared_absent": sorted(declared - observed),
                "observed_undeclared": sorted(observed - declared),
            }
            result["scopes"] = query(
                f"{dataset}.scopes",
                f"""SELECT uf, ano,
                {("mes," if "mes" in observed else "")} _source_release, count(*) AS n
                FROM {table} GROUP BY ALL ORDER BY ALL""",
            )
            result["total"] = query(f"{dataset}.total", f"SELECT count(*) AS n FROM {table}")
            unit = "substr(trim(idade),1,1)" if dataset == "sim_obitos" else "cod_idade"
            result["units"] = query(
                f"{dataset}.units",
                f"""SELECT {unit} AS unit,
                min(idade) AS raw_min, max(idade) AS raw_max, count(*) AS n
                FROM {table} GROUP BY ALL ORDER BY ALL""",
            )
            result["sex"] = query(
                f"{dataset}.sex",
                f"""SELECT sexo, count(*) AS n
                FROM {table} GROUP BY ALL ORDER BY ALL""",
            )
            age = reference_age(dataset)
            result["reference_bands"] = query(
                f"{dataset}.reference_bands",
                f"""WITH decoded AS
                (SELECT {age} AS age FROM {table})
                SELECT {age_band()} AS band, count(*) AS n
                FROM decoded GROUP BY ALL ORDER BY min(age) NULLS LAST""",
            )
            dates = (
                ("dtnasc", "dtobito")
                if dataset == "sim_obitos"
                else ("nasc", "dt_inter", "dt_saida", "gestor_dt")
            )
            fmt = "%d%m%Y" if dataset == "sim_obitos" else "%Y%m%d"
            result["dates"] = {}
            for field in dates:
                if field not in observed:
                    result["dates"][field] = {"unavailable": "field_absent"}
                    continue
                col = quote_identifier(field)
                result["dates"][field] = query(
                    f"{dataset}.dates.{field}",
                    f"""SELECT
                    count(*) AS total,
                    count(*) FILTER (WHERE {col} IS NULL OR trim({col}) = '') AS missing,
                    count(*) FILTER (WHERE {col} IS NOT NULL AND trim({col}) <> ''
                      AND (NOT regexp_full_match({col}, '[0-9]{{8}}')
                      OR try_strptime({col}, '{fmt}') IS NULL)) AS invalid,
                    count(*) FILTER (WHERE regexp_full_match({col}, '[0-9]{{8}}')
                      AND try_strptime({col}, '{fmt}') IS NOT NULL) AS valid
                    FROM {table}""",
                )
            if dataset == "sim_obitos":
                result["sentinels"] = query(
                    f"{dataset}.sentinels",
                    f"""SELECT
                    count(*) FILTER (WHERE idade = '000') AS code_000,
                    count(*) FILTER (WHERE idade = '400') AS code_400,
                    count(*) FILTER (WHERE idade LIKE '9%') AS code_9xx,
                    count(*) FILTER (WHERE idade LIKE '%99') AS suffix_99
                    FROM {table}""",
                )
                result["documentary_domain_exceptions"] = query(
                    f"{dataset}.domain_exceptions",
                    f"""SELECT idade, count(*) AS n
                    FROM {table} WHERE idade IN ('100','200','300')
                    OR (substr(idade,1,1) = '0' AND try_cast(substr(idade,2) AS INT) > 59)
                    OR (substr(idade,1,1) = '1' AND try_cast(substr(idade,2) AS INT) > 23)
                    OR (substr(idade,1,1) = '2' AND try_cast(substr(idade,2) AS INT) > 29)
                    OR (substr(idade,1,1) = '3' AND try_cast(substr(idade,2) AS INT) > 11)
                    GROUP BY ALL ORDER BY ALL""",
                )
                result["suffix99"] = query(
                    f"{dataset}.suffix99",
                    f"""SELECT idade,
                    count(*) AS n FROM {table} WHERE idade LIKE '%99'
                    GROUP BY ALL ORDER BY ALL""",
                )
            else:
                result["sentinel999_by_unit"] = query(
                    f"{dataset}.sentinel999",
                    f"""SELECT
                    cod_idade, count(*) AS total,
                    count(*) FILTER (WHERE idade = 999) AS value_999
                    FROM {table} GROUP BY ALL ORDER BY ALL""",
                )
                result["birth_admission_consistency"] = query(
                    f"{dataset}.birth_consistency",
                    f"""
                    WITH parsed AS (SELECT cod_idade, idade, {age} AS age,
                    try_strptime(nasc, '%Y%m%d') AS birth,
                    try_strptime(dt_inter, '%Y%m%d') AS admission,
                    try_strptime(dt_saida, '%Y%m%d') AS discharge FROM {table})
                    SELECT cod_idade, count(*) AS total,
                    count(*) FILTER (WHERE birth IS NULL OR admission IS NULL) AS invalid_dates,
                    count(*) FILTER (WHERE birth > admission) AS birth_after_admission,
                    count(*) FILTER (WHERE age = date_part('year', age(admission,birth)))
                      AS matches_completed_years,
                    count(*) FILTER (WHERE age = date_part('year', age(discharge,birth)))
                      AS matches_completed_years_at_discharge,
                    min(date_part('year', age(admission,birth)) - idade) AS min_years_minus_raw,
                    max(date_part('year', age(admission,birth)) - idade) AS max_years_minus_raw
                    FROM parsed GROUP BY ALL ORDER BY ALL""",
                )
            evidence["datasets"][dataset] = result
        evidence["snapshots_after"] = query(
            "snapshots_after",
            """SELECT snapshot_id,
            snapshot_time::VARCHAR AS snapshot_time, changes::VARCHAR AS changes
            FROM ducklake_snapshots('lake') ORDER BY snapshot_id""",
        )
    evidence["snapshot_history_unchanged"] = (
        evidence["snapshots_before"] == evidence["snapshots_after"]
    )
    (out / "audit.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    (out / "queries.sql").write_text(
        "\n\n".join(f"-- {q['name']}\n{q['sql']};" for q in queries) + "\n", encoding="utf-8"
    )
    print(f"Auditoria salva em {out}; snapshot {snapshot_id}; somente agregados.")


def audit_projection(target: str, snapshot_id: int, out: Path) -> None:
    """Verifica o contrato público sem substituir a auditoria de referência."""
    from dataclasses import asdict

    from omnisus import SourceContext, analytical_projection

    queries: list[str] = []
    evidence: dict = {
        "snapshot_id": snapshot_id,
        "target_kind": "postgresql" if "postgresql:" in target else "local",
        "library_version": omnisus.__version__,
        "audited_at": datetime.now(UTC).isoformat(),
        "datasets": {},
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "library_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
    }
    with LakeReader(target, snapshot_id=snapshot_id) as reader:
        con = reader.connect()
        evidence["snapshots_before"] = reader.snapshots()
        publications = reader.publications()

        def query(sql: str) -> list[dict]:
            queries.append(sql)
            cur = con.execute(sql)
            keys = [d[0] for d in cur.description]
            return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]

        for dataset in DATASETS:
            table = qualified(reader.alias, dataset)
            schema = query(f"DESCRIBE SELECT * FROM {table}")
            total = query(f"SELECT count(*) AS n FROM {table}")[0]["n"]
            selected = [p for p in publications if p["dataset"] == dataset and p["active"]]
            projection = analytical_projection(
                dataset,
                observed_schema={r["column_name"]: r["column_type"] for r in schema},
                scopes=[SourceContext.from_publication(p) for p in selected],
            )
            if projection.unavailable:
                raise RuntimeError(f"Projection unavailable: {dataset}: {projection.unavailable}")
            fields = ", ".join(
                f"{c.expression} AS {quote_identifier(c.name)}" for c in projection.columns
            )
            cte = f"WITH derived AS (SELECT {fields} FROM {table}) "
            bands = query(
                cte
                + f""", banded AS (
                SELECT idade_anos_completos AS age FROM derived)
                SELECT {age_band()} AS band, count(*) AS n FROM banded
                GROUP BY ALL ORDER BY min(age) NULLS LAST"""
            )
            sex = query(
                cte
                + """SELECT sexo_categoria, sexo_status, count(*) AS n
                FROM derived GROUP BY ALL ORDER BY ALL"""
            )
            statuses = {}
            for col in projection.columns:
                if col.name.endswith("_status"):
                    name = quote_identifier(col.name)
                    statuses[col.name] = query(
                        cte
                        + f"""SELECT {name} AS status,
                        count(*) AS n FROM derived GROUP BY ALL ORDER BY ALL"""
                    )
            assert sum(r["n"] for r in bands) == total
            assert sum(r["n"] for r in sex) == total
            for counts in statuses.values():
                assert sum(r["n"] for r in counts) == total
            schema_after = query(f"DESCRIBE SELECT * FROM {table}")
            total_after = query(f"SELECT count(*) AS n FROM {table}")[0]["n"]
            evidence["datasets"][dataset] = {
                "projection": asdict(projection),
                "publications": [
                    {
                        k: p[k]
                        for k in ("publication_id", "scope_json", "source_sha256", "source_uri")
                    }
                    for p in selected
                ],
                "schema_before": schema,
                "schema_after": schema_after,
                "total_before": total,
                "total_after": total_after,
                "bands": bands,
                "sex": sex,
                "statuses": statuses,
                "raw_schema_and_total_unchanged": schema == schema_after and total == total_after,
            }
        evidence["snapshots_after"] = reader.snapshots()
    evidence["snapshot_history_unchanged"] = (
        evidence["snapshots_before"] == evidence["snapshots_after"]
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "acceptance.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (out / "acceptance.sql").write_text(";\n\n".join(queries) + ";\n", encoding="utf-8")
    print(f"Aceite da projeção pública salvo em {out}.")


def audit_decode_coverage(target: str, snapshot_id: int, out: Path) -> None:
    """Valores sem chave exata no `x-decode`, por dataset do snapshot (decode_coverage)."""
    from dataclasses import asdict

    from omnisus.transforms.dictionaries import decode_coverage

    packaged = {
        p.name.removesuffix(".yaml")
        for p in files("omnisus.data.dicionarios").iterdir()
        if p.name.endswith(".yaml")
    }
    report: dict = {"snapshot_id": snapshot_id, "datasets": {}}
    with LakeReader(target, snapshot_id=snapshot_id) as reader:
        con = reader.connect()
        for dataset in sorted(packaged.intersection(reader.tables())):
            relation = con.sql(f"SELECT * FROM {qualified(reader.alias, dataset)}")
            report["datasets"][dataset] = [asdict(u) for u in decode_coverage(dataset, relation)]
    out.mkdir(parents=True, exist_ok=True)
    (out / "decode-coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Cobertura de x-decode salva em {out}; snapshot {snapshot_id}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--snapshot-id", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--acceptance-only", action="store_true")
    mode.add_argument("--decode-coverage", action="store_true")
    args = parser.parse_args()
    if args.acceptance_only:
        audit_projection(args.target, args.snapshot_id, args.out)
    elif args.decode_coverage:
        audit_decode_coverage(args.target, args.snapshot_id, args.out)
    else:
        audit(args.target, args.snapshot_id, args.out)


if __name__ == "__main__":
    main()
