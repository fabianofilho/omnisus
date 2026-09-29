import hashlib
import json
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

import omnisus as sus
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.age import decode_age

ROOT = Path(__file__).resolve().parents[3]


def contexts(dataset):
    rules = sus.describe_dataset(dataset)["analytics"]
    return [
        sus.SourceContext(
            sus.ScopeKey(uf=x["uf"], ano=x["ano"], mes=x.get("mes")),
            x["release"],
            x["source_sha256"],
        )
        for x in rules["validated_sources"]
    ]


def test_projection_requires_confirmed_source_context():
    projection = sus.analytical_projection(
        "sim_obitos", observed_schema={"idade": "VARCHAR"}, scopes=[]
    )
    assert not projection.columns
    assert projection.unavailable


def test_projection_rejects_unknown_version_and_schema_collision():
    with pytest.raises(ValueError, match="version"):
        sus.analytical_projection(
            "sim_obitos", observed_schema={}, scopes=[], rule_version="future"
        )
    with pytest.raises(ValueError, match="collision"):
        sus.analytical_projection(
            "sim_obitos",
            observed_schema={"idade": "VARCHAR", "idade_status": "VARCHAR"},
            scopes=contexts("sim_obitos"),
        )


def test_native_sql_age_sex_dates_and_invalid_dates():
    schema = {"idade": "VARCHAR", "sexo": "VARCHAR", "dtobito": "VARCHAR"}
    projection = sus.analytical_projection(
        "sim_obitos", observed_schema=schema, scopes=contexts("sim_obitos")
    )
    expressions = ", ".join(f'{c.expression} AS "{c.name}"' for c in projection.columns)
    with duckdb.connect() as con:
        rows = con.sql(f"""SELECT {expressions} FROM (VALUES
          ('469','2','01042023'), ('000','9','02012023'), ('310','Z','31022024'),
          (NULL,NULL,NULL)) t(idade,sexo,dtobito)""").fetchall()
        columns = [c.name for c in projection.columns]
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    assert records[0]["idade_anos_completos"] == 69
    assert records[0]["sexo_categoria"] == "female"
    assert records[1]["idade_status"] == "ignored"
    assert records[2]["dtobito_data"] is None
    assert records[2]["dtobito_data_status"] == "invalid"
    assert records[3]["dtobito_data_status"] == "missing"


def test_context_hash_and_scope_must_both_match():
    valid = contexts("sim_obitos")[0]
    for bad in [
        replace(valid, source_sha256="0" * 64),
        replace(valid, scope=sus.ScopeKey("XX", 2024)),
    ]:
        p = sus.analytical_projection(
            "sim_obitos", observed_schema={"idade": "VARCHAR"}, scopes=[bad]
        )
        assert not p.columns
    p = sus.analytical_projection(
        "sim_obitos", observed_schema={"idade": "VARCHAR"}, scopes=[valid, bad]
    )
    assert not p.columns


def test_publication_context_uses_publication_identity():
    row = {
        "dataset": "sim_obitos",
        "scope_json": '{"uf":"RR","ano":2023}',
        "source_uri": "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc",
        "source_sha256": "a" * 64,
    }
    context = sus.SourceContext.from_publication(row)
    assert context.scope == sus.ScopeKey("RR", 2023)
    assert context.release == "final"
    with pytest.raises(ValueError):
        sus.SourceContext.from_publication({})


