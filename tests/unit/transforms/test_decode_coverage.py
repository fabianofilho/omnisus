"""Exact-key decode coverage on every real mini fixture."""

from __future__ import annotations

from importlib.resources import files

import duckdb
import pytest

from omnisus.sources.datasus_ftp.parse import dbc_bytes_to_lazyframe
from omnisus.transforms.dictionaries import Uncovered, decode_coverage, load_dicionario

# (dataset, fixture) -> every (field, value, rows) that no x-decode key matches exactly.
# Counted on 2026-09-21 after gerar_decode_cnv.py. What remains are fields no CNV binds
# (hand maps kept) or fields listed in vinculos.json `sem_cnv`.
REMAINING = {
    ("cnes_estabelecimentos", "cnes_rr_2024_01_mini"): [],
    ("sia_apac_cirurgia_bariatrica", "sia_abo_sp_2024_01_mini"): [],
    ("sia_apac_laudos_diversos", "sia_ad_rr_2024_01_mini"): [],
    ("sia_apac_medicamentos", "sia_am_rr_2024_01_mini"): [("ap_coidade", "5", 1)],
    ("sia_apac_quimioterapia", "sia_aq_rr_2024_01_mini"): [],
    ("sia_apac_tratamento_dialitico", "sia_atd_rr_2024_01_mini"): [],
    ("sia_bpa_individualizado", "sia_bi_rr_2024_01_mini"): [],
    # tpidadepac: the only tables for it read 3 characters (issue tpidadepac-sem-tabela).
    ("sia_bpa_individualizado", "sia_bi_rr_2022_01_mini"): [
        ("tpidadepac", "5", 7),
        ("tpidadepac", "9", 2),
    ],
    ("sia_bpa_individualizado", "sia_bi_mg_2024_12_part1_excerpt"): [],
    ("sia_bpa_individualizado", "sia_bi_mg_2024_12_part2_excerpt"): [],
    ("sia_psicossocial", "sia_ps_rr_2024_01_mini"): [
        ("tp_droga", "", 358),
        ("tp_droga", "AO", 907),
        ("tp_droga", "CO", 2),
    ],
    # homonimo 2 is on no source page (issue homonimo-sem-fonte).
    ("sih_aih_reduzida", "sih_rr_2024_01_mini"): [("homonimo", "2", 39)],
    ("sim_obitos", "sim_rr_2023_mini"): [
        ("esc2010", "", 438),
        ("escmae2010", "", 3027),
        ("assistmed", "", 297),
        ("tpresginfo", "", 3296),
        ("tpnivelinv", "", 3038),
        ("morteparto", "", 2980),
        ("altcausa", "", 3015),
    ],
    ("sim_obitos", "sim_rr_2022_mini"): [
        ("esc2010", "", 359),
        ("escmae2010", "", 3029),
        ("assistmed", "", 348),
        ("tpresginfo", "", 3223),
        ("tpnivelinv", "", 2973),
        ("morteparto", "", 3009),
        ("altcausa", "", 3040),
    ],
    # SINAN: blank stays undecoded unless a source names it; 0 in cs_raca and
    # cs_gestant is on no page of the Notificação Individual v5 (pp. 4-5).
    ("sinan_chagas", "sinan_chagas_br_2023"): [
        ("cs_gestant", "", 1),
        ("cs_raca", "", 52),
        ("cs_escol_n", "", 575),
        ("tpautocto", "", 5452),
        ("doenca_tra", "", 5611),
        ("classi_fin", "", 164),
        ("criterio", "", 1006),
        ("evolucao", "", 1286),
    ],
    ("sinan_hanseniase", "sinan_hanseniase_br_2026"): [
        ("cs_gestant", "0", 1),
        ("cs_raca", "0", 74),
        ("cs_flxret", "", 10354),
        ("migrado_w", "", 10354),
    ],
    # TUBEBR20 excerpt: pop_saude and pop_imig 3 and bac_apos_6 0 are on no page of the
    # TB dictionary (pp. 3, 18); every other gap is a blank.
    ("sinan_tuberculose", "sinan_tuberculose_br_2020_excerpt"): [
        ("cs_raca", "", 2),
        ("cs_escol_n", "", 29),
        ("cs_flxret", "", 3000),
        ("migrado_w", "", 3000),
        ("raiox_tora", "", 4),
        ("extrapu1_n", "", 2793),
        ("agravaids", "", 8),
        ("agravalcoo", "", 5),
        ("agravdiabe", "", 7),
        ("agravdoenc", "", 7),
        ("agravoutra", "", 2792),
        ("hiv", "", 30),
        ("histopatol", "", 589),
        ("bacilosc_1", "", 139),
        ("bacilosc_2", "", 152),
        ("bacilosc_3", "", 160),
        ("bacilosc_4", "", 166),
        ("bacilosc_5", "", 175),
        ("bacilosc_6", "", 173),
        ("tratsup_at", "", 3000),
        ("situa_ence", "", 31),
        ("pop_liber", "", 4),
        ("pop_rua", "", 6),
        ("pop_saude", "", 6),
        ("pop_saude", "3", 304),
        ("pop_imig", "", 6),
        ("pop_imig", "3", 51),
        ("benef_gov", "", 2779),
        ("agravdroga", "", 7),
        ("agravtabac", "", 3),
        ("test_molec", "", 344),
        ("test_sensi", "", 174),
        ("bac_apos_6", "", 2951),
        ("bac_apos_6", "0", 1),
        ("transf", "", 2943),
    ],
    # tpdocresp 0 is not in the Estrutura (issue tpdocresp-0-sem-fonte).
    ("sinasc_nascidos_vivos", "sinasc_rr_2022_mini"): [
        ("tpdocresp", "", 1),
        ("tpdocresp", "0", 20),
    ],  # CNES, SIH and SIA rows: only fields whose every non-blank fixture value is a CNV
    # key were bound, and these files store blanks as NULL.
    ("sia_producao_ambulatorial", "sia_pa_rr_2024_01_mini"): [],
    ("sih_aih_rejeitada", "sih_rj_rr_2024_01_mini"): [],
    ("sih_servicos_profissionais", "sih_sp_rr_2024_01_mini"): [],
    ("cnes_dados_complementares", "cnes_dc_rr_2024_01_mini"): [],
    ("cnes_equipamentos", "cnes_eq_rr_2024_01_mini"): [],
    ("cnes_equipes", "cnes_ep_rr_2024_01_mini"): [],
    ("cnes_estabelecimentos_ensino", "cnes_ee_rr_2019_12_mini"): [],
    ("cnes_estabelecimentos_filantropicos", "cnes_ef_ap_2024_01_mini"): [],
    ("cnes_gestao_metas", "cnes_gm_rr_2024_01_mini"): [],
    ("cnes_habilitacoes", "cnes_hb_rr_2024_01_mini"): [],
    ("cnes_incentivos", "cnes_in_rr_2024_01_mini"): [],
    ("cnes_leitos", "cnes_lt_rr_2024_01_mini"): [],
    ("cnes_regras_contratuais", "cnes_rc_rr_2024_01_mini"): [],
    ("cnes_servicos_especializados", "cnes_sr_rr_2024_01_mini"): [],
    ("sim_obitos_fetais", "sim_dofet_br_2023_excerpt"): [],
    # DOEXT, DOINF and DOMAT read with sim_obitos' fields: the same blank-only gaps.
    ("sim_obitos_externos", "sim_doext_br_2023_excerpt"): [
        ("altcausa", "", 988),
        ("assistmed", "", 196),
        ("esc2010", "", 79),
        ("escmae2010", "", 994),
        ("morteparto", "", 988),
        ("tpnivelinv", "", 898),
        ("tpresginfo", "", 998),
    ],
    ("sim_obitos_infantis", "sim_doinf_br_2023_excerpt"): [
        ("altcausa", "", 145),
        ("assistmed", "", 246),
        ("esc2010", "", 1000),
        ("escmae2010", "", 85),
        ("morteparto", "", 114),
        ("tpnivelinv", "", 1000),
        ("tpresginfo", "", 1000),
    ],
    ("sim_obitos_maternos", "sim_domat_br_2023_mini"): [
        ("altcausa", "", 1325),
        ("assistmed", "", 129),
        ("esc2010", "", 39),
        ("escmae2010", "", 1325),
        ("morteparto", "", 1325),
        ("tpnivelinv", "", 90),
        ("tpresginfo", "", 115),
    ],
    ("sim_obitos_cid9", "sim_cid9_rr_1995_mini"): [],
    # SIA families of Informe Técnico SIASUS 2019-07, same rule; AMP has no DEF.
    ("sia_apac_acompanhamento_bariatrica", "sia_ab_se_2025_07_mini"): [],
    ("sia_apac_fistula_arteriovenosa", "sia_acf_rr_2024_01_mini"): [],
    ("sia_apac_nefrologia", "sia_an_pa_2014_10_mini"): [],
    ("sia_apac_radioterapia", "sia_ar_ac_2024_01_mini"): [],
    ("sia_atencao_domiciliar", "sia_sad_ma_2018_10_mini"): [],
}


