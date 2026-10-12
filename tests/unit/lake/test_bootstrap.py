"""Tests for Lake.bootstrap_auxiliares over the packaged zip.

The zip is built by ``scripts/build_bootstrap_zip.py`` from the hashed DATASUS files in
``SIM/CID10/TABELAS`` and ``CBO2002.CNV``; its ``manifest.json`` names each digest.
"""

from __future__ import annotations

import io
import json
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest

from omnisus.lake import Lake
from omnisus.metadata import sources_registry

TABLES = {"aux_uf", "aux_municipios", "aux_cid10", "aux_ocupacoes", "aux_paises"}


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory):
    path = tmp_path_factory.mktemp("bootstrap")
    lake = Lake.local(f"ducklake:{path}/x.ducklake")
    lake.bootstrap_auxiliares()
    yield lake
    lake.close()


def one(lake: Lake, sql: str, *args: object) -> tuple:
    row = lake.connect().execute(sql, list(args)).fetchone()
    assert row is not None, sql
    return row


def test_bootstrap_loads_the_five_vocabularies(lake: Lake) -> None:
    assert set(lake.tables()) >= TABLES
    counts = {t: one(lake, f"SELECT count(*) FROM lake.{t}")[0] for t in sorted(TABLES)}
    assert counts == {
        "aux_cid10": 14257,
        "aux_municipios": 5652,
        "aux_ocupacoes": 2458 + 3564,
        "aux_paises": 264,
        "aux_uf": 27,
    }


def test_municipalities_carry_coordinates_and_successors(lake: Lake) -> None:
    assert one(
        lake,
        "SELECT codigo_6, nome, uf_codigo, latitude, longitude, altitude, area, "
        "regiao_saude, situacao FROM lake.aux_municipios WHERE codigo_ibge = '1100205'",
    ) == ("110020", "Porto Velho", "11", -8.762, -63.904, 85, 34082.366, "1104", "ATIVO")
    assert one(
        lake,
        "SELECT situacao, ano_extincao, sucessor FROM lake.aux_municipios "
        "WHERE codigo_ibge = '4314530'",
    ) == ("EXTIN", 2002, "4302105")
    # 0°, 0° lies in the Atlantic: the rows CADMUN fills with zeros carry NULL.
    assert lake.connect().execute(
        "SELECT situacao, count(*) FROM lake.aux_municipios WHERE latitude IS NULL "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall() == [("ATIVO", 4), ("IGNOR", 27), ("TRANS", 60)]


def test_cid10_is_complete_with_chapters(lake: Lake) -> None:
    assert one(lake, "SELECT descricao, capitulo FROM lake.aux_cid10 WHERE codigo = 'B571'") == (
        "Form aguda doenc de Chagas s/compr cardiaco",
        1,
    )
    assert one(lake, "SELECT descricao FROM lake.aux_cid10 WHERE codigo = 'G904'") == (
        "Disreflexia autonômica",
    )
    assert one(lake, "SELECT count(DISTINCT capitulo) FROM lake.aux_cid10") == (22,)


def test_cid10_blocks_come_from_the_tabwin_groups(lake: Lake) -> None:
    """Blocks of CID10-grup_d.cnv (OBITOS_CID10_TAB.zip), the grouping the SIM DEF binds
    to CAUSABAS; comparison with the WHO and CBCD lists in evidence/2026-10-11-blocos-cid10."""
    assert one(
        lake, "SELECT bloco, bloco_descricao FROM lake.aux_cid10 WHERE codigo = 'B571'"
    ) == ("B50-B64", "Doencas devidas a protozoários")
    # A range may cross letters: TabWin compares the first three characters.
    assert one(lake, "SELECT bloco, capitulo FROM lake.aux_cid10 WHERE codigo = 'Y05'") == (
        "X85-Y09",
        20,
    )
    # Every block lies in one chapter, and 241 of the 243 blocks hold a code
    # (U92-U92 and U99-U99 hold none in CID10.DBF).
    assert (
        lake.connect()
        .execute(
            "SELECT bloco FROM lake.aux_cid10 WHERE bloco IS NOT NULL "
            "GROUP BY bloco HAVING count(DISTINCT capitulo) > 1"
        )
        .fetchall()
        == []
    )
    assert one(lake, "SELECT count(DISTINCT bloco) FROM lake.aux_cid10") == (241,)
    # O93, a Brazilian extension, is in no group: the CNV goes from O85-O92 to O94-O99.
    assert lake.connect().execute(
        "SELECT codigo FROM lake.aux_cid10 WHERE bloco IS NULL ORDER BY codigo"
    ).fetchall() == [("O93",)] + [(f"O93{n}",) for n in range(10)]
    assert one(
        lake,
        "SELECT count(*) FROM lake.aux_cid10 WHERE (bloco IS NULL) <> (bloco_descricao IS NULL)",
    ) == (0,)


def test_occupations_keep_both_schemes(lake: Lake) -> None:
    assert one(
        lake,
        "SELECT count(*), count(DISTINCT codigo) FROM lake.aux_ocupacoes "
        "WHERE esquema = 'cbo2002'",
    ) == (2458, 2458)
    assert one(
        lake,
        "SELECT descricao FROM lake.aux_ocupacoes WHERE esquema = 'cbo2002' AND codigo = '10105'",
    ) == ("Oficial General da Aeronáutica",)
    # TABOCUP lists several titles per code: a title index, not a join key.
    assert one(
        lake,
        "SELECT count(*), count(DISTINCT codigo) FROM lake.aux_ocupacoes "
        "WHERE esquema = 'tabocup'",
    ) == (3564, 383)
    assert one(
        lake,
        "SELECT descricao FROM lake.aux_ocupacoes WHERE esquema = 'tabocup' "
        "AND descricao LIKE 'COLOCADOR DE LI%'",
    ) == ("COLOCADOR DE LIÇOS",)


def test_uf_and_countries_come_from_the_dbf_verbatim(lake: Lake) -> None:
    assert one(lake, "SELECT sigla, nome FROM lake.aux_uf WHERE codigo_ibge = '11'") == (
        "RO",
        "RONDONIA",
    )
    assert one(lake, "SELECT count(*) FROM lake.aux_paises WHERE codigo = '044'") == (2,)


def test_manifest_names_registered_sources() -> None:
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        parquet = {n.removesuffix(".parquet") for n in zf.namelist() if n.endswith(".parquet")}
    assert set(manifest) == parquet == TABLES
    registry = {s["sha256"]: s for s in sources_registry()["sources"]}
    for table, entry in manifest.items():
        for source in entry["sources"]:
            assert registry[source["sha256"]]["url"] == source["url"], table


def test_bootstrap_idempotent(tmp_path: Path) -> None:
    lake = Lake.local(f"ducklake:{tmp_path}/x.ducklake")
    lake.bootstrap_auxiliares()
    lake.bootstrap_auxiliares()
    n = lake.connect().execute("SELECT count(*) FROM lake.aux_uf").fetchone()[0]
    assert n == 27
    lake.close()