def test_sinasc_maternal_age_uses_own_rule_and_source_identity():
    dataset = "sinasc_nascidos_vivos"
    rule = sus.describe_dataset(dataset)["analytics"]
    assert rule is not None
    assert rule["age"]["field"] == "idademae"
    assert rule["age"]["subject"] == "mother"
    valid = contexts(dataset)[0]
    schema = {"IDADEMAE": "VARCHAR", "SEXO": "VARCHAR"}
    projection = sus.analytical_projection(dataset, observed_schema=schema, scopes=[valid])
    assert [x.name for x in projection.columns] == [
        "idade_anos_completos",
        "idade_status",
        "idade_quantidade",
        "idade_unidade",
    ]
    expressions = ", ".join(f'{x.expression} AS "{x.name}"' for x in projection.columns)
    with duckdb.connect() as con:
        rows = con.sql(f"""SELECT IDADEMAE, {expressions} FROM
            (VALUES ('25','1'), ('99','2'), ('','2'), ('66','1')) t(IDADEMAE,SEXO)""").fetchall()
    assert rows == [
        ("25", 25, "valid", 25, "year"),
        ("99", None, "ignored", None, None),
        ("", None, "missing", None, None),
        ("66", None, "unsupported", None, None),
    ]
    for bad in [
        replace(valid, source_sha256="0" * 64),
        replace(valid, release="prelim"),
        replace(valid, scope=sus.ScopeKey("RR", 2022)),
    ]:
        for scopes in [[bad], [valid, bad]]:
            assert not sus.analytical_projection(
                dataset, observed_schema=schema, scopes=scopes
            ).columns
    assert not sus.analytical_projection(
        dataset, observed_schema={"idade": "INTEGER"}, scopes=[valid]
    ).columns


@pytest.mark.parametrize(
    ("dataset", "year", "month", "sha"),
    [
        (
            "sim_obitos",
            2021,
            None,
            "600b8af449468fec082e4e7ab6e852abae188cac73743c64dd470d122a41213a",
        ),
        (
            "sih_aih_reduzida",
            2023,
            1,
            "e9f717ff378477a883d19f733efe8409aee7f7795a027584b9f383364264d8e4",
        ),
    ],
)
def test_additional_audited_files_enable_age_sex_and_dates(dataset, year, month, sha):
    context = sus.SourceContext(sus.ScopeKey("RR", year, month), "final", sha)
    date_field = "dtobito" if dataset == "sim_obitos" else "dt_inter"
    schema = {"idade": "VARCHAR", "cod_idade": "VARCHAR", "sexo": "VARCHAR", date_field: "VARCHAR"}
    projection = sus.analytical_projection(dataset, observed_schema=schema, scopes=[context])
    assert {c.name for c in projection.columns} == {
        "idade_anos_completos",
        "idade_status",
        "idade_quantidade",
        "idade_unidade",
        "sexo_categoria",
        "sexo_status",
        date_field + "_data",
        date_field + "_data_status",
    }
    for bad in [
        replace(context, release="prelim"),
        replace(context, source_sha256="f" * 64),
        replace(context, scope=sus.ScopeKey("AP", year, month)),
    ]:
        assert not sus.analytical_projection(
            dataset, observed_schema=schema, scopes=[context, bad]
        ).columns


@pytest.mark.parametrize(
    ("dataset", "fixture", "year"),
    [
        ("sinan_chagas", "sinan_chagas_br_2023", 2023),
        ("sinan_hanseniase", "sinan_hanseniase_br_2026", 2026),
        ("sinan_tuberculose", "sinan_tuberculose_br_2020_excerpt", 2020),
    ],
)
def test_sinan_age_is_enabled_only_for_the_audited_file(dataset, fixture, year):
    """The audited identity is the full server file: FIXTURES.md `source_sha256` (for a
    whole fixture it is also the fixture's own digest; for an excerpt it is not)."""
    from tests.unit.test_fixture_provenance import load_fixture_rows

    (row,) = [r for r in load_fixture_rows() if r["file"] == f"dbc/{fixture}.dbc"]
    sha = row["source_sha256"]
    context = sus.SourceContext(sus.ScopeKey(uf=None, ano=year), "prelim", sha)
    schema = {"NU_IDADE_N": "BIGINT"}
    projection = sus.analytical_projection(dataset, observed_schema=schema, scopes=[context])
    assert [c.name for c in projection.columns] == [
        "idade_anos_completos",
        "idade_status",
        "idade_quantidade",
        "idade_unidade",
    ]
    for bad in [
        replace(context, source_sha256="0" * 64),
        replace(context, release="final"),
        replace(context, scope=sus.ScopeKey(uf=None, ano=year - 1)),
    ]:
        for scopes in [[bad], [context, bad]]:
            assert not sus.analytical_projection(
                dataset, observed_schema=schema, scopes=scopes
            ).columns