def _uncovered(dbc_fixture, dataset: str, fixture: str) -> list[Uncovered]:
    frame = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
    with duckdb.connect() as con:
        return decode_coverage(dataset, con.from_arrow(frame.to_arrow()))


@pytest.mark.parametrize(("dataset", "fixture"), sorted(REMAINING))
def test_every_mini_fixture_has_only_the_recorded_gaps(dbc_fixture, dataset, fixture):
    found = [(u.field, u.value, u.rows) for u in _uncovered(dbc_fixture, dataset, fixture)]
    assert sorted(found) == sorted(REMAINING[(dataset, fixture)])


def test_every_x_decode_key_is_a_string():
    """Pins the invariant that keeps ``decode_coverage`` and ``_lookup_decode`` agreeing.

    ``decode_coverage`` compares values as text against ``x-decode`` keys with no
    trimming and no integer fallback; ``_lookup_decode`` (used by ``display_row`` at
    runtime) additionally tries an integer-cast lookup. The two only report the same
    "covered" set while every ``x-decode`` key is a ``str``: a stored value like
    ``"01"`` against an *int* key ``1`` would be matched by ``_lookup_decode``'s
    fallback (``int("01") in decode_map`` -> ``True``) but still reported as
    uncovered by ``decode_coverage`` (``"01" != "1"`` as text, keys are compared
    verbatim). If any packaged dictionary ever declares a non-string key, this
    invariant breaks silently -- coverage reports would start disagreeing with what
    users actually see in ``display_row`` -- so it is pinned here on every packaged
    dictionary, loaded the same way ``decode_coverage`` loads them.
    """
    packaged = sorted(
        p.name.removesuffix(".yaml")
        for p in files("omnisus.data.dicionarios").iterdir()
        if p.name.endswith(".yaml")
    )
    assert packaged, "no packaged dictionaries found"
    offenders = [
        (dataset, field["name"], key)
        for dataset in packaged
        for field in load_dicionario(dataset).fields
        for key in (field.get("x-decode") or {})
        if not isinstance(key, str)
    ]
    assert offenders == []


