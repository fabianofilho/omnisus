"""Generate mini DBC test fixtures by downloading real DATASUS files.

Run manually once. Outputs are committed to tests/fixtures/dbc/.
We use the smallest UF (RR — Roraima) and recent years to keep fixtures tiny.

Downloads over anonymous FTP (ftp.datasus.gov.br); the HTTP mirror at
datasus.saude.gov.br/dissemin/publicos is 404. The production fetcher in
``omnisus.sources.datasus_ftp.fetch`` uses the same transport.

Every remote path comes from the registry row, so this script covers whatever
the registry covers. It used to carry a hand-copied path map for 5 of the 11
datasets, which meant ``conftest.py``'s advice — "run scripts/build_fixtures.py"
— was a dead end for the other 6.
"""

from __future__ import annotations

import ftplib
import io
from pathlib import Path

from omnisus.sources._base import ScopeKey
from omnisus.sources.datasus_ftp._ftp import ftp_host
from omnisus.sources.datasus_ftp.datasets import resolve
from omnisus.sources.datasus_ftp.inventory import list_sources

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "dbc"

FTP_TIMEOUT = 60

TARGETS: list[tuple[str, ScopeKey, str]] = [
    ("sinan_chagas", ScopeKey(uf=None, ano=2023), "sinan_chagas_br_2023.dbc"),
    ("sinan_hanseniase", ScopeKey(uf=None, ano=2026), "sinan_hanseniase_br_2026.dbc"),
    (
        "sinan_tuberculose",
        ScopeKey(uf=None, ano=2020),
        "sinan_tuberculose_br_2020_excerpt.dbc",
    ),
    ("sinan_dengue", ScopeKey(uf=None, ano=2023), "sinan_dengue_br_2023_excerpt.dbc"),
    ("sinan_violencia", ScopeKey(uf=None, ano=2023), "sinan_violencia_br_2023_excerpt.dbc"),
    ("sim_obitos", ScopeKey(uf="RR", ano=2023), "sim_rr_2023_mini.dbc"),
    ("sinasc_nascidos_vivos", ScopeKey(uf="RR", ano=2022), "sinasc_rr_2022_mini.dbc"),
    ("sih_aih_reduzida", ScopeKey(uf="RR", ano=2024, mes=1), "sih_rr_2024_01_mini.dbc"),
    ("sia_bpa_individualizado", ScopeKey(uf="RR", ano=2024, mes=1), "sia_bi_rr_2024_01_mini.dbc"),
    ("sia_apac_medicamentos", ScopeKey(uf="RR", ano=2024, mes=1), "sia_am_rr_2024_01_mini.dbc"),
    ("sia_apac_quimioterapia", ScopeKey(uf="RR", ano=2024, mes=1), "sia_aq_rr_2024_01_mini.dbc"),
    (
        "sia_apac_tratamento_dialitico",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sia_atd_rr_2024_01_mini.dbc",
    ),
    ("sia_apac_laudos_diversos", ScopeKey(uf="RR", ano=2024, mes=1), "sia_ad_rr_2024_01_mini.dbc"),
    ("sia_psicossocial", ScopeKey(uf="RR", ano=2024, mes=1), "sia_ps_rr_2024_01_mini.dbc"),
    (
        "sia_apac_cirurgia_bariatrica",
        ScopeKey(uf="SP", ano=2024, mes=1),
        "sia_abo_sp_2024_01_mini.dbc",
    ),
    ("cnes_estabelecimentos", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_rr_2024_01_mini.dbc"),
    (
        "sia_producao_ambulatorial",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sia_pa_rr_2024_01_mini.dbc",
    ),
    (
        "sia_producao_ambulatorial_1994_2007",
        ScopeKey(uf="RR", ano=2007, mes=12),
        "sia_pa_rr_2007_12_mini.dbc",
    ),
    ("sih_aih_rejeitada", ScopeKey(uf="RR", ano=2024, mes=1), "sih_rj_rr_2024_01_mini.dbc"),
    (
        "sih_servicos_profissionais",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sih_sp_rr_2024_01_mini.dbc",
    ),
    ("sih_aih_rejeitada_erro", ScopeKey(uf="RR", ano=2024, mes=1), "sih_er_rr_2024_01_mini.dbc"),
    (
        "sih_aih_reduzida_1992_2007",
        ScopeKey(uf="RR", ano=2007, mes=12),
        "sih_rd_rr_2007_12_mini.dbc",
    ),
    (
        "cnes_dados_complementares",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "cnes_dc_rr_2024_01_mini.dbc",
    ),
    ("cnes_equipamentos", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_eq_rr_2024_01_mini.dbc"),
    ("cnes_equipes", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_ep_rr_2024_01_mini.dbc"),
    ("cnes_gestao_metas", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_gm_rr_2024_01_mini.dbc"),
    ("cnes_habilitacoes", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_hb_rr_2024_01_mini.dbc"),
    ("cnes_incentivos", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_in_rr_2024_01_mini.dbc"),
    ("cnes_leitos", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_lt_rr_2024_01_mini.dbc"),
    ("cnes_regras_contratuais", ScopeKey(uf="RR", ano=2024, mes=1), "cnes_rc_rr_2024_01_mini.dbc"),
    (
        "cnes_servicos_especializados",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "cnes_sr_rr_2024_01_mini.dbc",
    ),
    (
        "cnes_estabelecimentos_ensino",
        ScopeKey(uf="RR", ano=2019, mes=12),
        "cnes_ee_rr_2019_12_mini.dbc",
    ),
    (
        "cnes_estabelecimentos_filantropicos",
        ScopeKey(uf="AP", ano=2024, mes=1),
        "cnes_ef_ap_2024_01_mini.dbc",
    ),
    ("sim_obitos_fetais", ScopeKey(uf=None, ano=2023), "sim_dofet_br_2023_excerpt.dbc"),
    ("sim_obitos_externos", ScopeKey(uf=None, ano=2023), "sim_doext_br_2023_excerpt.dbc"),
    ("sim_obitos_infantis", ScopeKey(uf=None, ano=2023), "sim_doinf_br_2023_excerpt.dbc"),
    ("sim_obitos_maternos", ScopeKey(uf=None, ano=2023), "sim_domat_br_2023_mini.dbc"),
    ("sim_obitos_cid9", ScopeKey(uf="RR", ano=1995), "sim_cid9_rr_1995_mini.dbc"),
    ("sinasc_1994_1995", ScopeKey(uf="RR", ano=1995), "sinasc_rr_1995_mini.dbc"),
    (
        "sia_apac_acompanhamento_bariatrica",
        ScopeKey(uf="SE", ano=2025, mes=7),
        "sia_ab_se_2025_07_mini.dbc",
    ),
    (
        "sia_apac_fistula_arteriovenosa",
        ScopeKey(uf="RR", ano=2024, mes=1),
        "sia_acf_rr_2024_01_mini.dbc",
    ),
    (
        "sia_apac_acompanhamento_multiprofissional",
        ScopeKey(uf="DF", ano=2024, mes=1),
        "sia_amp_df_2024_01_mini.dbc",
    ),
    ("sia_apac_nefrologia", ScopeKey(uf="PA", ano=2014, mes=10), "sia_an_pa_2014_10_mini.dbc"),
    ("sia_apac_radioterapia", ScopeKey(uf="AC", ano=2024, mes=1), "sia_ar_ac_2024_01_mini.dbc"),
    ("sia_atencao_domiciliar", ScopeKey(uf="MA", ano=2018, mes=10), "sia_sad_ma_2018_10_mini.dbc"),
]
"""One entry per registry row. ``tests/unit/test_public_api.py`` asserts this
list and its own ``_FIXTURE_FOR`` agree, so neither can drift from the other
or from the registry."""

EXCERPTS: dict[str, int] = {
    "sinan_tuberculose_br_2020_excerpt.dbc": 3000,
    "sim_dofet_br_2023_excerpt.dbc": 1000,
    "sim_doext_br_2023_excerpt.dbc": 1000,
    "sim_doinf_br_2023_excerpt.dbc": 1000,
}
"""Fixtures too large to commit whole: file name -> records kept (scripts/dbc_excerpt.py)."""


def fetch_via_ftp(dataset: str, scope: ScopeKey) -> bytes:
    source = list_sources(resolve(dataset), refresh=True)[scope]
    if len(source.files) != 1:
        raise SystemExit(
            f"{dataset} {scope} is split into parts; build an excerpt with scripts/dbc_excerpt.py"
        )
    entry = source.files[0]
    buf = io.BytesIO()
    with ftplib.FTP(ftp_host(), timeout=FTP_TIMEOUT) as ftp:
        ftp.login()
        ftp.cwd(entry.parent)
        ftp.retrbinary(f"RETR {entry.name}", buf.write)
    return buf.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for dataset, scope, fname in TARGETS:
        out_file = OUT / fname
        if out_file.exists():
            print(f"skip (exists): {out_file}")
            continue
        print(f"fetching {dataset} {scope} -> {out_file}")
        try:
            data = fetch_via_ftp(dataset, scope)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        if fname in EXCERPTS:
            from dbc_excerpt import excerpt_dbc

            data = excerpt_dbc(data, EXCERPTS[fname])
        out_file.write_bytes(data)
        print(f"  wrote {len(data) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
