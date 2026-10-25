"""Small DBF fixtures with independently specified field bytes."""

DBC_CASES = [
    ("sim_rr_2023_mini", "sim_obitos"),
    ("sinasc_rr_2022_mini", "sinasc_nascidos_vivos"),
    ("sih_rr_2024_01_mini", "sih_aih_reduzida"),
    ("cnes_rr_2024_01_mini", "cnes_estabelecimentos"),
    ("sia_abo_sp_2024_01_mini", "sia_apac_cirurgia_bariatrica"),
    ("sia_ad_rr_2024_01_mini", "sia_apac_laudos_diversos"),
    ("sia_am_rr_2024_01_mini", "sia_apac_medicamentos"),
    ("sia_aq_rr_2024_01_mini", "sia_apac_quimioterapia"),
    ("sia_atd_rr_2024_01_mini", "sia_apac_tratamento_dialitico"),
    ("sia_bi_rr_2024_01_mini", "sia_bpa_individualizado"),
    ("sia_ps_rr_2024_01_mini", "sia_psicossocial"),
    ("sih_rd_sp_2023_08_excerpt", "sih_aih_reduzida"),
    ("cnes_st_sp_2022_12_excerpt", "cnes_estabelecimentos"),
    # SINAN national files carry D (date) fields.
    ("sinan_tuberculose_br_2020_excerpt", "sinan_tuberculose"),
    ("sinan_hanseniase_br_2026", "sinan_hanseniase"),
    ("sinan_chagas_br_2023", "sinan_chagas"),
]


def make_dbf(
    fields: list[tuple[str, str, int, int]],
    records: list[bytes],
    *,
    declared_rows: int | None = None,
    eof: bytes = b"\x1a",
) -> bytes:
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(field[2] for field in fields)
    if any(len(record) != record_length for record in records):
        raise ValueError("Every record must include flag and exactly the declared field widths")
    header = bytearray(32)
    header[0] = 3
    header[1:4] = bytes([24, 1, 1])
    count = len(records) if declared_rows is None else declared_rows
    header[4:8] = count.to_bytes(4, "little")
    header[8:10] = header_length.to_bytes(2, "little")
    header[10:12] = record_length.to_bytes(2, "little")
    descriptors = bytearray()
    for name, kind, width, decimals in fields:
        encoded = name.encode("ascii")
        if not 1 <= len(encoded) <= 10 or not 1 <= width <= 255:
            raise ValueError("Invalid fixture field")
        descriptor = bytearray(32)
        descriptor[: len(encoded)] = encoded
        descriptor[11] = ord(kind)
        descriptor[16] = width
        descriptor[17] = decimals
        descriptors.extend(descriptor)
    return bytes(header + descriptors) + b"\x0d" + b"".join(records) + eof
