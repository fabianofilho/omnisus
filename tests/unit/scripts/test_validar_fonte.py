"""`scripts/metadados/validar_fonte.py`: audit a batch of sources for the analytical rules.

Real data: `sim_rr_2022_mini.dbc` and `sim_rr_2023_mini.dbc` are DORR2022.dbc and
DORR2023.dbc, both in SIM `validated_sources`; DORR2023 is the SIM reference.
`sinan_chagas_br_2023.dbc` is CHAGBR23.dbc, the validated national, preliminary source.
`sih_rr_2024_01_mini.dbc` is RDRR2401.dbc with GESTOR_CPF blanked (SHA-256 5e6f0c99…), so
it is not the validated source (37741f8b…). The fake server also lists the DORR2022 bytes
as AC 2022 and AL 2022, to accept two new SHA-256 in one edit, and the CHAGBR23 bytes as
the national 2022 scope, to accept a new national source.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

import omnisus as sus
from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp.inventory import ResolvedSource
from tests.support.datasus_names import filename_for
from tests.support.listings import fixture_entry

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "metadados" / "validar_fonte.py"
DBC = ROOT / "tests" / "fixtures" / "dbc"
DICIONARIOS = ROOT / "src" / "omnisus" / "data" / "dicionarios"
SIM_RR_2022 = ScopeKey(uf="RR", ano=2022)
SIM_RR_2023 = ScopeKey(uf="RR", ano=2023)
SIH_RR_2024_01 = ScopeKey(uf="RR", ano=2024, mes=1)
SINAN_2023 = ScopeKey(uf=None, ano=2023)
SERVED = {
    ("sim_obitos", SIM_RR_2022): "sim_rr_2022_mini",
    ("sim_obitos", SIM_RR_2023): "sim_rr_2023_mini",
    ("sim_obitos", ScopeKey(uf="AC", ano=2022)): "sim_rr_2022_mini",
    ("sim_obitos", ScopeKey(uf="AL", ano=2022)): "sim_rr_2022_mini",
    ("sih_aih_reduzida", SIH_RR_2024_01): "sih_rr_2024_01_mini",
    ("sinan_chagas", SINAN_2023): "sinan_chagas_br_2023",
    ("sinan_chagas", ScopeKey(uf=None, ano=2022)): "sinan_chagas_br_2023",
}
RELEASES = {"sinan_chagas": "prelim"}


def load_script():
    spec = importlib.util.spec_from_file_location("validar_fonte", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The script against a copy of the dictionaries and a fake server listing fixtures."""
    module = load_script()
    calls = {"list": 0, "fetch": []}
    contents = {}

    def list_sources(d, **_kw):
        calls["list"] += 1
        sources = {}
        for (dataset, scope), fixture in SERVED.items():
            if dataset != d.name:
                continue
            raw = (DBC / f"{fixture}.dbc").read_bytes()
            release = RELEASES.get(dataset, "final")
            entry = fixture_entry(d.directories()[release], filename_for(d, scope, None), raw)
            contents[entry.path] = raw
            sources[scope] = ResolvedSource(release=release, files=(entry,))
        return sources

    async def fetch(entry, **_kw):
        calls["fetch"].append(entry.name)
        return contents[entry.path]

    monkeypatch.setattr(module, "list_sources", list_sources)
    monkeypatch.setattr(module, "fetch_dbc_bytes", fetch)
    dictionaries = tmp_path / "dicionarios"
    shutil.copytree(DICIONARIOS, dictionaries)
    paths = {
        "dictionaries": dictionaries,
        "evidence": tmp_path / "evidence",
        "downloads": tmp_path / "downloads",
    }
    return module, paths, calls


def _validated(dictionaries: Path, dataset: str) -> list[dict]:
    raw = yaml.load(
        (dictionaries / f"{dataset}.yaml").read_text(encoding="utf-8"), Loader=yaml.CSafeLoader
    )
    return raw["x-analytics"]["validated_sources"]