@pytest.mark.parametrize(
    ("dataset", "fixture", "field", "values"),
    [
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "marca_uti", {"78", "81"}),
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "marca_uci", {"00", "01", "02"}),
        ("cnes_estabelecimentos", "cnes_rr_2024_01_mini", "turno_at", {"01", "03", "07"}),
        ("sinasc_nascidos_vivos", "sinasc_rr_2022_mini", "tpmetestim", {"8"}),
        ("sinasc_nascidos_vivos", "sinasc_rr_2022_mini", "kotelchuck", {"5"}),
    ],
)
def test_the_comparison_report_gaps_are_closed(dbc_fixture, dataset, fixture, field, values):
    """microdatasus comparison, defect table: these codes had no label."""
    found = {u.value for u in _uncovered(dbc_fixture, dataset, fixture) if u.field == field}
    assert not found & values


@pytest.mark.parametrize(
    ("dataset", "fixture", "field", "labels"),
    [
        # NATUREZA.CNV and VINCPREV.CNV (TAB_SIH): only the fallback range lists these codes.
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "natureza", {"00": "Ignorado"}),
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "vincprev", {"0": "Não classificado"}),
        # Estrutura do SIM 2025, p. 8, codes 01-03; the files write one digit ("1 ").
        (
            "sim_obitos",
            "sim_rr_2022_mini",
            "tpresginfo",
            {
                "1": "Não acrescentou nem corrigiu informação",
                "2": "Sim, permitiu o resgate de novas informações",
                "3": "Sim, permitiu a correção de alguma das causas informadas originalmente",
            },
        ),
        # Estrutura do SIM 2025, p. 7: the moment of a maternal death, not a place.
        (
            "sim_obitos",
            "sim_rr_2023_mini",
            "tpobitocor",
            {
                "6": "Entre 43 dias e até 1 ano após o parto",
                "8": "Mais de um ano após o parto",
                "": "Não investigado",
            },
        ),
        # TAB_SIA FINANC.CNV, the table of PA_TPFIN, which the Informe Técnico describes
        # with the same words as BPA-I TPFIN.
        (
            "sia_bpa_individualizado",
            "sia_bi_rr_2022_01_mini",
            "tpfin",
            {"05": "05 Incentivo - MAC"},
        ),
        # (column check of 2026-09-23, SP 2022). TP_DROGA.CNV lists the
        # combinations as written in the file.
        (
            "sia_psicossocial",
            "sia_ps_sp_2022_12_a_excerpt",
            "tp_droga",
            {"A O": "Alcool e Outras Drogas", "ACO": "Alcool, Crack e Outras Drogas"},
        ),
        ("sia_psicossocial", "sia_ps_sp_2022_12_b_excerpt", "tp_droga", {"AC": "Alcool e Crack"}),
        # AR and ACF bind AP_COIDADE to AQ's tables, so they take AQ's map.
        (
            "sia_apac_radioterapia",
            "sia_ar_ac_2024_01_mini",
            "ap_coidade",
            {"2": "Dias", "4": "Anos"},
        ),
        ("sia_apac_fistula_arteriovenosa", "sia_acf_rr_2024_01_mini", "ap_coidade", {"4": "Anos"}),
        # RD2008.DEF lines 275-277 bind REGCT to REGCT.CNV, as RJ2008.DEF lines 277-279 do.
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "regct", {"0000": "SEM CONTRATO"}),
        # RJ2008.DEF binds SEXO to RD's SEXO.CNV.
        (
            "sih_aih_rejeitada",
            "sih_rj_rr_2024_01_mini",
            "sexo",
            {"1": "Masculino", "3": "Feminino"},
        ),
        # Motivo_de_Erro.DEF relates CO_ERRO to DBF/MOTERRO.DBF.
        (
            "sih_aih_rejeitada_erro",
            "sih_er_rr_2024_01_mini",
            "co_erro",
            {
                "060082": "QUANTIDADE DE DIÁRIAS SUPERIOR A CAPACIDADE INSTALADA",
                "020081": "AIH BLOQUEADA POR PERÍODOS DE INTERNAÇÃO SOBREPOSTOS NO MOVIMENTO",
            },
        ),
    ],
)
def test_report_codes_take_the_source_label(dbc_fixture, dataset, fixture, field, labels):
    """Column check of 2026-09-23 (RR 2022): codes published with no label."""
    frame = dbc_bytes_to_lazyframe(dbc_fixture(fixture).read_bytes(), dataset=dataset).collect()
    assert set(labels) <= set(frame[field].to_list())
    decode = load_dicionario(dataset).field_def(field)["x-decode"]
    assert {code: decode.get(code) for code in labels} == labels