def test_tuberculose_audited_source_matches_the_evidence_manifest():
    """The gate isn't just some hash: it's the DBC that
    evidence/2026-09-22-w6-idade-tb/manifest.json records as audited."""
    manifest = json.loads(
        (ROOT / "evidence/2026-09-22-w6-idade-tb/manifest.json").read_text("utf-8")
    )
    (entry,) = [m for m in manifest if m["dataset"] == "sinan_tuberculose"]
    (validated,) = contexts("sinan_tuberculose")
    assert validated.source_sha256 == entry["sha256"]


def test_sim_subyear_age_keeps_quantity_and_unit(dbc_fixture):
    """Real DORR2023: sub-year deaths keep their unit instead of collapsing to 0 years."""
    raw = dbc_fixture("sim_rr_2023_mini").read_bytes()
    context = sus.SourceContext(sus.ScopeKey("RR", 2023), "final", hashlib.sha256(raw).hexdigest())
    frame = dbc_bytes_to_lazyframe(raw, dataset="sim_obitos").collect()
    with duckdb.connect() as con:
        con.register("source", frame)
        schema = {row[0]: row[1] for row in con.execute("DESCRIBE source").fetchall()}
        projection = sus.analytical_projection(
            "sim_obitos", observed_schema=schema, scopes=[context]
        )
        age = [c for c in projection.columns if c.name.startswith("idade_")]
        assert [c.name for c in age] == [
            "idade_anos_completos",
            "idade_status",
            "idade_quantidade",
            "idade_unidade",
        ]
        derived = "SELECT idade, " + ", ".join(f'{c.expression} AS "{c.name}"' for c in age)
        derived += " FROM source"
        units = con.execute(
            f"""SELECT idade_unidade, min(idade_quantidade), max(idade_quantidade), count(*)
            FROM ({derived}) GROUP BY ALL ORDER BY 1 NULLS LAST"""
        ).fetchall()
        rows = con.execute(derived).fetchall()
    assert units == [
        ("day", 0, 27, 124),
        ("hour", 1, 23, 37),
        ("minute", 1, 55, 18),
        ("month", 1, 11, 134),
        ("year", 1, 106, 2997),
        (None, None, None, 1),
    ]
    rule = sus.describe_dataset("sim_obitos")["analytics"]["age"]
    for value, years, status, quantity, unit in rows:
        scalar = decode_age(rule, value)
        valid_unit = scalar.unit if scalar.status == "valid" else None
        assert (years, status, quantity, unit) == (
            scalar.years_completed,
            scalar.status,
            scalar.quantity,
            valid_unit,
        ), value


@pytest.mark.parametrize(
    ("dataset", "fixture", "uf", "year", "month"),
    [
        ("sia_bpa_individualizado", "sia_bi_rr_2022_01_mini", "RR", 2022, 1),
        ("sia_bpa_individualizado", "sia_bi_rr_2024_01_mini", "RR", 2024, 1),
        ("sia_psicossocial", "sia_ps_rr_2024_01_mini", "RR", 2024, 1),
        ("sia_atencao_domiciliar", "sia_sad_ma_2018_10_mini", "MA", 2018, 10),
    ],
)
def test_sia_age_is_enabled_only_for_the_audited_files(dataset, fixture, uf, year, month):
    """The audited identity is each whole fixture's FIXTURES.md `source_sha256`."""
    from tests.unit.test_fixture_provenance import load_fixture_rows

    (row,) = [r for r in load_fixture_rows() if r["file"] == f"dbc/{fixture}.dbc"]
    context = sus.SourceContext(sus.ScopeKey(uf, year, month), "final", row["source_sha256"])
    schema = {"TPIDADEPAC": "VARCHAR", "IDADEPAC": "VARCHAR"}
    projection = sus.analytical_projection(dataset, observed_schema=schema, scopes=[context])
    assert [c.name for c in projection.columns] == [
        "idade_anos_completos",
        "idade_status",
        "idade_quantidade",
        "idade_unidade",
    ]
    for bad in [
        replace(context, source_sha256="0" * 64),
        replace(context, release="prelim"),
        replace(context, scope=sus.ScopeKey("AP", year, month)),
    ]:
        assert not sus.analytical_projection(
            dataset, observed_schema=schema, scopes=[context, bad]
        ).columns
