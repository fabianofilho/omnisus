"""TabWin DEF/CNV parsing on real packaged members (TabWin.pdf pp. 87-92)."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest

from omnisus.metadata import sources_registry
from omnisus.transforms.cnv import (
    CnvFormatError,
    CnvLine,
    cnv_map,
    dbf_lookup_map,
    parse_cnv,
    parse_def,
    parse_def_lookups,
    range_keys,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
CNV = files("omnisus.data.dicionarios") / "sources" / "cnv"


def member(path: str) -> str:
    return (CNV / path).read_bytes().decode("latin-1")


def test_packaged_members_are_the_archived_bytes():
    vinculos = json.loads((CNV / "vinculos.json").read_text(encoding="utf-8"))
    registry = {s["id"]: s for s in sources_registry()["sources"]}
    packaged = sorted(
        # as_posix: vinculos.json records one separator, the one the repository uses.
        Path(str(p)).relative_to(Path(str(CNV))).as_posix()
        for p in Path(str(CNV)).rglob("*")
        if p.is_file() and p.name != "vinculos.json"
    )
    assert packaged == sorted(vinculos["membros"])
    for path, entry in vinculos["membros"].items():
        assert hashlib.sha256((CNV / path).read_bytes()).hexdigest() == entry["sha256"], path
        assert registry[entry["fonte"]]["authority"] == "official"


def test_a_def_binds_one_field_to_several_tables():
    bindings = parse_def(member("sih/RD2008.DEF"))
    assert len(bindings) == 296
    assert [(b.kind, b.start, b.table) for b in bindings if b.field == "COBRANCA"] == [
        ("L", 1, "CNV\\SAIDAPERM.CNV"),
        ("C", 1, "CNV\\SAIDAPERMc.CNV"),
        ("S", 1, "CNV\\SAIDAPERM.CNV"),
    ]
    assert sum(b.field == "MUNIC_MOV" for b in bindings) == 15


def test_a_def_line_whose_third_field_is_a_name_keeps_the_binding_with_unknown_start():
    """RD2008.DEF: 'SubTp FAEC,FAEC_TP,DS_TPFIN,CNV\\TP_FINAN.CNV' and
    'Procedimentos obstétricos,PROC_REA,IP_DSCR,CNV\\PROCOBS2b.CNV' name a field
    (DS_TPFIN / IP_DSCR) instead of a start column in the third position. TabWin.pdf
    pp. 87-88 documents only two S/L/C forms: a numeric start column, or a related
    *.DBF* file (identified "pela extensão do nome do arquivo"); neither covers a
    non-numeric third field paired with a *.CNV* table, so the binding is kept
    (field and table sit in the same position in every documented form) with its
    start column marked unknown instead of being silently dropped.
    """
    bindings = parse_def(member("sih/RD2008.DEF"))
    assert [(b.kind, b.start, b.table) for b in bindings if b.field == "FAEC_TP"] == [
        ("L", None, "CNV\\TP_FINAN.CNV"),
        ("C", None, "CNV\\TP_FINAN.CNV"),
        ("S", None, "CNV\\TP_FINAN.CNV"),
    ]
    assert [(b.kind, b.start, b.table) for b in bindings if b.field == "PROC_REA"] == [
        ("L", None, "CNV\\PROCOBS2b.CNV"),
        ("C", None, "CNV\\PROCOBS2b.CNV"),
        ("S", None, "CNV\\PROCOBS2b.CNV"),
    ]


def test_a_def_line_relating_a_dbf_names_its_description_column():
    """Motivo_de_Erro.DEF (TAB_SIH) line 74 relates CO_ERRO to DBF/MOTERRO.DBF; the third
    field is the column holding the description (TabWin.pdf p. 88, "Campo D")."""
    lookups = parse_def_lookups(member("sih/Motivo_de_Erro.DEF"))
    assert [(b.kind, b.field, b.column, b.table) for b in lookups if b.field == "CO_ERRO"] == [
        ("X", "CO_ERRO", "DS_MOT_ERR", "DBF/MOTERRO.DBF")
    ]
    assert all(b.field != "CO_ERRO" for b in parse_def(member("sih/Motivo_de_Erro.DEF")))


def test_a_related_dbf_without_the_field_is_keyed_by_its_first_field():
    """MOTERRO.dbf has no CO_ERRO field, so TabWin indexes it by its first field,
    CD_MOT_ERR (TabWin.pdf p. 88). 641 records, 641 distinct codes."""
    labels = dbf_lookup_map((CNV / "sih/DBF/MOTERRO.dbf").read_bytes(), "CO_ERRO", "DS_MOT_ERR")
    assert len(labels) == 641
    assert labels["040006"] == "AIH APROVADA EM OUTRO PROCESSAMENTO"
    assert labels["060082"] == "QUANTIDADE DE DIÁRIAS SUPERIOR A CAPACIDADE INSTALADA"
    assert labels["0001"] == "DUPLICIDADE"


def test_a_def_line_naming_a_cnv_in_an_unknown_shape_fails():
    """Synthetic (AGENTS.md rule 2): a line naming a .CNV with a field count that
    fits neither documented S/L/C form must raise, never be dropped silently."""
    with pytest.raises(CnvFormatError, match=r"DEF line 1 names a CNV"):
        parse_def("LDescricao,CAMPO,1,extra,CNV\\TABELA.CNV\n")


def test_a_def_skips_comment_lines_and_keeps_the_letter_as_written():
    obito = parse_def(member("sim/Obito_1996_CID10.def"))
    # ";X*Escol series agreg, ESCFALAGR1, 1, ESCAGR1.CNV" is a comment line.
    assert [b.table for b in obito if b.field == "ESCFALAGR1"] == ["ESCAGR1.CNV", "ESCAGR2.CNV"]
    nascido = parse_def(member("sinasc/NASCIDO.def"))
    assert [(b.kind, b.field) for b in nascido if b.kind.islower()] == [("l", "CODESTAB")]


def test_a_cnv_line_lists_several_codes():
    lines = parse_cnv(member("sih/CNV/SAIDAPERM.CNV"))
    assert len(lines) == 28
    assert lines[15] == CnvLine(16, "Transferência para internação domiciliar", ("29", "32"), ())
    assert lines[21].codes == ("61", "17")


def test_range_keys_are_the_codes_only_a_range_labels():
    """Issue #31: SIH SEXO.CNV labels 0 and 4-9 only through ``Ignorado 0-9``, and CNES
    tiposegm.cnv labels 3-9 only through ``INVÁLIDO ,0,3-9``; the codes a line lists by
    themselves (SEXO 1-3; tiposegm blank, 0, 1, 2) are not range keys."""
    assert range_keys(parse_cnv(member("sih/CNV/SEXO.CNV"))) == {"0", *"456789"}
    assert range_keys(parse_cnv(member("cnes/CNV/tiposegm.cnv"))) == set("3456789")


def test_a_short_code_listed_again_takes_the_later_line():
    """ManualTabnet.pdf p. 21: in MESES.CNV, '01' is first "Ignorado" (00-99) and then
    "Janeiro", "esta prevalece, por aparecer por último". SIH SEXO.CNV and NATUREZA.CNV
    open with such a range."""
    sexo = parse_cnv(member("sih/CNV/SEXO.CNV"))
    assert sexo[0] == CnvLine(3, "Ignorado", (), ("0", "4", "5", "6", "7", "8", "9"))
    assert cnv_map(sexo) == {
        "0": "Ignorado",
        "1": "Masculino",
        "2": "Feminino",
        "3": "Feminino",
        **{code: "Ignorado" for code in "456789"},
    }
    natureza = cnv_map(parse_cnv(member("sih/CNV/NATUREZA.CNV")))
    assert len(natureza) == 100
    assert (natureza["00"], natureza["10"], natureza["11"], natureza["92"]) == (
        "Ignorado",
        "Próprio",
        "Ignorado",
        "Universitário de ensino e pesquisa privado",
    )


def test_codes_keep_their_blanks_and_keys_match_stored_values():
    """The lake right-strips DBF character fields; '0 ' is stored as '0', ' ' as ''."""
    assert parse_cnv(member("sinasc/ESCAGR1.CNV"))[1].codes == ("00", "0 ")
    assert cnv_map(parse_cnv(member("sinasc/TPMETODO.CNV"))) == {
        "1": "Exame Fisico",
        "2": "Outro Metodo",
        "8": "DUM",
        "9": "Ign",
        "": "N Inf",
    }


def test_a_wide_table_uses_the_100_column_layout():
    lines = parse_cnv(member("sih/CNV/LEITOS.CNV"))
    assert len(lines) == 41
    assert cnv_map(lines)["07"] == "07-Pediátricos"


def test_a_code_of_another_width_is_kept_as_written():
    assert parse_cnv(member("cnes/CNV/TurnosAt.CNV"))[7].codes == ("  -99",)


def test_a_description_may_reach_column_60_when_codes_start_at_61():
    """CBO2002.CNV (SIM) writes a 51st description character in column 60 on 246 lines."""
    lines = parse_cnv(member("sim/CBO2002.CNV"))
    assert len(lines) == 2429
    assert lines[62].label == "Dirigente e administrador de organização da socieda"
    assert lines[62].codes == ("114405",)
    decode = cnv_map(lines)
    assert decode["010105"] == decode["10105"] == "Oficial General da Aeronáutica"
    assert decode["622020"].startswith("Trabalhador volante da agricultura")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("      1  Colera" + " " * 45 + "A00-A09\n", "non-numeric range"),
        ("      1  Longo" + " " * 46 + "123\n", "wider than the declared 2"),
    ],
)
def test_codes_must_fit_the_header(body, message):
    """Synthetic malformed tables (AGENTS.md rule 2): no packaged CNV has either defect."""
    with pytest.raises(CnvFormatError, match=message):
        parse_cnv("1 2\n" + body)


def test_a_real_line_outside_the_layout_fails():
    """DNNOVA.CNV (SINASC) writes its code in column 60; the manual starts codes at 61."""
    text = (FIXTURES / "cnv" / "DNNOVA.CNV").read_bytes().decode("latin-1")
    with pytest.raises(CnvFormatError, match="column layout"):
        parse_cnv(text)


@pytest.mark.parametrize(
    ("header", "body", "message"),
    [
        (
            "2 5",
            "      1  Um" + " " * 49 + "12345\n      2  Outro" + " " * 46 + "12345\n",
            "long code '12345' twice: explicit and explicit",
        ),
        ("2 2", "      1  Todos" + " " * 46 + "0-99\n", "unequal width"),
    ],
)
def test_a_long_code_claimed_twice_or_an_uneven_range_fails(header, body, message):
    """Synthetic malformed tables (AGENTS.md rule 2). TabWin.pdf p. 91 keeps the first
    reference of a long code; no packaged CNV repeats one, so the parser refuses it."""
    with pytest.raises(CnvFormatError, match=message):
        parse_cnv(header + "\n" + body)


def test_sinan_defs_bind_every_cnv_at_a_known_column():
    """ChagasNET.def and HansNET.def (TAB_SINANNET): every CNV binding has a numeric start."""
    for path, count in [("sinan/ChagasNET.def", 481), ("sinan/HansNET.def", 334)]:
        bindings = parse_def(member(path))
        assert len(bindings) == count, path
        assert all(b.start is not None for b in bindings), path


def test_sinan_escolaridade_puts_nine_and_blank_on_one_line():
    """Escolarnet.cnv is the only official source of 0/00 and the two-digit spellings, and
    it files 9, 09, 99 and blank under one label; the SINAN block keeps 9 apart."""
    decode = cnv_map(parse_cnv(member("sinan/Escolarnet.cnv")))
    assert decode["0"] == decode["00"] == "Analfabeto"
    assert decode["3"] == decode["03"] == "5ª a 8ª série incompleta do EF"
    assert decode["9"] == decode["09"] == decode["99"] == decode[""] == "Ign/Branco"
    assert decode["10"] == "Não se aplica"
    assert len(decode) == 23