@pytest.mark.parametrize(
    ("dataset", "fixture", "field", "issue", "codes"),
    [
        ("sih_aih_reduzida", "sih_rr_2024_01_mini", "homonimo", "homonimo-sem-fonte", {"2"}),
        (
            "sinasc_nascidos_vivos",
            "sinasc_rr_2022_mini",
            "tpdocresp",
            "tpdocresp-0-sem-fonte",
            {"0"},
        ),
        (
            "sia_bpa_individualizado",
            "sia_bi_rr_2022_01_mini",
            "tpidadepac",
            "tpidadepac-sem-tabela",
            {"5", "9"},
        ),
        # Codes no source defines (SP 2022 excerpts, AM RR 2024-01).
        (
            "sia_psicossocial",
            "sia_ps_sp_2022_12_b_excerpt",
            "tp_droga",
            "tp_droga-combinacao-sem-fonte",
            {"AO", "CA", "OA"},
        ),
        (
            "sia_apac_laudos_diversos",
            "sia_ad_sp_2022_12_excerpt",
            "ap_tpapac",
            "ap_tpapac-4-sem-fonte",
            {"4"},
        ),
        (
            "sia_apac_laudos_diversos",
            "sia_ad_sp_2022_10_excerpt",
            "ap_coidade",
            "ap_coidade-sem-tabela",
            {"0"},
        ),
        (
            "sia_apac_medicamentos",
            "sia_am_rr_2024_01_mini",
            "ap_coidade",
            "ap_coidade-sem-tabela",
            {"5"},
        ),
        (
            "sia_apac_radioterapia",
            "sia_ar_sp_2022_12_excerpt",
            "ar_finali",
            "ar_finali-7-sem-fonte",
            {"7"},
        ),
        ("sih_aih_reduzida", "sih_rd_sp_2022_01_excerpt", "espec", "espec-17-sem-fonte", {"17"}),
        ("sih_aih_rejeitada", "sih_rj_sp_2022_03_excerpt", "espec", "espec-17-sem-fonte", {"17"}),
        (
            "sih_aih_rejeitada",
            "sih_rj_sp_2022_07_excerpt",
            "financ",
            "financ-00-sem-fonte",
            {"00"},
        ),
    ],
)
def test_codes_left_unlabeled_have_an_open_issue(
    dbc_fixture, dataset, fixture, field, issue, codes
):
    """A published code no source labels stays undecoded, and the field says why."""
    found = {u.value for u in _uncovered(dbc_fixture, dataset, fixture) if u.field == field}
    assert codes <= found
    issues = load_dicionario(dataset).field_def(field)["x-metadata"]["issues"]
    (entry,) = [i for i in issues if i["id"] == issue]
    assert entry["status"] == "open"
    assert all(f"'{code}'" in entry["description"] for code in codes)


