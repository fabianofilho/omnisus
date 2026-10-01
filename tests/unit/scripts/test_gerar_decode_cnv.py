"""The committed dictionaries are the generator's output; no CNV-bound hand map survives."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from omnisus.transforms.cnv import parse_def

ROOT = Path(__file__).resolve().parents[3]
CNV = ROOT / "src/omnisus/data/dicionarios/sources/cnv"


def _load(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    script = ROOT / "scripts" / "metadados" / "gerar_decode_cnv.py"
    spec = importlib.util.spec_from_file_location("gerar_decode_cnv", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "gerar_decode_cnv", module)
    spec.loader.exec_module(module)
    return module


def test_generator_output_is_committed(monkeypatch):
    """Idempotent: generating again from the packaged members changes no byte."""
    for path, text in _load(monkeypatch).generate().items():
        assert path.read_text(encoding="utf-8") == text, path.name


def test_every_hand_map_a_def_binds_is_generated_or_excused(monkeypatch):
    """A hand x-decode survives only where no CNV binds the field (or sem_cnv says why).

    A binding whose start column is unknown (``start=None``: RD2008.DEF ``FAEC_TP``,
    ``PROC_REA``) counts as binding the field, so a hand map on such a field must be
    listed in ``campos`` or ``sem_cnv`` too; it cannot pass unnoticed.
    """
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    for dataset, spec in vinculos["datasets"].items():
        bound = {
            b.field.lower()
            for def_path in gerar.def_paths(spec)
            for b in parse_def(gerar.read_def(def_path, vinculos))
            if b.start in (1, None)
        }
        doc = yaml.safe_load(
            (ROOT / "src/omnisus/data/dicionarios" / f"{dataset}.yaml").read_text("utf-8")
        )
        hand = {f["name"] for f in doc["schema"]["fields"] if f.get("x-decode")} & bound
        listed = set(spec["campos"]) | set(spec.get("sem_cnv", {}))
        assert hand <= listed, (dataset, sorted(hand - listed))
        assert set(spec.get("sem_cnv", {})) <= bound, dataset


def test_the_listed_out_of_layout_def_lines_are_the_only_ones_dropped(monkeypatch):
    """APAC_Quimioterapia.DEF line 343, Servico_Especializado_200803_.def lines 56 and 81
    and APAC_Radioterapia.DEF line 330 lack the comma between description and field. Each
    raw member fails on its first listed line; with the listed exclusions it parses."""
    from omnisus.transforms.cnv import CnvFormatError

    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    entries = vinculos["linhas_fora_do_layout"]
    assert [(e["membro"], e["linha"]) for e in entries] == [
        ("sia/APAC_Quimioterapia.DEF", 343),
        ("cnes/Servico_Especializado_200803_.def", 56),
        ("cnes/Servico_Especializado_200803_.def", 81),
        ("sia/APAC_Radioterapia.DEF", 330),
    ]
    firsts = [(e["membro"], e["linha"]) for e in entries if e["linha"] != 81]
    for member, first in firsts:
        raw = (CNV / member).read_bytes().decode("latin-1")
        with pytest.raises(CnvFormatError, match=f"DEF line {first} "):
            parse_def(raw)
        parse_def(gerar.read_def(member, vinculos))
    entry = entries[0]
    bindings = parse_def(gerar.read_def(entry["membro"], vinculos))
    assert [
        (b.kind, b.start)
        for b in bindings
        if (b.field, b.table) == ("AP_UFMUN", "CNV/BR_MICIBGE.CNV")
    ] == [("L", 1), ("C", 1)]


def test_a_listed_def_line_whose_text_differs_from_the_member_is_refused(monkeypatch):
    """The exclusion names the exact text of line 343; if the member no longer has that
    text there, the generator refuses instead of blanking whatever line is now 343."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    entry = vinculos["linhas_fora_do_layout"][0]
    entry["texto"] = entry["texto"].replace("AP_UFMUN        ,", "AP_UFMUN,")
    with pytest.raises(ValueError, match=r"APAC_Quimioterapia\.DEF line 343 is 'SMicro IBGE"):
        gerar.read_def(entry["membro"], vinculos)


