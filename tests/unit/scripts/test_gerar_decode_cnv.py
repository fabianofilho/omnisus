"""The committed dictionaries are the generator's output; no CNV-bound hand map survives."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
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
    listed in ``campos`` or ``sem_cnv`` too; it cannot pass unnoticed. A field in
    ``sem_cnv`` may be bound at any start column: issue #137 lists a start other than 1
    as one of the reasons a binding gives no map (RD2008.DEF ``DIAS_PERM`` at 2,
    ``N_AIH`` at 5).
    """
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    for dataset, spec in vinculos["datasets"].items():
        bound = {
            b.field.lower()
            for def_path in spec["def"]
            for b in parse_def(gerar.read_def(def_path, vinculos))
            if b.start in (1, None)
        }
        doc = yaml.load(
            (ROOT / "src/omnisus/data/dicionarios" / f"{dataset}.yaml").read_text("utf-8"),
            Loader=yaml.CSafeLoader,
        )
        hand = {f["name"] for f in doc["schema"]["fields"] if f.get("x-decode")} & bound
        listed = set(spec["campos"]) | set(spec.get("sem_cnv", {}))
        assert hand <= listed, (dataset, sorted(hand - listed))
        bound_anywhere = {
            b.field.lower()
            for def_path in spec["def"]
            for b in parse_def(gerar.read_def(def_path, vinculos))
        }
        assert set(spec.get("sem_cnv", {})) <= bound_anywhere, dataset


# Issue #7: the fields RD2008.DEF and RJ2008.DEF bind at position 1 to CNV members that
# are not packaged yet, with the values the RR 2024-01 fixture publishes. gestor_cod of
# the RD is related to DBF/LIBGESTOR.DBF (a lookup, decision 6), not bound to a CNV, so
# it is not here.
SIH_FIELDS_WAITING_FOR_A_MEMBER = [
    ("sih_aih_reduzida", "sih_rr_2024_01_mini", "nat_jur", {"1236", "1244", "2062"}),
    ("sih_aih_reduzida", "sih_rr_2024_01_mini", "cnaer", {"000"}),
    ("sih_aih_rejeitada", "sih_rj_rr_2024_01_mini", "nat_jur", {"1236", "1244"}),
    ("sih_aih_rejeitada", "sih_rj_rr_2024_01_mini", "cnaer", {"000"}),
    ("sih_aih_rejeitada", "sih_rj_rr_2024_01_mini", "gestor_cod", {""}),
]


