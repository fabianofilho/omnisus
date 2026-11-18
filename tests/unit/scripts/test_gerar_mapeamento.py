"""The mapping tables repeat what the package already says, one row per dataset, field
and issue. Each count is checked against ``sus.describe_datasets`` or the resolved
contract of ``sus.describe_dataset``, read from the packaged dictionaries.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from functools import cache
from pathlib import Path

import omnisus as sus

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "metadados" / "gerar_mapeamento.py"


@cache
def _module():
    spec = importlib.util.spec_from_file_location("gerar_mapeamento", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def _tables() -> dict[str, list[dict]]:
    return _module().build()


def test_every_dataset_of_the_registry_has_one_row_with_the_counts_of_the_table() -> None:
    table = sus.describe_datasets()
    bases = {row["base"]: row for row in _tables()["bases"]}
    assert sorted(bases) == sorted(table["name"])
    for row in table.iter_rows(named=True):
        base = bases[row["name"]]
        assert base["campos"] == row["fields"], row["name"]
        assert base["com_rotulo"] == row["labelled_fields"], row["name"]
        assert base["sistema"] == row["category"]
        assert base["com_rotulo"] == sum(
            base[f"rotulo_{status}"] for status in _module().STATUSES
        ), row["name"]


def test_a_field_row_repeats_the_claim_of_the_resolved_contract() -> None:
    campos = {row["chave"]: row for row in _tables()["campos"]}
    assert len(campos) == len(_tables()["campos"]) == sus.describe_datasets()["fields"].sum()
    item = next(
        f for f in sus.describe_dataset("sim_obitos")["fields"] if f["field"]["name"] == "sexo"
    )
    codes = next(c for c in item["claims"] if c["target"] == "/field/codes")
    row = campos["sim_obitos.sexo"]
    assert row["codigos"] == len(item["field"]["codes"]) > 0
    assert (row["status_codigos"], row["metodo_codigos"], row["revisor_codigos"]) == (
        codes["status"],
        codes["method"],
        codes["reviewer"],
    )
    assert row["aplicabilidade"] == item["applicability"]["status"]
    unlabelled = next(row for row in _tables()["campos"] if row["codigos"] == 0)
    assert unlabelled["status_codigos"] is None


def test_the_issue_rows_add_up_to_the_counts_of_each_dataset() -> None:
    by_base = Counter((row["base"], row["status"]) for row in _tables()["issues"])
    assert by_base
    for base in _tables()["bases"]:
        for status in ("open", "resolved"):
            assert base[f"issues_{status}"] == by_base[(base["base"], status)], base["base"]
    open_ids = {
        row["chave"]: row["issues_open"] for row in _tables()["campos"] if row["issues_open"]
    }
    for row in _tables()["issues"]:
        if row["status"] == "open":
            assert row["id"] in open_ids[f"{row['base']}.{row['campo']}"].split(", ")


def test_the_files_carry_the_script_and_no_path_of_the_machine(tmp_path) -> None:
    _module().main(tmp_path)
    for stem in ("bases", "campos", "issues"):
        document = json.loads((tmp_path / f"{stem}.json").read_text(encoding="utf-8"))
        assert document["rows"] == _tables()[stem]
        code, source, _ = document["meta"]
        assert code["value"] == SCRIPT.read_text(encoding="utf-8")
        assert source["value"].startswith(f"omnisus {sus.__version__}")
        assert str(ROOT) not in json.dumps(document)