def test_a_binding_with_unknown_start_is_refused_not_generated(monkeypatch):
    """RD2008.DEF binds FAEC_TP to TP_FINAN.CNV with 'DS_TPFIN' where the start column
    goes (TabWin.pdf pp. 87-88 documents no such form). The generator never writes a
    map from such a binding: it names the reason instead of reporting a missing line."""
    gerar = _load(monkeypatch)
    text = (CNV / "sih/RD2008.DEF").read_bytes().decode("latin-1")
    assert {b.field for b in parse_def(text) if b.start is None} == {"FAEC_TP", "PROC_REA"}
    with pytest.raises(ValueError, match="unknown start column"):
        gerar.binding_for("sih/RD2008.DEF", text, "faec_tp", "sih/CNV/TP_FINAN.CNV")


@pytest.mark.parametrize(
    ("field", "member", "labels"),
    [
        ("complex", "sih/CNV/COMPLEX2.CNV", {"01": "Atenção Básica", "05": "Não se aplica"}),
        ("ident", "sih/CNV/IDENT.CNV", {"1": "Normal", "3": "Outras/ignorado"}),
        ("instru", "sih/CNV/INSTRU.CNV", {"1": "Analfabeto", "0": "Ignorado/não se aplica"}),
        ("natureza", "sih/CNV/NATUREZA.CNV", {"10": "Próprio", "00": "Ignorado"}),
        ("raca_cor", "sih/CNV/RACACOR.CNV", {"01": "Branca", "99": "Sem informação"}),
        ("sexo", "sih/CNV/SEXO.CNV", {"3": "Feminino", "9": "Ignorado"}),
        ("vincprev", "sih/CNV/VINCPREV.CNV", {"1": "Autônomo", "0": "Não classificado"}),
    ],
)
def test_sih_fields_with_a_fallback_range_take_the_cnv_map(field, member, labels):
    """ManualTabnet.pdf p. 21: a code listed again takes the later line. These CNVs open
    with a fallback range, so they left `sem_cnv` for `campos`."""
    from omnisus.transforms.cnv import cnv_map, parse_cnv
    from omnisus.transforms.dictionaries import load_dicionario

    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    sih = vinculos["datasets"]["sih_aih_reduzida"]
    assert sih["campos"][field] == member
    assert field not in sih["sem_cnv"]
    decode = load_dicionario("sih_aih_reduzida").field_def(field)["x-decode"]
    assert decode == cnv_map(parse_cnv((CNV / member).read_bytes().decode("latin-1")))
    assert {code: decode[code] for code in labels} == labels


def test_rd_cnv_maps_are_verified_and_the_hand_maps_they_replaced_resolved():
    """RD's hand maps had no source, so the TAB_SIH CNV settles them: every RD cnv-parse
    claim is verified, and each issue cnv-difere-do-mapa-anterior is resolved with the old
    labels kept in its text. A field RJ2008.DEF binds to the same CNV has the same map in
    RJ, where no hand map ever existed and the claim was verified from the start."""
    from omnisus.transforms.dictionaries import load_dicionario

    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    rd = vinculos["datasets"]["sih_aih_reduzida"]["campos"]
    rj = vinculos["datasets"]["sih_aih_rejeitada"]["campos"]
    shared = {f for f in rd if rj.get(f) == rd[f]}
    # RJ has no tpdisec fields (RJ2008.DEF binds none to TP_DIAGSEC.CNV).
    assert set(rd) - shared == {"marca_uci", *(f"tpdisec{n}" for n in range(1, 10))}
    for name in rd:
        field = load_dicionario("sih_aih_reduzida").field_def(name)
        (claim,) = [c for c in field["x-metadata"]["claims"] if c["target"] == "/field/codes"]
        assert (claim["method"], claim["status"]) == ("cnv-parse", "verified_in_source"), name
        for issue in field["x-metadata"].get("issues", []):
            if issue["id"] == "cnv-difere-do-mapa-anterior":
                assert issue["status"] == "resolved", name
                assert " era " in issue["description"], name
        if name in shared:
            assert (
                field["x-decode"]
                == (load_dicionario("sih_aih_rejeitada").field_def(name)["x-decode"])
            ), name


def _marca_uti(gerar: ModuleType) -> tuple[dict[str, Any], dict[str, str]]:
    """The committed sih marca_uti field and the map its packaged MARCAUTI.CNV yields."""
    from omnisus.transforms.cnv import cnv_map, parse_cnv

    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    doc = yaml.safe_load(
        (ROOT / "src/omnisus/data/dicionarios/sih_aih_reduzida.yaml").read_text("utf-8")
    )
    field = next(f for f in doc["schema"]["fields"] if f["name"] == "marca_uti")
    text = gerar.read_member("sih/CNV/MARCAUTI.CNV", vinculos["membros"])
    return field, dict(sorted(cnv_map(parse_cnv(text)).items()))


