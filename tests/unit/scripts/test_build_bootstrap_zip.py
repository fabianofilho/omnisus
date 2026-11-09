"""The pure parts of scripts/build_bootstrap_zip.py, on the SIGTAP and base files the
build reads (tests/fixtures/FIXTURES.md); the build itself needs the DATASUS server."""

from __future__ import annotations

import io
import zipfile
from importlib.resources import files
from pathlib import Path

import polars as pl
import pytest
from scripts.build_bootstrap_zip import (
    _from_territorial,
    aux_cid10,
    aux_municipios,
    parse_tb_cid,
    sigtap_cid10,
)

SIGTAP = Path(__file__).resolve().parents[2] / "fixtures" / "sigtap"
# tb_cid.txt codes that CID10.DBF (2020) lacks: the 9 of the first review, plus A925, A97,
# C823 to C826 and W460 to W469.
MISSING = [
    "A925", "A97", "C823", "C824", "C825", "C826", "N182", "N183", "N184", "N185", "P354",
    "U09", "U099", "U10", "U109", *[f"W46{n}" for n in range(10)],
]  # fmt: skip


# Records of tb_municip.dbf in 06-base_territorial_jun26.zip (SHA-256 f6e06a67...316a;
# tb_municip.dbf SHA-256 a99e4594fcfa824212536b589cf6ebe2adec9a9f3c18047b88fb836a6fce20f3,
# 5725 records), as dbfread2 reads them with cp1252, unchanged. Transcribed, not committed
# as a file: the DBF is 1.2 MB.
PINTO_BANDEIRA = {
    "CO_MUNICIP": "431454", "CO_MUNICDV": "4314548", "CO_STATUS": "ATIVO", "CO_TIPO": "ATIVO",
    "DS_NOME": "Pinto Bandeira", "UF": "RS", "MACRORREGI": "4310",
    "DS_NOMEPAD": "PINTO BANDEIRA", "DS_OBSERV": "S", "CO_REGIAO": "4", "CO_UF": "43",
    "CO_ALTER": "", "CO_ALTERDV": "", "IN_CAPITAL": "N", "IN_AMAZLEG": "N", "IN_SEMIAR": "",
    "IN_FRONTZN": "N", "DT_INSTAL": "2013", "DT_EXTIN": "", "CO_SUCESS": "", "NU_ORDEM": "",
    "NU_ORDMAP": "", "NU_LATITUD": "-29,09777778", "NU_LONGIT": "-51,45027778",
    "NU_ALTITUD": "638", "NU_AREA": "104,821",
}  # fmt: skip
# Nazária, all 26 fields as dbfread2 reads them from the same tb_municip.dbf, unchanged;
# nothing is inherited from Pinto Bandeira.
NAZARIA = {
    "CO_MUNICIP": "220672", "CO_MUNICDV": "2206720", "CO_STATUS": "ATIVO", "CO_TIPO": "ATIVO",
    "DS_NOME": "Nazaria", "UF": "PI", "MACRORREGI": "2208", "DS_NOMEPAD": "NAZARIA",
    "DS_OBSERV": "S", "CO_REGIAO": "2", "CO_UF": "22", "CO_ALTER": "", "CO_ALTERDV": "",
    "IN_CAPITAL": "N", "IN_AMAZLEG": "N", "IN_SEMIAR": "", "IN_FRONTZN": "N",
    "DT_INSTAL": "2009", "DT_EXTIN": "", "CO_SUCESS": "", "NU_ORDEM": "", "NU_ORDMAP": "",
    "NU_LATITUD": "-5,346925", "NU_LONGIT": "-42,8140484695768", "NU_ALTITUD": "72",
    "NU_AREA": "",
}  # fmt: skip
# CO_STATUS of the 5725 records: ATIVO 5571, REG ADM 63, TRANS 60, IGNR 27, EXTIN 2,
# IGNOR 2 (evidence/2026-10-31-tb-municip-co-status/). The build takes only the enum of
# aux_municipios.yaml, CADMUN's four.
SITUACAO = ["ATIVO", "EXTIN", "IGNOR", "TRANS"]


def tb_cid_files() -> tuple[list[str], list[str]]:
    layout = (SIGTAP / "tb_cid_layout_202610.txt").read_text(encoding="latin-1").splitlines()
    lines = (SIGTAP / "tb_cid_202610.txt").read_text(encoding="latin-1").splitlines()
    return layout, lines


