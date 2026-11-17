"""The resolved contract of every packaged dictionary validates against the JSON Schema (#9).

``scripts/metadados/consultar.py`` validated one field on demand; nothing ran it over the
dictionaries, so an invented claim status or a misspelled key passed unnoticed.
"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

import omnisus as sus

ROOT = Path(__file__).resolve().parents[3]
DICIONARIOS = ROOT / "src/omnisus/data/dicionarios"
DATASETS = sorted(path.stem for path in DICIONARIOS.glob("*.yaml"))


def _consultar():
    spec = importlib.util.spec_from_file_location(
        "consultar", ROOT / "scripts" / "metadados" / "consultar.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documents(dataset: str):
    description = sus.describe_dataset(dataset)
    header = {key: description[key] for key in ("schema_version", "dictionary_version")}
    for field in description["fields"]:
        yield {**header, "dataset": description["dataset"], **field}


@pytest.mark.parametrize("dataset", DATASETS)
def test_every_field_document_is_valid(dataset) -> None:
    validate = _consultar().validate_metadata
    for document in _documents(dataset):
        validate(document)


def test_an_invented_claim_status_is_refused() -> None:
    validate = _consultar().validate_metadata
    document = deepcopy(next(_documents("sih_aih_rejeitada")))
    document["claims"][0]["status"] = "probably_fine"
    with pytest.raises(jsonschema.ValidationError):
        validate(document)