def _regenerate(gerar: ModuleType, field: dict[str, Any], decode: dict[str, str]) -> Any:
    evidence = {"source_id": "sih-tab-f05b32f32908", "pages": [], "locator": "x"}
    return gerar.regenerate("sih_aih_reduzida", field, decode, evidence, "2026-09-21")


def test_an_unchanged_cnv_parse_map_is_left_as_is(monkeypatch):
    """Same CNV map over a cnv-parse claim: the field, its claim and its issue stay put."""
    gerar = _load(monkeypatch)
    field, decode = _marca_uti(gerar)
    assert _regenerate(gerar, field, decode) is field


def test_a_codes_claim_from_another_method_is_never_replaced(monkeypatch):
    """A /field/codes claim the generator did not write (e.g. read from a page) is
    reviewed evidence; the generator refuses and names it instead of dropping it."""
    gerar = _load(monkeypatch)
    field, decode = _marca_uti(gerar)
    (claim,) = [c for c in field["x-metadata"]["claims"] if c["target"] == "/field/codes"]
    claim["method"] = "page-read"
    claim["evidence"] = [{"source_id": "sih-dicionario", "pages": [7], "locator": "Tabela 3"}]
    with pytest.raises(
        ValueError, match=r"sih_aih_reduzida\.marca_uti.*'page-read'.*sih-dicionario.*review"
    ):
        _regenerate(gerar, field, decode)


def test_a_changed_cnv_map_over_a_cnv_parse_claim_needs_review(monkeypatch):
    """A republished CNV that relabels, drops or adds codes is refused with those codes;
    the claim and the issue holding the original hand labels are not rewritten."""
    gerar = _load(monkeypatch)
    field, decode = _marca_uti(gerar)
    decode["01"] = "Outro rótulo"
    del decode["99"]
    decode["98"] = "Novo"
    with pytest.raises(
        ValueError, match=r"sih_aih_reduzida\.marca_uti.*\['01', '98', '99'\].*review"
    ):
        _regenerate(gerar, field, decode)


def test_replace_field_keeps_the_entry_indentation(monkeypatch):
    """SINAN dictionaries write `  - name:`; the swap keeps it and touches no other field."""
    gerar = _load(monkeypatch)
    text = (ROOT / "src/omnisus/data/dicionarios/sinan_hanseniase.yaml").read_text("utf-8")
    new = gerar.replace_field(
        text, "nu_lesoes", {"name": "nu_lesoes", "type": "integer", "label": "x"}
    )
    assert "  - name: nu_lesoes\n    type: integer\n    label: x\n  - name: formaclini\n" in new
    before = [f for f in yaml.safe_load(text)["schema"]["fields"] if f["name"] != "nu_lesoes"]
    after = [f for f in yaml.safe_load(new)["schema"]["fields"] if f["name"] != "nu_lesoes"]
    assert after == before
    with pytest.raises(ValueError, match="nu_lesao: 0 field entries"):
        gerar.replace_field(text, "nu_lesao", {"name": "nu_lesao"})


@pytest.mark.parametrize(
    "path", sorted((ROOT / "src/omnisus/data/dicionarios").glob("*.yaml")), ids=lambda p: p.stem
)
def test_replace_field_on_the_last_field_keeps_what_follows(monkeypatch, path):
    """The last entry of every packaged fields list: only that field changes, and the
    keys after the list (primaryKey, x-analytics, ...) survive (pendência 5)."""
    gerar = _load(monkeypatch)
    text = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    last = doc["schema"]["fields"][-1]
    changed = dict(last, description="replaced by the test")
    after = yaml.safe_load(gerar.replace_field(text, last["name"], changed))
    doc["schema"]["fields"][-1] = changed
    assert after == doc


def test_a_mesmo_que_member_is_read_from_the_stored_copy(monkeypatch):
    """TAB_SIH_199201-199712.zip publishes IDENT.CNV with the bytes of TAB_SIH.zip's
    CNV/IDENT.CNV: no second file is packaged, and reading the 1992 member returns the
    stored copy's text, checked against the 1992 member's own SHA-256 (issue #28)."""
    gerar = _load(monkeypatch)
    membros = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))["membros"]
    entry = membros["sih_199201_199712/IDENT.CNV"]
    assert entry["mesmo_que"] == "sih/CNV/IDENT.CNV"
    assert not (CNV / "sih_199201_199712/IDENT.CNV").exists()
    assert gerar.read_member("sih_199201_199712/IDENT.CNV", membros) == gerar.read_member(
        "sih/CNV/IDENT.CNV", membros
    )