def _sha(fixture: str) -> str:
    return hashlib.sha256((DBC / f"{fixture}.dbc").read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _folder(evidence: Path, name: str) -> Path:
    return evidence / f"{datetime.now(UTC):%Y-%m-%d}-validacao-{name}"


def test_a_batch_lists_the_server_once_and_writes_one_evidence_folder(workspace) -> None:
    module, paths, calls = workspace

    code = module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023"], **paths)

    assert code == 0
    assert calls["list"] == 1
    folder = _folder(paths["evidence"], "sim_obitos-2022-2023")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert {(m["url"].rsplit("/", 1)[1], m["sha256"]) for m in manifest} == {
        ("DORR2022.dbc", _sha("sim_rr_2022_mini")),
        ("DORR2023.dbc", _sha("sim_rr_2023_mini")),
    }
    assert [(r["escopo"], r["decisao"]) for r in _rows(folder / "escopos.csv")] == [
        ("RR_2022", "aceito"),
        ("RR_2023", "aceito"),
    ]
    assert not list(paths["downloads"].glob("*.dbc"))


def test_the_evidence_records_no_local_path(workspace, tmp_path: Path) -> None:
    module, paths, _calls = workspace

    module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2023", "--fim", "2023"], **paths)

    for written in paths["evidence"].rglob("*"):
        if written.is_file():
            text = written.read_text(encoding="utf-8")
            assert str(tmp_path) not in text, written.name
            assert '"path"' not in text, written.name


def test_every_status_column_reconciles_with_the_rows_of_its_scope(workspace) -> None:
    module, paths, _calls = workspace

    module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023"], **paths)

    folder = _folder(paths["evidence"], "sim_obitos-2022-2023")
    rows = {r["escopo"]: int(r["linhas"]) for r in _rows(folder / "escopos.csv")}
    assert rows == {"RR_2022": 3246, "RR_2023": 3311}
    totals: dict[tuple[str, str], int] = {}
    for r in _rows(folder / "estados.csv"):
        key = (r["escopo"], r["coluna"])
        totals[key] = totals.get(key, 0) + int(r["n"])
    assert {"idade_status", "sexo_status", "dtobito_data_status"} <= {c for _, c in totals}
    assert all(n == rows[escopo] for (escopo, _), n in totals.items())
    referencia = json.loads((folder / "referencia.json").read_text(encoding="utf-8"))
    assert referencia["referencia"] == "RR_2023"
    assert referencia["expressions"] and referencia["schema"]


def test_accept_appends_every_accepted_scope_in_one_edit(workspace) -> None:
    module, paths, _calls = workspace
    yaml_path = paths["dictionaries"] / "sim_obitos.yaml"
    before = yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)

    code = module.main(
        ["sim_obitos", "--ufs", "AC,AL", "--inicio", "2022", "--fim", "2022", "--accept"],
        **paths,
    )

    assert code == 0
    after = yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=yaml.CSafeLoader)
    added = after["x-analytics"]["validated_sources"][-2:]
    del after["x-analytics"]["validated_sources"][-2:]
    sha = _sha("sim_rr_2022_mini")
    assert added == [
        {"uf": "AC", "ano": 2022, "release": "final", "source_sha256": sha},
        {"uf": "AL", "ano": 2022, "release": "final", "source_sha256": sha},
    ]
    assert after == before


def test_an_already_validated_source_is_not_added_twice(workspace) -> None:
    module, paths, _calls = workspace
    before = _validated(paths["dictionaries"], "sim_obitos")

    code = module.main(
        ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023", "--accept"], **paths
    )

    assert code == 0
    assert _validated(paths["dictionaries"], "sim_obitos") == before


def test_a_scope_the_server_does_not_list_downloads_and_writes_nothing(workspace) -> None:
    module, paths, calls = workspace

    code = module.main(
        [
            "sih_aih_reduzida",
            "--ufs",
            "RR,AC",
            "--inicio",
            "2024-01",
            "--fim",
            "2024-01",
            "--accept",
        ],
        **paths,
    )

    assert code == 1
    assert calls["fetch"] == []
    assert not paths["evidence"].exists()
    assert _validated(paths["dictionaries"], "sih_aih_reduzida") == _validated(
        DICIONARIOS, "sih_aih_reduzida"
    )


