"""Tests for transforms.dictionaries — Frictionless YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omnisus.transforms.dictionaries import Dicionario, load_dicionario

# ---------------------------------------------------------------------------
# Loading + caching
# ---------------------------------------------------------------------------


def test_load_aux_uf_returns_dicionario() -> None:
    dic = load_dicionario("aux_uf")
    assert isinstance(dic, Dicionario)
    assert dic.name == "aux_uf"
    assert dic.encoding == "utf-8"


def test_load_dicionario_unknown_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_dicionario("does_not_exist")


def test_loader_caches_parsed_yaml() -> None:
    a = load_dicionario("aux_uf")
    b = load_dicionario("aux_uf")
    assert a is b  # lru_cache


def test_a_packaged_dictionary_is_parsed_by_libyaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """libyaml reads a dictionary several times faster than PyYAML's pure-Python loader."""
    parsed = []

    class Spy(yaml.CSafeLoader):
        def __init__(self, stream: str) -> None:
            parsed.append(stream)
            super().__init__(stream)

    monkeypatch.setattr(yaml, "CSafeLoader", Spy)
    load_dicionario.__wrapped__("sih_aih_rejeitada")
    assert len(parsed) == 1


def test_without_libyaml_a_dictionary_loads_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PyYAML built without libyaml has no CSafeLoader; the pure-Python loader gives
    the same dictionary."""
    expected = load_dicionario("sih_aih_rejeitada").raw
    monkeypatch.delattr(yaml, "CSafeLoader")
    assert load_dicionario.__wrapped__("sih_aih_rejeitada").raw == expected


def test_load_sim_obitos_has_expected_extensions() -> None:
    dic = load_dicionario("sim_obitos")
    assert dic.encoding == "latin-1"
    assert dic.partitions == ["ano", "uf"]
    assert dic.source_format == "dbc"
    # Type-tolerant decode: int input + string keys in YAML
    assert dic.decode("sexo", 1) == "Masculino"
    assert dic.decode("sexo", 99) is None


# ---------------------------------------------------------------------------
# field_def — case-insensitive lookup
# ---------------------------------------------------------------------------


def test_field_def_lookup_is_case_insensitive() -> None:
    dic = load_dicionario("sim_obitos")
    assert dic.field_def("sexo") is dic.field_def("SEXO")
    assert dic.field_def("SEXO")["name"] == "sexo"
    assert dic.field_def("nonexistent") is None


# ---------------------------------------------------------------------------
# decode — type tolerance
# ---------------------------------------------------------------------------


def test_decode_accepts_string_input_for_string_keys() -> None:
    dic = load_dicionario("sim_obitos")
    # YAML keys are strings; lake stores VARCHAR — string input must work.
    assert dic.decode("tipobito", "1") == "Fetal"
    assert dic.decode("tipobito", "2") == "Não Fetal"


def test_decode_accepts_int_input_for_string_keys() -> None:
    dic = load_dicionario("sim_obitos")
    # Same data, but value happens to be an int — must still match.
    assert dic.decode("tipobito", 1) == "Fetal"
    assert dic.decode("tipobito", 2) == "Não Fetal"


def test_decode_strips_whitespace() -> None:
    dic = load_dicionario("sim_obitos")
    # DBF/DBC files frequently pad codes with spaces — must still decode.
    assert dic.decode("sexo", " 1 ") == "Masculino"


def test_decode_unknown_value_has_no_label() -> None:
    """A code the map does not know is never guessed (CONTEXT.md, Label)."""
    dic = load_dicionario("sim_obitos")
    assert dic.decode("sexo", "Z") is None
    assert dic.decode("sexo", 42) is None


def test_decode_field_without_code_map_has_no_label() -> None:
    dic = load_dicionario("sim_obitos")
    assert dic.decode("not_a_field", "anything") is None
    assert dic.decode("dtobito", "01012024") is None


def test_decode_handles_padded_string_keys() -> None:
    """Codes like ``ESCFALAGR1`` use 2-digit padded keys ('00', '01')."""
    dic = load_dicionario("sim_obitos")
    assert dic.decode("escfalagr1", "00") == "Sem Escolaridade"
    # Int 0 must also map to '00' via string normalization — but the YAML has
    # both '00' and '01'..'12', so int 0 should NOT match '00' (different key).
    # We accept that one as-is (no decode happens).
    assert dic.decode("escfalagr1", "01") == "Fundamental I Incompleto"


# ---------------------------------------------------------------------------
# decode_row — full-row decoding with transforms + decode
# ---------------------------------------------------------------------------


def test_decode_row_translates_x_decode_fields() -> None:
    dic = load_dicionario("sim_obitos")
    row = {"sexo": "1", "racacor": "2", "tipobito": "2"}
    result = dic.decode_row(row)
    assert result["sexo"] == "Masculino"
    assert result["racacor"] == "Preta"
    assert result["tipobito"] == "Não Fetal"


def test_decode_row_passes_unknown_keys_through_unchanged() -> None:
    dic = load_dicionario("sim_obitos")
    row = {"sexo": "1", "made_up_field": "raw_value"}
    result = dic.decode_row(row)
    assert result["sexo"] == "Masculino"
    assert result["made_up_field"] == "raw_value"


def test_decode_row_handles_empty_and_none_values() -> None:
    dic = load_dicionario("sim_obitos")
    # A blank or null code has no label; a field without a code map is untouched.
    row = {"sexo": None, "horaobito": "", "tipobito": "  "}
    result = dic.decode_row(row)
    assert result["sexo"] is None
    assert result["horaobito"] == ""
    assert result["tipobito"] is None


def test_decode_row_accepts_uppercase_keys() -> None:
    """Legacy callers may pass uppercase DBF column names — must still decode."""
    dic = load_dicionario("sim_obitos")
    result = dic.decode_row({"SEXO": "1", "DTOBITO": "01012024"})
    assert result["SEXO"] == "Masculino"
    assert result["DTOBITO"] == "01012024"


def test_decode_row_returns_new_dict() -> None:
    dic = load_dicionario("sim_obitos")
    row = {"sexo": "1"}
    result = dic.decode_row(row)
    assert result is not row
    assert row["sexo"] == "1"  # original untouched


def test_decode_row_handles_empty_input() -> None:
    dic = load_dicionario("sim_obitos")
    assert dic.decode_row({}) == {}


# ---------------------------------------------------------------------------
# Labels — used by the explorer for human-readable column headers
# ---------------------------------------------------------------------------


def test_sim_fields_have_labels() -> None:
    dic = load_dicionario("sim_obitos")
    assert dic.field_def("sexo")["label"] == "Sexo"
    assert dic.field_def("dtobito")["label"] == "Data do óbito"
    assert dic.field_def("horaobito")["label"] == "Hora do óbito"
    assert dic.field_def("idade")["label"] == "Idade"


def test_sinasc_fields_have_labels() -> None:
    dic = load_dicionario("sinasc_nascidos_vivos")
    assert dic.field_def("sexo")["label"] == "Sexo"
    assert dic.field_def("dtnasc")["label"] == "Data de nascimento"


def test_sih_fields_have_labels() -> None:
    dic = load_dicionario("sih_aih_reduzida")
    assert dic.field_def("dt_inter")["label"] == "Data de internação"
    assert dic.field_def("morte")["label"] == "Óbito"


# ---------------------------------------------------------------------------
# Path-based loading (uncurated datasets)
# ---------------------------------------------------------------------------


def _copy_packaged(name: str, dest: Path) -> Path:
    from importlib.resources import files

    src = (files("omnisus.data.dicionarios") / f"{name}.yaml").read_text(encoding="utf-8")
    dest.write_text(src, encoding="utf-8")
    return dest


def test_load_dicionario_accepts_a_path(tmp_path: Path) -> None:
    """An ad-hoc dataset supplies its own YAML."""
    custom = _copy_packaged("sim_obitos", tmp_path / "custom.yaml")
    dic = load_dicionario(custom)
    packaged = load_dicionario("sim_obitos")
    assert dic.name == packaged.name
    assert dic.encoding == packaged.encoding
    assert [f["name"] for f in dic.fields] == [f["name"] for f in packaged.fields]


def test_load_dicionario_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="dicionario not found"):
        load_dicionario(tmp_path / "nope.yaml")
