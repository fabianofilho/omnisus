"""A code map is either written as a claim or it is not there (#72).

The maintainer's rule: a field with ``x-decode`` has an authored ``/field/codes`` claim, with
its evidence or, when the map was measured and not read, ``method: fixture-measure``,
``unreviewed`` and an open issue on the field; a map no DEF and no registered document backs
is removed, with an issue saying what was consulted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import omnisus as sus

DICIONARIOS = Path(sus.__file__).parent / "data" / "dicionarios"


def _decoded_fields():
    for path in sorted(DICIONARIOS.glob("*.yaml")):
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
        for field in raw["schema"]["fields"]:
            if field.get("x-decode"):
                yield path.stem, field


@pytest.mark.parametrize(
    ("dataset", "field"), [pytest.param(d, f, id=f"{d}.{f['name']}") for d, f in _decoded_fields()]
)
def test_every_code_map_has_an_authored_codes_claim(dataset, field) -> None:
    claims = (field.get("x-metadata") or {}).get("claims", [])
    (claim,) = [c for c in claims if c["target"] == "/field/codes"]
    if claim["method"] == "fixture-measure":
        issues = (field["x-metadata"]).get("issues", [])
        assert claim["status"] == "unreviewed" and claim["reviewer"] is None
        assert any(i["status"] == "open" for i in issues), "a measured map keeps an open issue"
    else:
        assert claim["evidence"], "a read map cites its source"


def _field(dataset: str, name: str) -> dict:
    raw = yaml.load((DICIONARIOS / f"{dataset}.yaml").read_text(), Loader=yaml.CSafeLoader)
    return next(f for f in raw["schema"]["fields"] if f["name"] == name)


@pytest.mark.parametrize(
    ("dataset", "name"),
    [
        ("sia_bpa_individualizado", "complex"),
        ("sim_obitos", "_source_release"),
        ("sih_aih_reduzida", "_source_release"),
    ],
)
def test_a_map_nothing_backs_is_gone(dataset, name) -> None:
    assert "x-decode" not in _field(dataset, name)


def test_complex_says_what_was_consulted() -> None:
    issues = _field("sia_bpa_individualizado", "complex")["x-metadata"]["issues"]
    (issue,) = issues
    assert issue["id"] == "complex-sem-def" and issue["status"] == "open"
    assert "Informe Técnico" in issue["description"]


@pytest.mark.parametrize(
    ("dataset", "name"),
    [
        ("sim_obitos", "esc2010"),
        ("sim_obitos", "escmae2010"),
        ("sinasc_nascidos_vivos", "stdnnova"),
    ],
)
def test_a_label_the_document_contradicts_is_a_conflicting_claim_with_an_issue(
    dataset, name
) -> None:
    field = _field(dataset, name)
    (claim,) = [c for c in field["x-metadata"]["claims"] if c["target"] == "/field/codes"]
    assert claim["status"] == "conflicting" and claim["evidence"]
    assert any(i["status"] == "open" for i in field["x-metadata"]["issues"])