@pytest.mark.parametrize(
    ("dataset", "fixture", "field", "observed"), SIH_FIELDS_WAITING_FOR_A_MEMBER
)
def test_a_sih_field_bound_to_an_unpackaged_cnv_is_excused_naming_each_member(
    monkeypatch, dataset, fixture, field, observed
):
    """Issue #7, decision 4: a field the SIH DEF binds to a CNV that is not packaged has no
    map and is listed in `sem_cnv` with a reason that names every member the DEF binds it
    to, taken from the packaged DEF, not from memory; the fixture publishes exactly the
    values recorded here, which the reason may cite."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    spec = vinculos["datasets"][dataset]
    members = {
        (Path(def_path).parent / b.table.replace("\\", "/")).as_posix()
        for def_path in spec["def"]
        for b in parse_def(gerar.read_def(def_path, vinculos))
        if b.field.lower() == field and b.start == 1
    }
    assert members, (dataset, field)
    packaged = {m.lower() for m in vinculos["membros"]}
    assert not {m.lower() for m in members} & packaged, (dataset, field)
    doc = yaml.load(
        (ROOT / "src/omnisus/data/dicionarios" / f"{dataset}.yaml").read_text("utf-8"),
        Loader=yaml.CSafeLoader,
    )
    (definition,) = [f for f in doc["schema"]["fields"] if f["name"] == field]
    assert "x-decode" not in definition
    assert field not in spec["campos"]
    reason = spec.get("sem_cnv", {}).get(field, "")
    assert reason, (dataset, field)
    assert all(Path(m).name in reason for m in members), (dataset, field, sorted(members))
    frame = dbc_bytes_to_lazyframe(
        (ROOT / "tests/fixtures/dbc" / f"{fixture}.dbc").read_bytes(), dataset=dataset
    ).collect()
    assert set(frame[field].to_list()) == observed, (dataset, field)


# Issue #137: every field RD2008.DEF and RJ2008.DEF bind to a CNV, at any start column,
# has a map (`x-decode` or `campos`) or a reason in `sem_cnv`. The issue leaves one field
# out on purpose: cod_idade of the RJ, which issue #6 tracks.
SIH_2008_FIELDS_LEFT_TO_ANOTHER_ISSUE = {"sih_aih_rejeitada": {"cod_idade"}}
_CITED_LINES = re.compile(r"\blinhas? ((?:\d+(?:-\d+)?(?:, | e )?)+)")


def _cited_lines(reason: str) -> set[int]:
    """The DEF lines a reason cites, from its "linha N" and "linhas A-B, C e D" parts."""
    cited: set[int] = set()
    for group in _CITED_LINES.findall(reason):
        for first, last in re.findall(r"(\d+)(?:-(\d+))?", group):
            cited.update(range(int(first), int(last or first) + 1))
    return cited


@pytest.mark.parametrize("dataset", ["sih_aih_reduzida", "sih_aih_rejeitada"])
def test_every_field_the_sih_2008_def_binds_has_a_map_or_a_reason(monkeypatch, dataset):
    """Issue #137 (decision 4 of #7, extended): no field the RD or RJ DEF binds is left
    without a map and without a word. A field with no map is in `sem_cnv` with a reason
    that names the DEF and cites every line of it that binds the field, read from the
    packaged DEF (each line on its own), and says why the binding gives no map: a
    grouping, a start other than 1, a start column the DEF does not give, or a member
    that is not packaged. cod_idade of the RJ is the one field left out, by the issue."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    spec = vinculos["datasets"][dataset]
    (def_path,) = spec["def"]
    doc = yaml.load(
        (ROOT / "src/omnisus/data/dicionarios" / f"{dataset}.yaml").read_text("utf-8"),
        Loader=yaml.CSafeLoader,
    )
    fields = {f["name"]: f for f in doc["schema"]["fields"]}
    lines: dict[str, set[int]] = defaultdict(set)
    text = gerar.read_def(def_path, vinculos)
    for number, line in enumerate(text.splitlines(), 1):
        for b in parse_def(line):
            if b.field.lower() in fields:
                lines[b.field.lower()].add(number)
    reasons = spec.get("sem_cnv", {})
    without_word = {
        f
        for f in lines
        if not fields[f].get("x-decode") and f not in spec["campos"] and f not in reasons
    }
    assert without_word == SIH_2008_FIELDS_LEFT_TO_ANOTHER_ISSUE.get(dataset, set()), (
        dataset,
        sorted(without_word),
    )
    for field in sorted(lines.keys() & reasons.keys()):
        if fields[field].get("x-decode"):
            continue  # a hand map with a reason says why the CNV does not fit (cod_idade, RD)
        reason = reasons[field]
        assert Path(def_path).name in reason, (dataset, field)
        missing = lines[field] - _cited_lines(reason)
        assert not missing, (dataset, field, sorted(missing))
        kinds = ("agrupamento", "posição", "coluna inicial", "empacotad")
        assert any(kind in reason for kind in kinds), (dataset, field)


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
    # RJ has no tpdisec fields (RJ2008.DEF binds none to TP_DIAGSEC.CNV), and RJ2008.DEF
    # does not cite FONTE_ORC.
    assert set(rd) - shared == {"fonte_orc", "marca_uci", *(f"tpdisec{n}" for n in range(1, 10))}
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
    doc = yaml.load(
        (ROOT / "src/omnisus/data/dicionarios/sih_aih_reduzida.yaml").read_text("utf-8"),
        Loader=yaml.CSafeLoader,
    )
    field = next(f for f in doc["schema"]["fields"] if f["name"] == "marca_uti")
    text = gerar.read_member("sih/CNV/MARCAUTI.CNV", vinculos["membros"])
    return field, dict(sorted(cnv_map(parse_cnv(text)).items()))