def test_an_interrupted_batch_resumes_without_downloading_again(workspace, monkeypatch) -> None:
    module, paths, calls = workspace
    real_fetch = module.fetch_dbc_bytes

    async def fails_on_the_second(entry, **kw):
        if len(calls["fetch"]) == 1:
            raise ConnectionError("530 too many connections")
        return await real_fetch(entry, **kw)

    monkeypatch.setattr(module, "fetch_dbc_bytes", fails_on_the_second)
    argv = ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023"]
    with pytest.raises(ConnectionError):
        module.main(argv, **paths)
    assert calls["fetch"] == ["DORR2023.dbc"]

    monkeypatch.setattr(module, "fetch_dbc_bytes", real_fetch)
    assert module.main(argv, **paths) == 0

    assert calls["fetch"] == ["DORR2023.dbc", "DORR2022.dbc"]
    assert not list(paths["downloads"].glob("parcial-*"))


def test_the_window_takes_months_only_for_a_monthly_dataset() -> None:
    module = load_script()
    sih, sim = sus.resolve("sih_aih_reduzida"), sus.resolve("sim_obitos")

    escopos = module.janela(sih, ["RR"], (2024, 11), (2025, 2))

    assert [str(s) for s in escopos] == ["RR_2024_11", "RR_2024_12", "RR_2025_01", "RR_2025_02"]
    assert [str(s) for s in module.janela(sim, ["RR", "SP"], (2024, None), (2024, None))] == [
        "RR_2024",
        "SP_2024",
    ]
    with pytest.raises(ValueError, match="AAAA-MM"):
        module.janela(sih, ["RR"], (2024, None), (2025, None))