def test_amp_age_unit_and_sex_stay_undecoded_without_a_def(dbc_fixture):
    """TAB_SIA has no AMP DEF and the Informe Técnico no AMP layout: AMPDF2401 holds
    AP_COIDADE 4 and AP_SEXO F/M, and neither field gets a map."""
    raw = dbc_fixture("sia_amp_df_2024_01_mini").read_bytes()
    dataset = "sia_apac_acompanhamento_multiprofissional"
    frame = dbc_bytes_to_lazyframe(raw, dataset=dataset).collect()
    assert set(frame["ap_coidade"]) == {"4"} and set(frame["ap_sexo"]) == {"F", "M"}
    for name in ("ap_coidade", "ap_sexo"):
        field = load_dicionario(dataset).field_def(name)
        assert "x-decode" not in field
        (entry,) = [i for i in field["x-metadata"]["issues"] if i["id"] == "amp-sem-def"]
        assert entry["status"] == "open"


APAC_WITH_UNIT_MAP = [
    "sia_apac_quimioterapia",
    "sia_apac_tratamento_dialitico",
    "sia_apac_medicamentos",
    "sia_apac_laudos_diversos",
    "sia_apac_cirurgia_bariatrica",
    "sia_apac_radioterapia",
    "sia_apac_fistula_arteriovenosa",
]


@pytest.mark.parametrize("dataset", APAC_WITH_UNIT_MAP)
def test_every_apac_age_unit_map_says_it_was_measured(dataset):
    """No table labels the 1-character AP_COIDADE: every APAC map carries the issue."""
    field = load_dicionario(dataset).field_def("ap_coidade")
    assert field["x-decode"] == {"2": "Dias", "3": "Meses", "4": "Anos"}
    (entry,) = [i for i in field["x-metadata"]["issues"] if i["id"] == "ap_coidade-sem-tabela"]
    assert entry["status"] == "open"


@pytest.mark.parametrize(
    ("dataset", "field", "issue"),
    [
        ("sia_apac_quimioterapia", "ap_tpapac", "ap_tpapac-4-sem-fonte"),
        ("sia_apac_tratamento_dialitico", "ap_tpapac", "ap_tpapac-4-sem-fonte"),
    ],
)
def test_report_codes_without_a_fixture_still_have_an_open_issue(dataset, field, issue):
    """AQ and ATD publish AP_TPAPAC 4 in SP 2022 (1 row each), in files too large to cut."""
    issues = load_dicionario(dataset).field_def(field)["x-metadata"]["issues"]
    (entry,) = [i for i in issues if i["id"] == issue]
    assert entry["status"] == "open" and "'4'" in entry["description"]


def test_cobranca_labels_come_from_saidaperm():
    """Portaria SAS 719/2007 shift reported on 2026-09-20; TAB_SIH SAIDAPERM.CNV settles it."""
    decode = load_dicionario("sih_aih_reduzida").field_def("cobranca")["x-decode"]
    assert decode["26"] == "Permanência por mudança de procedimento"
    assert decode["31"] == "Transferência para outro estabelecimento"


def test_co_erro_labels_only_the_six_character_codes_er_publishes():
    """MOTERRO.dbf holds 581 codes of 6 characters (latin-1 text) and 60 of 4 (41 of them in
    CP850, e.g. 0008 'SOLICITA\\x80\\xc7O'). The 4,931 ER files on the server publish only
    6-character codes, so only those take a label."""
    decode = load_dicionario("sih_aih_rejeitada_erro").field_def("co_erro")["x-decode"]
    assert len(decode) == 581
    assert {len(code) for code in decode} == {6}
    assert decode["040006"] == "AIH APROVADA EM OUTRO PROCESSAMENTO"
    assert decode["010004"] == "PROCEDIMENTO PRINCIPAL NÃO É DE CNRAC"