def _regenerate(gerar: ModuleType, field: dict[str, Any], decode: dict[str, str]) -> Any:
    """Regenerate with the committed claim's own evidence and checked_at."""
    (claim,) = [c for c in field["x-metadata"]["claims"] if c["target"] == "/field/codes"]
    return gerar.regenerate(
        "sih_aih_reduzida", field, decode, claim["evidence"], claim["checked_at"]
    )


def test_an_unchanged_cnv_parse_map_is_left_as_is(monkeypatch):
    """Same CNV map and evidence over a cnv-parse claim: the field, its claim and its
    issue stay put."""
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
    before = [
        f
        for f in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]
        if f["name"] != "nu_lesoes"
    ]
    after = [
        f
        for f in yaml.load(new, Loader=yaml.CSafeLoader)["schema"]["fields"]
        if f["name"] != "nu_lesoes"
    ]
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
    doc = yaml.load(text, Loader=yaml.CSafeLoader)
    last = doc["schema"]["fields"][-1]
    changed = dict(last, description="replaced by the test")
    after = yaml.load(gerar.replace_field(text, last["name"], changed), Loader=yaml.CSafeLoader)
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
    committed = {
        f["name"]: f for f in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]
    }
    for name in RD_ERAS:
        field = dict(committed[name])
        del field["x-decode"]
        meta = field["x-metadata"]
        claims = [c for c in meta["claims"] if c["target"] != "/field/codes"]
        field["x-metadata"] = {**meta, "claims": claims}
        text = gerar.replace_field(text, name, field)
    target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(gerar, "DICIONARIOS", tmp_path)
    generated = yaml.load(gerar.generate()[target], Loader=yaml.CSafeLoader)["schema"]["fields"]
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
    defs = vinculos["datasets"]["sih_aih_reduzida_1992_2007"]["def"]
    with pytest.raises(ValueError, match=r"sih_199801_200307/MORTES\.CNV is not a member"):
        gerar.evidence_for(defs, "morte", "sih_199201_199712/MORTES.CNV", vinculos)


def test_every_dataset_lists_its_defs():
    """`def` has one shape: a list of DEF members, one per package publishing the
    bindings (AGENTS.md rule 5: one mechanism, not a string or a list)."""
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    for dataset, spec in vinculos["datasets"].items():
        assert isinstance(spec["def"], list) and spec["def"], dataset
        assert all(d in vinculos["membros"] for d in spec["def"]), dataset