def packaged_codes() -> set[str]:
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return set(pl.read_parquet(zf.read("aux_cid10.parquet"))["codigo"])


def test_tb_cid_is_read_with_its_layout() -> None:
    codes = parse_tb_cid(*tb_cid_files())
    assert len(codes) == 14246
    assert codes["N185"] == "Doença renal crônica, estádio 5"
    assert codes["A97"] == "Dengue (AGRAVO DE NOTIFICAÇÃO COMPULSÓRIA)"


def test_a_changed_tb_cid_layout_stops_the_build() -> None:
    """Synthetic layout: the malformed-input case of AGENTS.md rule 2."""
    layout, lines = tb_cid_files()
    layout[2] = "NO_CID,90,5,94,VARCHAR2"
    with pytest.raises(SystemExit, match=r"tb_cid_layout\.txt changed"):
        parse_tb_cid(layout, lines)


def test_sigtap_cid10_is_every_code_the_dbf_lacks() -> None:
    layout, lines = tb_cid_files()
    have = packaged_codes() - set(MISSING)
    found = sigtap_cid10(layout, lines, have)
    assert [c for c, _ in found] == MISSING
    assert dict(found)["W469"] == "Contato com agulha hipodérmica - local não especificado"
    assert sigtap_cid10(layout, lines, packaged_codes()) == []


def test_cid10_dbf_description_must_repeat_its_code() -> None:
    """Synthetic row: the malformed-input case of AGENTS.md rule 2."""
    with pytest.raises(SystemExit, match="A00: DESCR does not start with its code"):
        aux_cid10([{"CID10": "A00", "DESCR": "B00 Colera"}], [], [], [])


def test_a_territorial_record_takes_cadmuns_columns() -> None:
    assert _from_territorial(PINTO_BANDEIRA) == {
        "MUNCODDV": "4314548",
        "MUNCOD": "431454",
        "MUNNOME": "Pinto Bandeira",
        "UFCOD": "43",
        "SITUACAO": "ATIVO",
        "ANOINST": "2013",
        "ANOEXT": "",
        "SUCESSOR": "",
        "LATITUDE": -29.09777778,
        "LONGITUDE": -51.45027778,
        "ALTITUDE": 638,
        "AREA": 104.821,
        "RSAUDCOD": None,
        "MSAUDCOD": None,
    }


def test_a_territorial_record_without_area_has_none() -> None:
    nazaria = _from_territorial(NAZARIA)
    assert (nazaria["ANOINST"], nazaria["ALTITUDE"], nazaria["AREA"]) == ("2009", 72, None)


@pytest.mark.parametrize("status", SITUACAO)
def test_every_status_the_dictionary_accepts_is_accepted(status: str) -> None:
    assert _from_territorial({**PINTO_BANDEIRA, "CO_STATUS": status})["SITUACAO"] == status


@pytest.mark.parametrize("status", ["REG ADM", "IGNR", "EM INSTALACAO"])
def test_a_status_outside_the_dictionary_stops_the_build(status: str) -> None:
    """The real record with CO_STATUS changed: the malformed-input case of AGENTS.md rule 2.
    REG ADM and IGNR are in the base but not in the dictionary's enum."""
    with pytest.raises(SystemExit, match=f"CO_STATUS '{status}'"):
        _from_territorial({**PINTO_BANDEIRA, "CO_STATUS": status})


def test_a_decimal_altitude_stops_the_build() -> None:
    """The real record with NU_ALTITUD changed: the malformed-input case of AGENTS.md rule 2.
    The six altitudes are whole; a decimal one would be truncated by int()."""
    with pytest.raises(SystemExit, match="NU_ALTITUD '638,5'"):
        _from_territorial({**PINTO_BANDEIRA, "NU_ALTITUD": "638,5"})


def test_aux_municipios_appends_the_territorial_records() -> None:
    frame = aux_municipios([], [PINTO_BANDEIRA, NAZARIA])
    assert frame.select("codigo_6", "nome", "ano_instalacao", "area").rows() == [
        ("431454", "Pinto Bandeira", 2013, 104.821),
        ("220672", "Nazaria", 2009, None),
    ]


def test_a_territorial_code_cadmun_already_has_stops_the_build() -> None:
    """CADMUN with Pinto Bandeira, built from the real record: the clash the build refuses."""
    with pytest.raises(SystemExit, match=r"CADMUN already has \['431454'\]"):
        aux_municipios([_from_territorial(PINTO_BANDEIRA)], [PINTO_BANDEIRA])