@pytest.fixture(scope="module")
def auditado(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The candidate audit of the real DORR2023, under its server name, as the batch runs it."""
    module = load_script()
    path = tmp_path_factory.mktemp("auditoria") / "DORR2023.dbc"
    raw = (DBC / "sim_rr_2023_mini.dbc").read_bytes()
    path.write_bytes(raw)
    item = {
        "dataset": "sim_obitos",
        "path": str(path),
        "url": "ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "scope": {"uf": "RR", "ano": 2023, "mes": None},
        "release": "final",
    }
    return module.audit(item, candidate=True)


def test_a_scope_like_its_reference_is_accepted(auditado) -> None:
    regra = sus.describe_dataset("sim_obitos")["analytics"]["age"]
    assert load_script().bloqueios(auditado, auditado, regra) == []


def test_a_schema_other_than_the_reference_blocks(auditado) -> None:
    regra = sus.describe_dataset("sim_obitos")["analytics"]["age"]
    referencia = {**auditado, "schema": {**auditado["schema"], "fonte_orc": "VARCHAR"}}

    (motivo,) = load_script().bloqueios(auditado, referencia, regra)

    assert motivo.startswith("schema difere da referência: faltam ['fonte_orc']")


def test_an_unknown_sex_code_blocks(auditado) -> None:
    regra = sus.describe_dataset("sim_obitos")["analytics"]["age"]
    estados = {**auditado["states"], "sexo_status": [{"status": "unsupported", "n": 2}]}

    motivos = load_script().bloqueios({**auditado, "states": estados}, auditado, regra)

    assert motivos == ["sexo não suportado em 2 linhas"]


def test_an_undeclared_age_unit_blocks_and_an_out_of_range_age_does_not(auditado) -> None:
    """On the real DORR2023 audit: SIM unit 6 is not declared by the rule (units 0 to 5,
    9 ignored); 312 is the declared unit month above its bound of 11 months."""
    module = load_script()
    regra = sus.describe_dataset("sim_obitos")["analytics"]["age"]

    def com(valor: str) -> dict:
        linha = {"value": valor, "unit": None, "status": "unsupported", "n": 1}
        return {**auditado, "uninterpreted_age_codes": [linha]}

    assert module.bloqueios(com("610"), auditado, regra) == [
        "idade '610' com unidade não declarada (1)"
    ]
    assert module.bloqueios(com("312"), auditado, regra) == []


def test_only_an_undeclared_age_unit_blocks() -> None:
    """The documented SIH codes (x-analytics.age notes: 230 and 312 unsupported, 000 and
    999 invalid composites) are reported; a unit the rule does not declare blocks."""
    module = load_script()
    regra = sus.describe_dataset("sih_aih_reduzida")["analytics"]["age"]

    assert module.motivo_idade(regra, "30", "2") == "fora da faixa da unidade"
    assert module.motivo_idade(regra, "12", "3") == "fora da faixa da unidade"
    assert module.motivo_idade(regra, "00", "0") == "composta inválida"
    assert module.motivo_idade(regra, "99", "9") == "composta inválida"
    assert module.motivo_idade(regra, "4A", "4") == "texto malformado"
    assert module.motivo_idade(regra, "10", "7") == "unidade não declarada"


def test_a_reference_outside_the_window_is_audited_but_not_decided(workspace) -> None:
    module, paths, _calls = workspace

    code = module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2022"], **paths)

    assert code == 0
    folder = _folder(paths["evidence"], "sim_obitos-2022-2022")
    assert [r["escopo"] for r in _rows(folder / "escopos.csv")] == ["RR_2022"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(m["url"].rsplit("/", 1)[1] for m in manifest) == ["DORR2022.dbc", "DORR2023.dbc"]


def test_a_scope_split_into_several_files_is_blocked_without_download(
    workspace, monkeypatch
) -> None:
    """The evidence names each part the server lists, with its size, for the audit by hand."""
    module, paths, calls = workspace
    served = module.list_sources
    partes = []

    def split(d, **kw):
        sources = served(d, **kw)
        (entry,) = sources[SIM_RR_2022].files
        partes[:] = [entry, entry]
        sources[SIM_RR_2022] = ResolvedSource(release="final", files=tuple(partes))
        return sources

    monkeypatch.setattr(module, "list_sources", split)

    code = module.main(
        ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023", "--accept"], **paths
    )

    assert code == 2
    assert calls["fetch"] == ["DORR2023.dbc"]
    folder = _folder(paths["evidence"], "sim_obitos-2022-2023")
    (bloqueado,) = [r for r in _rows(folder / "escopos.csv") if r["decisao"] == "bloqueado"]
    assert bloqueado["escopo"] == "RR_2022"
    listadas = "; ".join(f"{p.path}, {p.size_bytes} bytes" for p in partes)
    assert bloqueado["motivos"] == f"dividido em 2 arquivos ({listadas}); audite à mão"


def test_a_failing_reference_stops_before_any_decision(workspace, monkeypatch) -> None:
    """A download cut short (the first 512 bytes of the real DORR2023, a malformed-input
    case of the decoder) fails the reference audit; the batch stops before downloading more."""
    module, paths, calls = workspace
    real_fetch = module.fetch_dbc_bytes

    async def truncated(entry, **kw):
        raw = await real_fetch(entry, **kw)
        return raw[:512] if entry.name == "DORR2023.dbc" else raw

    monkeypatch.setattr(module, "fetch_dbc_bytes", truncated)

    code = module.main(
        ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023", "--accept"], **paths
    )

    assert code == 1
    assert calls["fetch"] == ["DORR2023.dbc"]
    assert not paths["evidence"].exists()
    assert _validated(paths["dictionaries"], "sim_obitos") == _validated(DICIONARIOS, "sim_obitos")


def test_a_file_republished_between_runs_is_audited_again(workspace, monkeypatch) -> None:
    """The first run stops after AC 2022; then the server lists AC 2022 with other bytes
    (the real DORR2023), so the resumed run downloads it again and keeps the reference."""
    module, paths, calls = workspace
    real_fetch = module.fetch_dbc_bytes

    async def fails_on_the_third(entry, **kw):
        if len(calls["fetch"]) == 2:
            raise ConnectionError("530 too many connections")
        return await real_fetch(entry, **kw)

    monkeypatch.setattr(module, "fetch_dbc_bytes", fails_on_the_third)
    argv = ["sim_obitos", "--ufs", "AC,AL", "--inicio", "2022", "--fim", "2022"]
    with pytest.raises(ConnectionError):
        module.main(argv, **paths)
    assert calls["fetch"] == ["DORR2023.dbc", "DOAC2022.dbc"]

    monkeypatch.setattr(module, "fetch_dbc_bytes", real_fetch)
    monkeypatch.setitem(SERVED, ("sim_obitos", ScopeKey(uf="AC", ano=2022)), "sim_rr_2023_mini")
    assert module.main(argv, **paths) == 0

    assert calls["fetch"] == ["DORR2023.dbc", "DOAC2022.dbc", "DOAC2022.dbc", "DOAL2022.dbc"]


def test_a_new_file_for_a_validated_scope_is_added_next_to_the_old_one(
    workspace, monkeypatch
) -> None:
    """SIM RR 2022 is validated with DORR2022 (6643344f…); served with other real bytes, the
    new SHA-256 is appended and the old one stays, for lakes that imported it."""
    module, paths, _calls = workspace
    monkeypatch.setitem(SERVED, ("sim_obitos", SIM_RR_2022), "sim_rr_2023_mini")
    before = _validated(paths["dictionaries"], "sim_obitos")

    code = module.main(
        ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2022", "--accept"], **paths
    )

    assert code == 0
    after = _validated(paths["dictionaries"], "sim_obitos")
    assert after[: len(before)] == before
    assert after[len(before) :] == [
        {"uf": "RR", "ano": 2022, "release": "final", "source_sha256": _sha("sim_rr_2023_mini")}
    ]


def test_a_republished_reference_stops_the_batch(workspace, monkeypatch) -> None:
    """The reference RR 2023 served with other real bytes (DORR2022) is not the file
    validated by hand: nothing is compared against it."""
    module, paths, calls = workspace
    monkeypatch.setitem(SERVED, ("sim_obitos", SIM_RR_2023), "sim_rr_2022_mini")

    code = module.main(
        ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023", "--accept"], **paths
    )

    assert code == 1
    assert calls["fetch"] == ["DORR2023.dbc"]
    assert not paths["evidence"].exists()
    assert _validated(paths["dictionaries"], "sim_obitos") == _validated(DICIONARIOS, "sim_obitos")


def test_a_failed_audit_is_retried_on_the_next_run(workspace, monkeypatch) -> None:
    """A download cut short fails the reference; the next run downloads it again instead of
    reusing the cached failure."""
    module, paths, calls = workspace
    real_fetch = module.fetch_dbc_bytes

    async def truncated(entry, **kw):
        return (await real_fetch(entry, **kw))[:512]

    argv = ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023"]
    monkeypatch.setattr(module, "fetch_dbc_bytes", truncated)
    assert module.main(argv, **paths) == 1
    monkeypatch.setattr(module, "fetch_dbc_bytes", real_fetch)

    assert module.main(argv, **paths) == 0
    assert calls["fetch"] == ["DORR2023.dbc", "DORR2023.dbc", "DORR2022.dbc"]


def test_a_cached_audit_under_another_dictionary_is_done_again(workspace, monkeypatch) -> None:
    """The run stops after the reference; the cached audit then carries another
    metadata_hash (a dictionary changed in between), so the resumed run audits it again."""
    module, paths, calls = workspace
    real_fetch = module.fetch_dbc_bytes

    async def fails_on_the_second(entry, **kw):
        if len(calls["fetch"]) == 1:
            raise ConnectionError("530 too many connections")
        return await real_fetch(entry, **kw)

    monkeypatch.setattr(module, "fetch_dbc_bytes", fails_on_the_second)
    argv = ["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2023"]
    with pytest.raises(ConnectionError):
        module.main(argv, **paths)
    (parcial,) = paths["downloads"].glob("parcial-*.jsonl")
    registro = json.loads(parcial.read_text(encoding="utf-8"))
    registro["resultado"]["metadata_hash"] = "outro dicionário"
    parcial.write_text(json.dumps(registro) + "\n", encoding="utf-8")

    monkeypatch.setattr(module, "fetch_dbc_bytes", real_fetch)
    assert module.main(argv, **paths) == 0
    assert calls["fetch"] == ["DORR2023.dbc", "DORR2023.dbc", "DORR2022.dbc"]


def test_a_second_run_does_not_overwrite_the_evidence_of_the_first(workspace) -> None:
    """Same day and window, other UFs: the folder name is the same, so the second run stops
    before listing the server instead of replacing the first run's evidence."""
    module, paths, calls = workspace
    assert (
        module.main(["sim_obitos", "--ufs", "AC,AL", "--inicio", "2022", "--fim", "2022"], **paths)
        == 0
    )
    folder = _folder(paths["evidence"], "sim_obitos-2022-2022")
    manifest = (folder / "manifest.json").read_bytes()

    code = module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2022", "--fim", "2022"], **paths)

    assert code == 1
    assert (folder / "manifest.json").read_bytes() == manifest
    assert calls["list"] == 1
    assert len(calls["fetch"]) == 3


def test_an_empty_window_stops_before_listing_the_server(workspace, capsys) -> None:
    module, paths, calls = workspace

    code = module.main(["sim_obitos", "--ufs", "RR", "--inicio", "2023", "--fim", "2022"], **paths)

    assert code == 1
    assert "nenhum escopo" in capsys.readouterr().err
    assert calls["list"] == 0
    assert not paths["evidence"].exists()


def test_a_dataset_without_a_known_reference_asks_for_one(workspace, capsys) -> None:
    module, paths, calls = workspace

    code = module.main(
        ["sinasc_nascidos_vivos", "--ufs", "RR", "--inicio", "2023", "--fim", "2023"], **paths
    )

    assert code == 1
    assert "--referencia" in capsys.readouterr().err
    assert calls["list"] == 0


def test_a_national_dataset_runs_without_ufs_against_its_reference(workspace) -> None:
    """SINAN Chagas 2023 is national and preliminary; its validated entry records `uf: null`,
    so accepting the same file again adds nothing."""
    module, paths, _calls = workspace
    before = _validated(paths["dictionaries"], "sinan_chagas")

    code = module.main(
        [
            "sinan_chagas",
            "--inicio",
            "2023",
            "--fim",
            "2023",
            "--referencia",
            "national_2023",
            "--accept",
        ],
        **paths,
    )

    assert code == 0
    folder = _folder(paths["evidence"], "sinan_chagas-2023-2023")
    assert [(r["escopo"], r["decisao"]) for r in _rows(folder / "escopos.csv")] == [
        ("national_2023", "aceito")
    ]
    assert _validated(paths["dictionaries"], "sinan_chagas") == before


def test_a_new_national_source_is_recorded_with_a_null_uf(workspace) -> None:
    """The national entries of the dictionaries carry ``uf: null``: the library reads
    ``source["uf"]`` to match a scope (``analytics._confirmed``)."""
    module, paths, _calls = workspace
    argv = ["sinan_chagas", "--inicio", "2022", "--fim", "2023", "--referencia", "national_2023"]

    code = module.main([*argv, "--accept"], **paths)

    assert code == 0
    assert _validated(paths["dictionaries"], "sinan_chagas")[-1] == {
        "uf": None,
        "ano": 2022,
        "release": "prelim",
        "source_sha256": _sha("sinan_chagas_br_2023"),
    }


def test_ufs_are_refused_for_a_national_dataset(workspace, capsys) -> None:
    module, paths, calls = workspace

    code = module.main(
        ["sinan_chagas", "--ufs", "RR", "--inicio", "2023", "--fim", "2023"], **paths
    )

    assert code == 1
    assert "nacional" in capsys.readouterr().err
    assert calls["list"] == 0