def test_a_def_in_the_list_whose_member_has_other_bytes_is_refused(monkeypatch):
    """MORTES.CNV of TAB_SIH.zip (sih/CNV/MORTES.CNV) is not the bytes of the 1992
    MORTES.CNV. If the 1998 package's member recorded those bytes, its RD.DEF would
    bind MORTE to a different map: the generator must refuse to cite it."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    membros = vinculos["membros"]
    other = membros["sih/CNV/MORTES.CNV"]["sha256"]
    assert other != membros["sih_199201_199712/MORTES.CNV"]["sha256"]
    membros["sih_199801_200307/MORTES.CNV"]["sha256"] = other
    defs = vinculos["datasets"]["sih_aih_reduzida_1992_2007"]["def"]
    with pytest.raises(ValueError, match=r"sih_199801_200307/MORTES\.CNV is not a member"):
        gerar.evidence_for(defs, "morte", "sih_199201_199712/MORTES.CNV", vinculos)


def test_a_hand_edited_evidence_of_a_current_claim_is_rewritten(monkeypatch, tmp_path):
    """The generator owns the evidence and checked_at of its own claims: a hand edit of
    the locator or date of sih_aih_reduzida.marca_uti (same map) comes back as generated,
    so `--check` fails on it (issue #28: hand-written evidence went unnoticed)."""
    gerar = _load(monkeypatch)
    dicionarios = ROOT / "src/omnisus/data/dicionarios"
    for path in dicionarios.glob("*.yaml"):
        (tmp_path / path.name).write_text(path.read_text("utf-8"), encoding="utf-8")
    target = tmp_path / "sih_aih_reduzida.yaml"
    text = target.read_text("utf-8")
    committed = next(
        f
        for f in yaml.load(text, Loader=yaml.CSafeLoader)["schema"]["fields"]
        if f["name"] == "marca_uti"
    )
    edited = json.loads(json.dumps(committed))
    (claim,) = [c for c in edited["x-metadata"]["claims"] if c["target"] == "/field/codes"]
    claim["evidence"][0]["locator"] = "escrito à mão"
    claim["checked_at"] = "2026-01-01"
    target.write_text(gerar.replace_field(text, "marca_uti", edited), encoding="utf-8")
    monkeypatch.setattr(gerar, "DICIONARIOS", tmp_path)
    generated = yaml.load(gerar.generate()[target], Loader=yaml.CSafeLoader)["schema"]["fields"]
    assert next(f for f in generated if f["name"] == "marca_uti") == committed


def test_a_dbf_field_with_several_defs_is_refused(monkeypatch):
    """Motivo_de_Erro.DEF relates CO_ERRO to DBF/MOTERRO.dbf and names the description
    column. No dataset lists two DEFs for a DBF field, so the test lists the real
    Motivo_de_Erro.DEF twice: the generator reads the column from one DEF only, and
    must refuse rather than cite DEFs whose column it never read."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    defs = ["sih/Motivo_de_Erro.DEF", "sih/Motivo_de_Erro.DEF"]
    with pytest.raises(ValueError, match=r"DBF member .* one DEF"):
        gerar.evidence_for(defs, "co_erro", "sih/DBF/MOTERRO.dbf", vinculos)


def test_a_bare_cnv_name_resolves_beside_the_def_not_in_its_cnv_folder(monkeypatch):
    """APAC_Pos_Cirurgia_Bariatica.def line 241 binds AP_MN_IND to `MANT_IND.CNV`, with no
    `CNV/` folder; the eight other APAC DEFs, AB's among them, name `CNV/MANT_IND.CNV`.
    The generator resolves a table path from the DEF's folder, so that line names
    `sia/MANT_IND.CNV`, which is not a packaged member, and not `sia/CNV/MANT_IND.CNV`.
    ABO's AP_MN_IND stays without a map, listed in `sem_cnv`; AB's takes the CNV."""
    gerar = _load(monkeypatch)
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    pos = "sia/APAC_Pos_Cirurgia_Bariatica.def"
    text = gerar.read_def(pos, vinculos)
    assert text.splitlines()[240].split(",")[-1].strip() == "MANT_IND.CNV"
    with pytest.raises(ValueError, match="does not bind ap_mn_ind"):
        gerar.binding_for(pos, text, "ap_mn_ind", "sia/CNV/MANT_IND.CNV")
    assert "sia/MANT_IND.CNV" not in vinculos["membros"]
    abo = vinculos["datasets"]["sia_apac_cirurgia_bariatrica"]
    assert "ap_mn_ind" not in abo["campos"] and "ap_mn_ind" in abo["sem_cnv"]
    ab = vinculos["datasets"]["sia_apac_acompanhamento_bariatrica"]
    assert ab["campos"]["ap_mn_ind"] == "sia/CNV/MANT_IND.CNV"