def test_a_mesmo_que_member_whose_sha256_differs_from_the_copy_is_refused(monkeypatch):
    """MORTES.CNV of TAB_SIH_199201-199712.zip is not the bytes of TAB_SIH.zip's
    CNV/MORTES.CNV. Pointing the first at the second must fail on the hash, not decode
    the newer table as if it were the old one."""
    gerar = _load(monkeypatch)
    membros = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))["membros"]
    membros["sih_199201_199712/MORTES.CNV"]["mesmo_que"] = "sih/CNV/MORTES.CNV"
    with pytest.raises(ValueError, match=r"sih_199201_199712/MORTES\.CNV: bytes differ"):
        gerar.read_member("sih_199201_199712/MORTES.CNV", membros)


RD_ERAS = ["ident", "sexo", "morte", "natureza", "gestao", "instru", "vincprev"]


def test_the_rd_era_claims_are_the_generator_output(monkeypatch, tmp_path):
    """Each of the three era packages (TAB_SIH_199201-199712, 199801-200307, 200308-200712)
    binds these fields in its own RD.DEF to the same CNV bytes. Dropping the committed
    claim and map and generating again gives the committed field: one evidence entry per
    package, in the order of `def`, and checked_at the latest retrieval (issue #28)."""
    gerar = _load(monkeypatch)
    dicionarios = ROOT / "src/omnisus/data/dicionarios"
    for path in dicionarios.glob("*.yaml"):
        (tmp_path / path.name).write_text(path.read_text("utf-8"), encoding="utf-8")
    target = tmp_path / "sih_aih_reduzida_1992_2007.yaml"
    text = target.read_text("utf-8")
    committed = {f["name"]: f for f in yaml.safe_load(text)["schema"]["fields"]}
    for name in RD_ERAS:
        field = dict(committed[name])
        del field["x-decode"]
        meta = field["x-metadata"]
        claims = [c for c in meta["claims"] if c["target"] != "/field/codes"]
        field["x-metadata"] = {**meta, "claims": claims}
        text = gerar.replace_field(text, name, field)
    target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(gerar, "DICIONARIOS", tmp_path)
    generated = yaml.safe_load(gerar.generate()[target])["schema"]["fields"]
    for field in generated:
        if field["name"] in RD_ERAS:
            assert field == committed[field["name"]], field["name"]
            (claim,) = field["x-metadata"]["claims"]
            assert [e["source_id"] for e in claim["evidence"]] == [
                "sih-tab-b433310785e0",
                "sih-tab-171271844c06",
                "sih-tab-80582969071f",
            ]


def test_a_def_in_the_list_that_does_not_bind_the_field_is_refused(monkeypatch):
    """RD2008.DEF binds TPDISEC1 to CNV/TP_DIAGSEC.CNV; RJ2008.DEF, in the same package
    folder, binds no field to that table. Listing RJ2008.DEF as a second DEF for the field
    must fail instead of citing a package that does not bind it."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    defs = ["sih/RD2008.DEF", "sih/RJ2008.DEF"]
    with pytest.raises(ValueError, match=r"sih/RJ2008\.DEF does not bind tpdisec1"):
        gerar.evidence_for(defs, "tpdisec1", "sih/CNV/TP_DIAGSEC.CNV", vinculos)


def test_a_mesmo_que_chain_is_refused(monkeypatch):
    """sih_199201_199712/IDENT.CNV has no file of its own; a member that names it must
    name the stored copy instead, so a reader never follows a chain."""
    gerar = _load(monkeypatch)
    membros = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))["membros"]
    membros["sih_199801_200307/IDENT.CNV"]["mesmo_que"] = "sih_199201_199712/IDENT.CNV"
    with pytest.raises(ValueError, match="has no file of its own"):
        gerar.read_member("sih_199801_200307/IDENT.CNV", membros)


def test_a_def_in_the_list_without_the_member_is_refused(monkeypatch):
    """TAB_SIH_199801-200307.zip publishes MORTES.CNV; without its member in `membros`
    the generator cannot check that it holds the bytes of the 1992 MORTES.CNV, and
    refuses to cite that package."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    del vinculos["membros"]["sih_199801_200307/MORTES.CNV"]
    defs = gerar.def_paths(vinculos["datasets"]["sih_aih_reduzida_1992_2007"])
    with pytest.raises(ValueError, match=r"sih_199801_200307/MORTES\.CNV is not a member"):
        gerar.evidence_for(defs, "morte", "sih_199201_199712/MORTES.CNV", vinculos)
