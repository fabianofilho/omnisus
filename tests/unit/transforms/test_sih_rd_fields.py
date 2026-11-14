"""RD from 2008: the dictionary declares every field the layouts of real files publish (#86).

The census of `SIHSUS/200801_/Dados` (evidence/2026-10-06-rd-2008-layouts/census.csv) has
six layouts, the fifth from 2014-01 and the sixth from 2025-03, which adds FONTE_ORC. One
fixture of each of the last two: RDRR2401 and an excerpt of RDRR2503.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from scripts.gen_dicionario import fields_of

import omnisus as sus
from omnisus.sources.datasus_ftp import dbc
from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.dictionaries import load_dicionario

ROOT = Path(__file__).resolve().parents[3]
CENSUS = ROOT / "evidence/2026-10-06-rd-2008-layouts/census.csv"
DATASET = "sih_aih_reduzida"
LAYOUTS = {"sih_rr_2024_01_mini": 5, "sih_rd_rr_2025_03_excerpt": 6}


def census_layouts() -> dict[int, set[str]]:
    """Layout number -> its fields, lowercased, from the census."""
    out: dict[int, set[str]] = {}
    with CENSUS.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out.setdefault(int(row["layout"]), set()).update(
                name.lower() for name in row["fields"].split(" ")[::2]
            )
    return out


def fixture_fields(dbc_fixture, fixture: str) -> dict[str, str]:
    raw = dbc_fixture(fixture).read_bytes()
    return {f["name"]: f["type"] for f in fields_of(dbc.decompress_bytes(raw))}


def test_the_dictionary_declares_every_field_of_every_layout():
    declared = {f["name"] for f in load_dicionario(DATASET).fields}
    assert sorted(set().union(*census_layouts().values()) - declared) == []


@pytest.mark.parametrize("fixture", sorted(LAYOUTS))
def test_each_fixture_publishes_the_fields_of_its_layout(dbc_fixture, fixture):
    assert set(fixture_fields(dbc_fixture, fixture)) == census_layouts()[LAYOUTS[fixture]]


def test_fonte_orc_takes_the_labels_of_fonterem(dbc_fixture):
    """RD2008.DEF line 274 binds FONTE_ORC to CNV/fonterem.CNV at position 1. The table
    names 01-04, each also as '1' and ' 1', and opens with the literal key '  -zz' (#24);
    '00', the only value of the excerpt, is not a key, and the field's issue says so."""
    published = fixture_fields(dbc_fixture, "sih_rd_rr_2025_03_excerpt")
    field = load_dicionario(DATASET).field_def("fonte_orc")
    assert field["type"] == published["fonte_orc"]
    labels = {
        "01": "MOD.1-SERVICO DE SAUDE - AES",
        "02": "MOD.2-EQUIPE VOLANTES-AES",
        "03": "CREDITO FINANC.PARC.VENCIDAS E VICENDAS",
        "04": "CREDITO FINANCEIRO TRANSACAO TRIBUTARIA",
    }
    expected = {"  -zz": "Branco Ignorado"}
    for code, label in labels.items():
        expected |= {code: label, code[1]: label, f" {code[1]}": label}
    assert field["x-decode"] == expected
    (claim,) = field["x-metadata"]["claims"]
    assert claim["method"] == "cnv-parse"
    assert "FONTE_ORC, 1, CNV/fonterem.CNV" in claim["evidence"][0]["locator"]
    assert [i["id"] for i in field["x-metadata"]["issues"]] == ["fonte_orc-00-sem-fonte"]


def test_uf_zi_is_the_gestor_municipality(dbc_fixture):
    """RD2008.DEF lines 175-176 call UF_ZI 'Município gestor' (CNV/br_municgestor.cnv),
    and RDRR2401 publishes it with 6 digits, the width of a municipality code; the
    dictionary called it "UF do gestor" (#155)."""
    def_lines = (
        (ROOT / "src/omnisus/data/dicionarios/sources/cnv/sih/RD2008.DEF")
        .read_text(encoding="latin-1")
        .splitlines()
    )
    assert [line.split(",")[0][1:].strip() for line in def_lines[174:176]] == [
        "Município gestor",
        "Município gestor",
    ]
    raw = dbc_fixture("sih_rr_2024_01_mini").read_bytes()
    values = dbc_bytes_to_lazyframe(raw, dataset=DATASET).collect()["uf_zi"]
    assert values.str.contains(r"^\d{6}$").all()
    assert load_dicionario(DATASET).field_def("uf_zi")["label"] == "Município gestor"


COD_IDADE = {"2": "Dias", "3": "Meses", "4": "Anos", "5": "Anos (somar 100)"}


@pytest.mark.parametrize(
    ("dataset", "fixture", "def_member", "def_lines", "published"),
    [
        (
            "sih_aih_reduzida",
            "sih_rr_2024_01_mini",
            "RD2008.DEF",
            range(188, 192),
            {"2": 157, "3": 175, "4": 3378, "5": 4},
        ),
        (
            "sih_aih_rejeitada",
            "sih_rj_rr_2024_01_mini",
            "RJ2008.DEF",
            range(193, 197),
            {"2": 4, "3": 4, "4": 22},
        ),
    ],
)
def test_cod_idade_labels_the_measured_units(
    dbc_fixture, dataset, fixture, def_member, def_lines, published
):
    """#6: the RD and RJ DEF bind COD_IDADE to IDADEBAS, IDADEPUB, IDADE18 and IDADEDET.CNV,
    which read 3 characters (unit + age); IDADEDET has 2xx days, 3xx months, 4xx years,
    500-530 "100 anos" to "130 anos" and 000 "Idade inválida". The 1-character unit is
    measured, not read: '5' is a year to add to 100, and '0' gets no label (no source says
    "Ignorada"; no SIH fixture publishes '0', so that part is checked on the dictionary).
    The RJ had no map and takes the same one."""
    text = (ROOT / "src/omnisus/data/dicionarios/sources/cnv/sih" / def_member).read_text(
        encoding="latin-1"
    )
    bound = [text.splitlines()[n - 1].split(",") for n in def_lines]
    assert [(f.strip(), t.strip()) for _, f, _, t in bound] == [
        ("COD_IDADE", f"CNV\\{cnv}.CNV") for cnv in ("IDADEBAS", "IDADEPUB", "IDADE18", "IDADEDET")
    ]
    raw = dbc_fixture(fixture).read_bytes()
    frame = dbc_bytes_to_lazyframe(raw, dataset=dataset).collect().select("cod_idade")
    assert dict(frame["cod_idade"].value_counts().rows()) == published
    labelled = sus.label(dataset, frame, columns=["cod_idade"])
    assert dict(labelled.unique().rows()) == {code: COD_IDADE[code] for code in published}
    field = load_dicionario(dataset).field_def("cod_idade")
    assert field["x-decode"] == COD_IDADE
    (claim,) = field["x-metadata"]["claims"]
    assert (claim["target"], claim["status"]) == ("/field/codes", "unreviewed")
    assert "sih-tab-714ed980d483" in {e["source_id"] for e in claim["evidence"]}
    (entry,) = field["x-metadata"]["issues"]
    assert (entry["id"], entry["status"]) == ("cod_idade-sem-tabela", "open")
    assert all(s in entry["description"] for s in ("IDADEDET.CNV", "IDADEBAS.CNV", "'0'"))
