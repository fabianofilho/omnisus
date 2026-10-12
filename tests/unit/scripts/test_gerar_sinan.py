"""The SINAN dictionaries are gerar_sinan.py's output, and every code cites a source."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from omnisus.metadata import describe_dataset
from omnisus.sources.datasus_ftp.dbc import decompress_bytes

ROOT = Path(__file__).resolve().parents[3]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"
FIXTURES = ROOT / "tests/fixtures/dbc"
TYPES = {"C": "string", "D": "date", "N": "integer"}


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = ROOT / "scripts" / "metadados" / "gerar_sinan.py"
    spec = importlib.util.spec_from_file_location("gerar_sinan", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "gerar_sinan", module)
    spec.loader.exec_module(module)
    return module


def _bloco() -> dict:
    return yaml.load(
        (ROOT / "scripts/metadados/sinan_bloco_comum.yaml").read_text("utf-8"),
        Loader=yaml.CSafeLoader,
    )


def _membros(gerar: ModuleType) -> dict:
    return json.loads((gerar.CNV / "vinculos.json").read_text("utf-8"))["membros"]


def _entry(section: list[dict], name: str) -> dict:
    return copy.deepcopy(next(e for e in section if e["name"] == name))


def test_generator_output_is_committed(monkeypatch):
    """Idempotent: generating again from the block changes no byte."""
    for path, text in _load(monkeypatch).generate().items():
        assert path.read_text(encoding="utf-8") == text, path.name


@pytest.mark.parametrize(
    ("dataset", "fixture"),
    [
        ("sinan_chagas", "sinan_chagas_br_2023"),
        ("sinan_hanseniase", "sinan_hanseniase_br_2026"),
        ("sinan_tuberculose", "sinan_tuberculose_br_2020_excerpt"),
    ],
)
def test_declared_types_follow_the_real_dbf_descriptor(dataset, fixture):
    """C -> string, D -> date, N -> integer, read from the fixture's own header.

    CHAGBR23 declares DT_TRANSRM as D 8 (all blank in that file); the dictionary
    called it string while hanseníase called it date."""
    dbf = decompress_bytes((FIXTURES / f"{fixture}.dbc").read_bytes())
    header = int.from_bytes(dbf[8:10], "little")
    physical = {}
    for offset in range(32, header - 1, 32):
        if dbf[offset] == 0x0D:
            break
        name = dbf[offset : offset + 11].split(b"\0")[0].decode("latin-1").lower()
        physical[name] = TYPES[chr(dbf[offset + 11])]
    doc = yaml.load((DICIONARIOS / f"{dataset}.yaml").read_text("utf-8"), Loader=yaml.CSafeLoader)
    declared = {f["name"]: f["type"] for f in doc["schema"]["fields"]}
    assert declared == physical


@pytest.mark.parametrize(
    ("dataset", "blank"),
    [
        ("sinan_chagas", {"nduplic_n"}),
        (
            "sinan_hanseniase",
            {"nduplic_n", "in_vincula", "tpalta_n", "avalia_n", "aval_atu_n", "epis_racio"},
        ),
        ("sinan_tuberculose", {"nduplic_n", "in_vincula"}),
    ],
)
def test_nine_is_ignored_and_blank_is_a_code_only_where_a_source_names_it(dataset, blank):
    """9 = Ignorado stays distinct from blank; both spellings 9 and 09 are listed.

    Blank is a key only where a page says "0 ou branco" (nduplic_n, in_vincula) or a CNV
    lists the blank code (hanseníase tpalta_n, avalia_n, aval_atu_n, epis_racio)."""
    fields = {f["field"]["name"]: f["field"] for f in describe_dataset(dataset)["fields"]}
    escol = {c["value"]: c["missing_kind"] for c in fields["cs_escol_n"]["codes"]}
    assert escol["9"] == escol["09"] == "ignored"
    with_blank = {n for n, f in fields.items() if "" in {c["value"] for c in f["codes"]}}
    assert with_blank == blank


def test_tuberculose_keeps_the_raw_doenca_tra():
    """The full TUBEBR20 holds 0-6 in DOENCA_TRA (7 records with 6), a pre-5.0 field
    (TuberculNET5_0.def) that the 2020 TB dictionary does not list: the agravo entry
    replaces the common 1/2/9 map."""
    fields = {
        f["field"]["name"]: f["field"] for f in describe_dataset("sinan_tuberculose")["fields"]
    }
    assert fields["doenca_tra"]["codes"] == []
    assert fields["doenca_tra"]["description"] == (
        "Doença relacionada ao trabalho: no TUBEBR20 o campo traz 0 a 6 (7 registros com "
        "6), mas nenhuma página do dicionário de tuberculose de 2020 o lista, por isso "
        "fica sem decodificação."
    )
    chagas = {f["field"]["name"]: f["field"] for f in describe_dataset("sinan_chagas")["fields"]}
    assert [c["value"] for c in chagas["doenca_tra"]["codes"]] == ["1", "2", "9"]


def test_a_code_no_source_cites_is_refused(monkeypatch):
    gerar = _load(monkeypatch)
    entry = _entry(_bloco()["comum"], "cs_raca")
    entry["x-decode"]["0"] = "Ign/Branco"
    with pytest.raises(ValueError, match=r"x\.cs_raca: codes without a source \['0'\]"):
        gerar.definition_for(entry, "x.cs_raca", "2026-09-22", _membros(gerar))


def test_a_code_the_cited_cnv_does_not_list_is_refused(monkeypatch):
    gerar = _load(monkeypatch)
    entry = _entry(_bloco()["comum"], "cs_escol_n")
    entry["x-decode"]["A"] = "Analfabeto"
    entry["fontes"][1]["codigos"].append("A")
    with pytest.raises(ValueError, match=r"sinan/Escolarnet\.cnv does not list \['A'\]"):
        gerar.definition_for(entry, "x.cs_escol_n", "2026-09-22", _membros(gerar))


def test_a_block_field_also_bound_in_vinculos_is_refused(monkeypatch, tmp_path):
    """The block and gerar_decode_cnv.py never write the same field."""
    gerar = _load(monkeypatch)
    cnv = tmp_path / "cnv"
    shutil.copytree(gerar.CNV, cnv)
    vinculos = json.loads((cnv / "vinculos.json").read_text("utf-8"))
    vinculos["datasets"]["sinan_hanseniase"]["campos"]["migrado_w"] = "sinan/SAIDAhans.cnv"
    (cnv / "vinculos.json").write_text(json.dumps(vinculos), encoding="utf-8")
    monkeypatch.setattr(gerar, "CNV", cnv)
    with pytest.raises(ValueError, match=r"sinan_hanseniase\.migrado_w: in the block and in"):
        gerar.generate()


def test_chagas_classification_cites_the_agravo_dictionary_and_anexo_i():
    """1 and 2 from Chagas v5 p. 10; 8 only from the draft Anexo I (NI v5 p. 18)."""
    field = next(
        f for f in describe_dataset("sinan_chagas")["fields"] if f["field"]["name"] == "classi_fin"
    )
    assert {c["value"]: c["label"] for c in field["field"]["codes"]} == {
        "1": "confirmado",
        "2": "descartado",
        "8": "Inconclusivo",
    }
    (claim,) = [c for c in field["claims"] if c["target"] == "/field/codes"]
    assert claim["status"] == "verified_in_source"
    assert [(e["source_id"], e["pages"]) for e in claim["evidence"]] == [
        ("sinan-16c598f86fbf", [10]),
        ("sinan-b3e0561c7a2d", [18]),
    ]
    assert 'O código 8 vem do Anexo I, marcado "Falta concluir revisão" (p. 17).' in claim["note"]


def test_a_page_map_whose_entry_left_the_block_is_refused(monkeypatch, tmp_path):
    """Deleting an entry must not leave its generated map behind unnoticed."""
    gerar = _load(monkeypatch)
    bloco = _bloco()
    bloco["agravo"]["sinan_chagas"] = [
        e for e in bloco["agravo"]["sinan_chagas"] if e["name"] != "criterio"
    ]
    path = tmp_path / "bloco.yaml"
    path.write_text(yaml.safe_dump(bloco, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(gerar, "BLOCO", path)
    with pytest.raises(ValueError, match=r"sinan_chagas\.criterio: page-read claim without"):
        gerar.generate()


def test_a_common_entry_no_sinan_dictionary_has_is_refused(monkeypatch, tmp_path):
    """A typo in `comum` must not be skipped silently (every SINAN dictionary lacks it)."""
    gerar = _load(monkeypatch)
    bloco = _bloco()
    bloco["comum"].append(_entry(bloco["comum"], "cs_sexo") | {"name": "cs_sexx"})
    path = tmp_path / "bloco.yaml"
    path.write_text(yaml.safe_dump(bloco, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(gerar, "BLOCO", path)
    with pytest.raises(ValueError, match=r"comum names no SINAN field: \['cs_sexx'\]"):
        gerar.generate()


def test_an_agravo_entry_its_dictionary_lacks_is_refused(monkeypatch, tmp_path):
    """`agravo` entries belong to one dictionary: a name it lacks is a typo, never skipped."""
    gerar = _load(monkeypatch)
    bloco = _bloco()
    section = bloco["agravo"]["sinan_chagas"]
    section.append(_entry(section, "criterio") | {"name": "new_typo"})
    path = tmp_path / "bloco.yaml"
    path.write_text(yaml.safe_dump(bloco, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(gerar, "BLOCO", path)
    with pytest.raises(ValueError, match=r"sinan_chagas: agravo names no field \['new_typo'\]"):
        gerar.generate()


def test_a_cnv_field_moved_into_the_block_is_refused(monkeypatch, tmp_path):
    """Leaving `campos` and entering the block must not overwrite the cnv-parse claim
    unnoticed; the other direction already stops (pendência 3 do estado do programa)."""
    gerar = _load(monkeypatch)
    cnv = tmp_path / "cnv"
    shutil.copytree(gerar.CNV, cnv)
    vinculos = json.loads((cnv / "vinculos.json").read_text("utf-8"))
    del vinculos["datasets"]["sinan_hanseniase"]["campos"]["tpalta_n"]
    (cnv / "vinculos.json").write_text(json.dumps(vinculos), encoding="utf-8")
    monkeypatch.setattr(gerar, "CNV", cnv)
    bloco = _bloco()
    bloco["agravo"].setdefault("sinan_hanseniase", []).append(
        _entry(bloco["comum"], "cs_sexo") | {"name": "tpalta_n"}
    )
    path = tmp_path / "bloco.yaml"
    path.write_text(yaml.safe_dump(bloco, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(gerar, "BLOCO", path)
    with pytest.raises(ValueError, match=r"sinan_hanseniase\.tpalta_n: cnv-parse claim"):
        gerar.generate()
