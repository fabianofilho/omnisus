from copy import deepcopy

import pytest

import omnisus as sus
from omnisus.transforms.dictionaries import load_dicionario


def test_metadata_is_detached_and_reproducible():
    first = sus.describe_dataset("sim_obitos")
    expected = deepcopy(first)
    first["schema"]["fields"].clear()
    first["fields"].clear()
    assert sus.describe_dataset("sim_obitos") == expected
    assert expected["schema_version"] == "1.0.0"
    assert len(expected["metadata_hash"]) == 64


def test_public_display_preserves_input_and_uncoded_values():
    row = {"sexo": "3", "idade": "2", "cod_idade": "5", "unknown": "01"}
    shown = sus.display_row("sih_aih_reduzida", row)
    assert row == {"sexo": "3", "idade": "2", "cod_idade": "5", "unknown": "01"}
    assert shown["idade"] == "2" and shown["unknown"] == "01"
    assert shown["sexo"] == load_dicionario("sih_aih_reduzida").decode("sexo", "3")


def test_metadata_separates_source_from_observation():
    description = sus.describe_dataset("sim_obitos")
    field = next(x for x in description["fields"] if x["field"]["name"] == "sexo")
    assert field["field"]["logical_type"] == "string"
    assert "observed_type" not in field["field"]
    assert field["field"]["codes"]
    assert all(isinstance(c["value"], str) for c in field["field"]["codes"])


def test_unknown_dataset_has_no_fabricated_description():
    with pytest.raises(FileNotFoundError):
        sus.describe_dataset("no_such_dataset")


def test_all_legacy_fields_have_explicit_review_status():
    description = sus.describe_dataset("sih_aih_reduzida")
    assert len(description["fields"]) == len(description["schema"]["fields"])
    for field in description["fields"]:
        assert field["claims"]
        assert field["applicability"]["status"] in {"unknown", "confirmed"}


@pytest.mark.parametrize("rule", ["age", "sex"])
def test_analytical_evidence_must_resolve(monkeypatch, rule):
    from omnisus.transforms.dictionaries import load_dicionario

    evidence = load_dicionario("sim_obitos").raw["x-analytics"][rule]["evidence"][0]
    monkeypatch.setitem(evidence, "source_id", "nonexistent-evidence")
    with pytest.raises(ValueError, match="Unresolved analytical source"):
        sus.describe_dataset("sim_obitos")


def test_review_hash_rejects_changed_value(monkeypatch):
    from omnisus.transforms.dictionaries import load_dicionario

    field = load_dicionario("sim_obitos").field_def("sexo")
    monkeypatch.setitem(field["x-decode"], "1", "Changed without review")
    with pytest.raises(ValueError, match="Changed reviewed value"):
        sus.describe_dataset("sim_obitos")


@pytest.mark.parametrize(
    "dataset,field_name",
    [
        ("sim_obitos", "idade"),
        ("sih_aih_reduzida", "idade"),
        ("sinasc_nascidos_vivos", "idademae"),
        ("sia_bpa_individualizado", "idadepac"),
        ("sia_psicossocial", "idadepac"),
        ("sia_atencao_domiciliar", "idadepac"),
    ],
)
def test_age_derivation_lists_quantity_and_unit_outputs(dataset, field_name):
    description = sus.describe_dataset(dataset)
    field = next(x for x in description["fields"] if x["field"]["name"] == field_name)
    assert field["field"]["derivation"]["output"] == [
        "idade_anos_completos",
        "idade_quantidade",
        "idade_unidade",
    ]


@pytest.mark.parametrize("dataset", ["sinan_chagas", "sinan_hanseniase", "sinan_tuberculose"])
def test_sinan_age_field_has_derivation_metadata(dataset):
    description = sus.describe_dataset(dataset)
    field = next(x for x in description["fields"] if x["field"]["name"] == "nu_idade_n")
    derivation = field["field"]["derivation"]
    assert derivation is not None
    assert derivation["output"] == [
        "idade_anos_completos",
        "idade_quantidade",
        "idade_unidade",
    ]
    assert field["applicability"]["status"] == "confirmed"
    assert {e["source_id"] for e in field["applicability"]["evidence"]} == {"sinan-b3e0561c7a2d"}


def test_sih_sex_rule_cites_the_documented_cnv_precedence():
    """SEXO.CNV lists 1, 2 and 3 after the fallback 0-9; ManualTabnet.pdf p. 21 says the
    later line wins, which is what the rule's categories assume."""
    rule = sus.describe_dataset("sih_aih_reduzida")["analytics"]["sex"]
    evidence = [e for e in rule["evidence"] if e["source_id"] == "tabnet-5a97b03fe23a"]
    assert [e["pages"] for e in evidence] == [[21]]


def test_sih_natureza_says_when_it_stopped_being_filled():
    """IT_SIHSUS_1603 p. 2: NATUREZA "com conteúdo até maio/12"."""
    description = sus.describe_dataset("sih_aih_reduzida")
    column = next(x for x in description["fields"] if x["field"]["name"] == "natureza")
    assert "maio de 2012" in column["field"]["description"]
    (claim,) = [c for c in column["claims"] if c["target"] == "/field/description"]
    assert claim["status"] == "verified_in_source"
    assert [(e["source_id"], e["pages"]) for e in claim["evidence"]] == [
        ("sihsus-1e89d5f2cc41", [2])
    ]
