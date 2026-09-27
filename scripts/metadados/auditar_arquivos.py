"""Audita DBCs completos por manifesto; exporta apenas schemas e agregados.

A identidade é conferida antes do parsing. O modo --candidate avalia as regras
existentes sem ampliar a aplicabilidade; só o aceite usa analytical_projection.
Não modifica o lake, o manifesto nem os dicionários. Caminhos são relativos à raiz.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import duckdb

import omnisus as sus
from omnisus.lake.sql import quote_identifier as qi
from omnisus.sources.datasus_ftp.datasets import release_from_uri, resolve
from omnisus.sources.datasus_ftp.filenames import parse_name
from omnisus.sources.datasus_ftp.staging import dbc_bytes_to_parquet
from omnisus.transforms.age import age_expressions, decode_age
from omnisus.transforms.analytics import _date_expressions, _sex_expressions

ROOT = Path(__file__).resolve().parents[2]


def audit(item: dict, *, candidate: bool) -> dict:
    dataset = item["dataset"]
    context = sus.SourceContext(sus.ScopeKey(**item["scope"]), item["release"], item["sha256"])
    path = ROOT / item["path"]
    name = parse_name(resolve(dataset), path.name)
    if name is None or name.scope != context.scope or name.part is not None:
        raise ValueError("Source filename does not match dataset/scope")
    if Path(urlparse(item["url"]).path).name != path.name:
        raise ValueError("Source filename does not match dataset/scope")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("Source hash differs from the recorded manifest")
    uri_release = release_from_uri(dataset, item["url"])
    if uri_release != item["release"]:
        # A legacy directory requires the original, preserved portal response.
        portal_path = ROOT / item["release_evidence"]
        portal_bytes = portal_path.read_bytes()
        if hashlib.sha256(portal_bytes).hexdigest() != item["release_evidence_sha256"]:
            raise ValueError("Portal evidence hash mismatch")
        portal = json.loads(portal_bytes)
        if item["release"] != "final" or not any(
            row["endereco"] == item["url"] and row["modalidade"] == "Dados - Finais"
            for row in portal["resposta"]
        ):
            raise ValueError("Release not confirmed by original portal evidence")
    metadata = sus.describe_dataset(dataset)
    rules = metadata["analytics"]
    age_rule = rules["age"]
    queries = []
    with tempfile.TemporaryDirectory(prefix="omnisus-rule-audit-") as directory:
        staged = Path(directory) / "source.parquet"
        parsed = dbc_bytes_to_parquet(
            raw,
            staged,
            dataset=dataset,
            ano=context.scope.ano,
            uf=context.scope.uf,
            mes=context.scope.mes,
            release=context.release,
        )
        staged_hash = hashlib.sha256(staged.read_bytes()).hexdigest()
        with duckdb.connect() as con:
            con.read_parquet(str(staged)).create_view("source")

            def query(name: str, sql: str) -> list[dict]:
                queries.append({"name": name, "sql": sql})
                cur = con.execute(sql)
                return [
                    dict(zip([x[0] for x in cur.description], row, strict=True))
                    for row in cur.fetchall()
                ]

            schema = {row[0]: row[1] for row in con.execute("DESCRIBE source").fetchall()}
            projection = sus.analytical_projection(
                dataset, observed_schema=schema, scopes=[context]
            )
            age_field = qi(age_rule["field"])
            unit = qi(age_rule["unit_field"]) if age_rule.get("unit_field") else "NULL"
            if candidate:
                age_sql = age_expressions(age_rule, age_field, unit)
                columns = [
                    sus.DerivedColumn("idade_anos_completos", "INTEGER", age_sql.years),
                    sus.DerivedColumn("idade_status", "VARCHAR", age_sql.status),
                    sus.DerivedColumn("idade_quantidade", "INTEGER", age_sql.quantity),
                    sus.DerivedColumn("idade_unidade", "VARCHAR", age_sql.unit),
                ]
                if rules.get("sex"):
                    value, status = _sex_expressions(rules["sex"], qi(rules["sex"]["field"]))
                    columns += [
                        sus.DerivedColumn("sexo_categoria", "VARCHAR", value),
                        sus.DerivedColumn("sexo_status", "VARCHAR", status),
                    ]
                defs = {f["name"]: f for f in metadata["schema"]["fields"]}
                for field in rules.get("dates", []):
                    if field not in schema:
                        continue
                    value, status = _date_expressions(
                        qi(field), schema[field], defs[field]["x-format"]
                    )
                    columns += [
                        sus.DerivedColumn(field + "_data", "DATE", value),
                        sus.DerivedColumn(field + "_data_status", "VARCHAR", status),
                    ]
            else:
                columns = list(projection.columns)
                if not any(x.name == "idade_anos_completos" for x in columns):
                    raise ValueError("Analytical source identity is not confirmed")
            select = ", ".join(f"{x.expression} AS {qi(x.name)}" for x in columns)
            con.execute(f"CREATE VIEW projected AS SELECT *, {select} FROM source")
            result = {
                "dataset": dataset,
                "source": item,
                "candidate": candidate,
                "rule_version": rules["version"],
                "metadata_hash": metadata["metadata_hash"],
                "schema": schema,
                "parsed_rows": parsed.rows,
                "unavailable": [asdict(x) for x in projection.unavailable],
                "expressions": [asdict(x) for x in columns],
                "rows": query("rows", "SELECT count(*) AS n FROM projected")[0]["n"],
                "states": {},
            }
            assert result["rows"] == parsed.rows
            for col in columns:
                if col.name.endswith("status"):
                    states = query(
                        col.name,
                        f"SELECT {qi(col.name)} AS status, count(*) AS n FROM projected GROUP BY ALL ORDER BY 1",
                    )
                    assert sum(x["n"] for x in states) == parsed.rows
                    result["states"][col.name] = states
            result["uninterpreted_age_codes"] = query(
                "uninterpreted_age_codes",
                f"SELECT {age_field} AS value, {unit} AS unit, idade_status AS status, count(*) AS n FROM projected WHERE idade_status IN ('unsupported', 'invalid') GROUP BY ALL ORDER BY ALL",
            )
            result["age_groups"] = query(
                "age_groups",
                f"SELECT {unit} AS unit, idade_status AS status, min(idade_anos_completos) AS minimum, max(idade_anos_completos) AS maximum, count(*) AS n FROM projected GROUP BY ALL ORDER BY ALL",
            )
            distinct = con.execute(
                f"SELECT DISTINCT {age_field}, {unit}, idade_anos_completos, idade_status, "
                f"idade_quantidade, idade_unidade FROM projected"
            ).fetchall()
            for value, unit_value, years, status, quantity, unit_name in distinct:
                scalar = decode_age(age_rule, value, unit_value)
                assert (scalar.years_completed, scalar.status, scalar.quantity) == (
                    years,
                    status,
                    quantity,
                )
                assert unit_name == (scalar.unit if scalar.status == "valid" else None)
            result["sql_scalar_distinct_pairs_checked"] = len(distinct)
            if rules.get("sex"):
                result["sex"] = query(
                    "sex",
                    "SELECT sexo_categoria, sexo_status, count(*) AS n FROM projected GROUP BY ALL ORDER BY ALL",
                )
            birth, event, fmt = (
                ("dtnascmae", "dtnasc", "%d%m%Y")
                if dataset == "sinasc_nascidos_vivos"
                else ("dtnasc", "dtobito", "%d%m%Y")
                if dataset == "sim_obitos"
                else ("nasc", "dt_inter", "%Y%m%d")
            )
            if birth in schema and event in schema:
                sql = f"""WITH dates AS (SELECT idade_anos_completos AS age,
                    CASE WHEN regexp_full_match({qi(birth)}, '[0-9]{{8}}') THEN try_strptime({qi(birth)}, '{fmt}')::DATE END AS birth,
                    CASE WHEN regexp_full_match({qi(event)}, '[0-9]{{8}}') THEN try_strptime({qi(event)}, '{fmt}')::DATE END AS event FROM projected),
                    compared AS (SELECT *, date_diff('year', birth, event) - (strftime(event,'%m%d') < strftime(birth,'%m%d'))::INTEGER AS calculated FROM dates)
                    SELECT count(*) AS total, count(*) FILTER (WHERE age IS NOT NULL AND birth IS NOT NULL AND event >= birth) AS comparable,
                    count(*) FILTER (WHERE event >= birth AND age = calculated) AS equal,
                    count(*) FILTER (WHERE event >= birth AND age <> calculated) AS different FROM compared"""
                result["date_consistency_not_authority"] = query("date_consistency", sql)[0]
            assert schema == {row[0]: row[1] for row in con.execute("DESCRIBE source").fetchall()}
        assert hashlib.sha256(staged.read_bytes()).hexdigest() == staged_hash
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    result["source_and_staged_data_unchanged"] = True
    result["queries"] = queries
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    report = {
        "audited_at": datetime.now(UTC).isoformat(),
        "library_version": sus.__version__,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "backends": {
            k: os.environ.get(k, "auto") for k in ["OMNISUS_DBC_BACKEND", "OMNISUS_DBF_BACKEND"]
        },
        "files": [audit(item, candidate=args.candidate) for item in json.loads(manifest_bytes)],
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            [
                {
                    "dataset": x["dataset"],
                    "rows": x["rows"],
                    "states": x["states"],
                    "comparison": x.get("date_consistency_not_authority"),
                }
                for x in report["files"]
            ],
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
