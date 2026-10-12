"""Validate that every bundled Frictionless YAML loads cleanly.

The bundled YAMLs are Frictionless ``tabular-data-resource`` descriptors with
the table schema nested under ``schema``. We pull that subdocument out and
hand it to :class:`frictionless.Schema.from_descriptor` so the test exercises
real Frictionless validation rather than just a YAML round-trip.
"""

from __future__ import annotations

import io
import zipfile
from importlib.resources import files

import polars as pl
import pytest
import yaml
from frictionless import Schema as FrictionlessSchema


def _load_schema(dataset: str) -> FrictionlessSchema:
    yaml_path = files("omnisus.data.dicionarios") / f"{dataset}.yaml"
    raw = yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
    return FrictionlessSchema.from_descriptor(raw["schema"])


DICIONARIOS = sorted(
    p.name.removesuffix(".yaml")
    for p in files("omnisus.data.dicionarios").iterdir()
    if p.name.endswith(".yaml")
)


@pytest.mark.parametrize("dataset", DICIONARIOS)
def test_frictionless_loads_for_all_dicionarios(dataset: str) -> None:
    schema = _load_schema(dataset)
    assert schema.fields, f"{dataset} has no fields"


@pytest.mark.parametrize(
    "table", ["aux_uf", "aux_municipios", "aux_cid10", "aux_ocupacoes", "aux_paises"]
)
def test_aux_dictionaries_name_the_bootstrap_columns(table: str) -> None:
    """Each aux_* dictionary declares exactly the columns of its table in the packaged zip."""
    raw = (files("omnisus.data") / "auxiliares-bootstrap.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        columns = pl.read_parquet(io.BytesIO(zf.read(f"{table}.parquet"))).columns
    assert [f.name for f in _load_schema(table).fields] == columns
