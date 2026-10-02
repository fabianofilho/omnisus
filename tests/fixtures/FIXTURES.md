# Fixture provenance

Every data file under `tests/fixtures/dbc/`, `tests/fixtures/listings/`,
`tests/fixtures/cnv/` and `tests/fixtures/sigtap/` has one row here (AGENTS.md, zero-assumption policy, rule 2).
`tests/unit/test_fixture_provenance.py` enforces it.

- `whole`: the unchanged server file; `source_sha256` is its digest.
- `excerpt`: `records` consecutive records of the server file named in `source`,
  re-wrapped by `scripts/dbc_excerpt.py`; `source_sha256` is the digest of the
  full server file. They are the first records unless `note` names the first one
  kept (0-based, `--first`).
- `listing`: raw `LIST` lines of the directory in `source`, gzipped;
  `source_sha256` is the digest of the full listing text; `records` is the number
  of lines kept; `note` names the filter, if any. `scripts/capture_listing.py`
  captures one and prints these values.
- `member`: one file extracted unchanged from the server archive in `source`
  (`<archive URL>#<path inside the archive>`); `source_sha256` is the digest of the
  member, equal to the committed bytes; `note` gives the archive's SHA-256.
- `synthetic`: hand-made bytes for malformed-input tests only; `note` says why.
- `vector`: a test vector copied unchanged from another project; `source` is its
  URL pinned to a commit, `source_sha256` the digest of the committed bytes,
  `server_modified` the commit date, and `note` its licence.

`server_modified` is the mtime the DATASUS listing reported (server clock, no time
zone), or `unknown`.

| file | kind | source | server_modified | source_sha256 | records | note |
| --- | --- | --- | --- | --- | --- | --- |
| cnv/DNNOVA.CNV | member | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/1996_/Auxiliar/Arq_Para_Tabulacao_A_Partir_1996.zip#Arquivos Auxiliares para Tabulação a partir de 1996/DNNOVA.CNV | 2026-07-09T19:46 | c8ea069a96007e047ac47b5b8594b5d3b5a0ec92a81616e47cf7ff91ac425b33 | | archive SHA-256 de43d0c99630e3229d0c23e00ceca7b13eb41d80b5108da769d61c248aed1ab6; code written in column 60, outside the TabWin layout |
| cnv/IDADEDET.CNV | member | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Auxiliar/TAB_SIA.zip#CNV/IDADEDET.CNV | 2026-09-15T23:18 | 47e02370f68924ac1748e526215b95a12a2942a97ea216e96f4ad9c562954d6e | | archive SHA-256 e5812b51d802b2fe3d0c7988a24d694b97a7998a9f2f5cff390b0b4103e74d98; the same bytes as TAB_SIH `CNV/IDADEDET.CNV` |
| dbc/cnes_dc_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/DC/DCRR2401.dbc | 2024-02-15T14:25 | f33f297642b455e644d3be11d5bfa1608ac1da6e4848dd82ac53110d8ed28538 | 9 | |
| dbc/cnes_ee_rr_2019_12_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EE/EERR1912.dbc | 2020-08-24T09:48 | e14f86b84cbce5a9e9bb60b1f07f446875c3f2a66589a9106edf86745e7628d4 | 1 | |
| dbc/cnes_ef_ap_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EF/EFAP2401.dbc | 2024-02-15T14:25 | 038d9407399f79b8a683722841f9709f852c3d4da5b7fc0724846141b6559d71 | 1 | |
| dbc/cnes_ep_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EP/EPRR2401.dbc | 2024-02-15T14:25 | 98cf1abaeac4e8e5ffb1d56e6d595e331a61f57728f118b0afa8c67841f290f1 | 434 | |
| dbc/cnes_eq_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/EQ/EQRR2401.dbc | 2024-02-15T14:25 | 6d706d8ed1e1450e65c83ea9296330ebe27d1261275532de2181d777cbd785aa | 3094 | |
| dbc/cnes_gm_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/GM/GMRR2401.dbc | 2024-02-15T14:25 | a3129d9aca30ec72f6109dd3fb8118ecf6cf9a79b2795449299c4a80d5268ec4 | 36 | |
| dbc/cnes_hb_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/HB/HBRR2401.dbc | 2024-02-15T14:25 | 34528819d27008bfe25be5bbc740af97b47b39097704ab2fcde98922f6a6c861 | 52 | |
| dbc/cnes_in_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/IN/INRR2401.dbc | 2024-02-15T14:25 | 3ed4d864f7684d66ac0929b18d9f4fe69e88874991f4d1af1156554a0fec0a65 | 40 | |
| dbc/cnes_lt_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/LT/LTRR2401.dbc | 2024-02-15T14:25 | 78d215351acc4b62aac3a59664cdb166211e82aba5242d4b50f50457eb511b76 | 137 | |
| dbc/cnes_rc_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/RC/RCRR2401.dbc | 2024-02-15T14:25 | 50139a7735603188c2497c9d4c7c0a99159c31827fea2cf61a74464696fb3df9 | 73 | |
| dbc/cnes_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/ST/STRR2401.dbc | 2024-02-15T14:25 | 99352c3b41d3f8f4a38d02b899460dc7b58fa5471e0ffbef83ceab4ededbfb35 | 1036 | |
| dbc/cnes_sr_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/SR/SRRR2401.dbc | 2024-02-15T14:25 | 1c2c077c29c0307d579f8c7a78d925ab1a6bf2100c7968caea9248f3d9f9f1d5 | 2361 | |
| dbc/cnes_st_sp_2022_12_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/ST/STSP2212.dbc | 2023-01-11T07:34 | dba6fff68657a6c3272d5be2a12266ee190f5be7355451d71d3ca1c5503bd285 | 5 | first record 65936 of 85,396; record 65938 holds ALVARA `.\x8f6018202200448734`, the file's only byte cp1252 leaves undefined |
| dbc/malformed/dict_size_3.dbc | synthetic | | | | | PKWare DCL dictionary-size byte 3 (valid: 4, 5, 6) after a valid 33-byte DBF header; both decoders must raise |
| dbc/malformed/short_header.dbc | synthetic | | | | | declares a 32-byte DBF header (minimum 33) claiming 5 records and holds none; before the header guard it staged 0 rows silently |
| dbc/malformed/zero_record_length.dbc | synthetic | | | | | 65-byte DBF header declaring 3 records of length 0, holding 2 (field NOME C3); before the record-length guard it switched off both DBF integrity gates and staged 2 rows silently |
| dbc/sia_ab_se_2025_07_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ABSE2507.dbc | 2026-02-10T14:44 | 4eea439d69d0902d209f9bcaac4a66e3eeebc989b03e226a7d6ca3b9ffb62a29 | 5 | |
| dbc/sia_abo_sp_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ABOSP2401.dbc | 2025-02-05T21:00 | a074880b8dac172b62eed4eafb48a20d1ef6a5c398ae40125f6579b90fbe318d | 844 | |
| dbc/sia_acf_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ACFRR2401.dbc | 2025-02-05T21:01 | af758b73b9b8ff4d60aee6f0f28948dbaa73f240c41bb887a356ce342ce935da | 20 | |
| dbc/sia_ad_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ADRR2401.dbc | 2025-02-05T21:01 | 78efff648a0c6624e4c0b54fab02e8acf25cbe0c1c73a5d24bc1098b9aaff882 | 678 | |
| dbc/sia_ad_sp_2022_10_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ADSP2210.dbc | 2023-11-08T09:03 | 50f7d8d7d5a33be9c378aba835ee96c8cef9cca91add16d382626daf9d7b2bfe | 1 | first record 12349 of 72,935; ap_coidade '0' with ap_nuidade '00' |
| dbc/sia_ad_sp_2022_12_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ADSP2212.dbc | 2024-01-08T20:56 | c0e186720cb35f84ab7078330ee1956fbd90c70cbbc8798c56495e4ce7f33bcb | 2 | first record 51620 of 70,486; ap_tpapac '4' in both |
| dbc/sia_am_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/AMRR2401.dbc | 2025-02-05T21:01 | dbad1970271aea1a0bff0ad8006b27e17c527950cc042d268b215a375b7c22ef | 2083 | |
| dbc/sia_amp_df_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/AMPDF2401.dbc | 2025-02-05T21:01 | 3c99ca5e7d47bed0a07d478686c5b1caf83c44cf013639e68b75570397197d49 | 25 | |
| dbc/sia_an_pa_2014_10_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ANPA1410.dbc | 2019-06-07T09:31 | 2a16136ba196eb64863a9fa9379f4fb5db1a8631f59e010a4e88e2a76ec060e5 | 2 | |
| dbc/sia_aq_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/AQRR2401.dbc | 2025-02-05T21:01 | f0c8fb5e0bdbc81ed59f599e6783afcca8f30b5c3321d0509b1baf3803b60e55 | 17 | |
| dbc/sia_ar_ac_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ARAC2401.dbc | 2025-02-05T21:01 | bf98a8c580cb39ade944fd33bad89f44430affd75a0c5dbfe310f684ad4310b1 | 39 | |
| dbc/sia_ar_sp_2022_12_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ARSP2212.dbc | 2024-01-08T20:56 | 12462afcad1e206bb736e138fef880d47c4012cec8c013396c4d267dee38cd3c | 1 | first record 413 of 2,787; ar_finali '7' |
| dbc/sia_atd_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/ATDRR2401.dbc | 2025-02-05T21:01 | 6bd7e025d6ea81cd2d515727e4679fd1f3c56b70a2841488f0ad2d651704f71e | 358 | |
| dbc/sia_bi_mg_2024_12_part1_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/BIMG2412_1.dbc | 2026-01-09T15:38 | ba4708a6f6d9952bc6228d7779299dd72a6c04b0ea2f849a1c7f86f793bd0dd5 | 200 | part 1 of a month published only as parts |
| dbc/sia_bi_mg_2024_12_part2_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/BIMG2412_2.dbc | 2026-01-09T15:38 | b907940c1ce2605a83ecad2b6711a86ea9af5028594483c603b22836de5cfbda | 200 | part 2 of a month published only as parts |
| dbc/sia_bi_rr_2022_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/BIRR2201.dbc | 2023-10-12T15:02 | 03d41d139dd970f25a565471053a5459f7cd77ef7d2633a63f33db2f8725340a | 16594 | holds tpidadepac 5 (7 rows) and 9 (2 rows) |
| dbc/sia_bi_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/BIRR2401.dbc | 2025-02-05T21:03 | 80fb48c648f88c72de4e2577bfad46b8dde45dcbc029ba38c91707133f3337b2 | 12099 | |
| dbc/sia_pa_rr_2007_12_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/199407_200712/Dados/PARR0712.dbc | 2013-10-24T16:14 | 6a61553fc6151a986428b19b6944dc8e99cdecacc32cac55b523b00ebc4c948d | 16988 | |
| dbc/sia_pa_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/PARR2401.dbc | 2025-02-05T21:05 | 3f875df629008dbc118bb12e41e7df44e80bac8a5c1d914ad745c47678d76d0d | 21341 | |
| dbc/sia_ps_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/PSRR2401.dbc | 2025-02-05T21:06 | 56022bfa7245e8d57530c74e7f3144ec797c14736e94e873ba25e0ffb5c2b5d7 | 1670 | |
| dbc/sia_ps_sp_2022_12_a_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/PSSP2212.dbc | 2024-01-08T21:00 | 9954c25e08ec7f112a56b0db77e4c9c5ddb8b26baa5e573d1bb489ed91e69441 | 30 | first record 280898 of 288,019; tp_droga 'A O' (records 280898, 280900) and 'ACO' |
| dbc/sia_ps_sp_2022_12_b_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/PSSP2212.dbc | 2024-01-08T21:00 | 9954c25e08ec7f112a56b0db77e4c9c5ddb8b26baa5e573d1bb489ed91e69441 | 17 | first record 212148 of 288,019; tp_droga 'AC', 'ACO', 'AO', 'CA' and 'OA' |
| dbc/sia_sad_ma_2018_10_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados/SADMA1810.dbc | 2020-01-10T09:45 | 09470713cd7e913e690d5c98df63d12282c26c48db241ddc629d293911182f89 | 33 | |
| dbc/sih_er_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/ERRR2401.dbc | 2025-02-09T21:24 | 5f6f48faf36d4ced250f94c97c687081eee854e8bc4abc93dd0ab67c87623fa2 | 31 | |
| dbc/sih_rd_rr_1994_12_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/199201_200712/Dados/RDRR9412.dbc | 2013-10-31T13:09 | 72e8ec8edd5d52c79587f3d7206603d9e973811bd5d20924bfa19986b462ee05 | 1614 | |
| dbc/sih_rd_rr_1997_09_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/199201_200712/Dados/RDRR9709.dbc | 2013-10-31T13:09 | 0f5e8f9fe143cdc99f01dfbf3369ce46a18332356c0088fa2c9578afb56de9bf | 794 | |
| dbc/sih_rd_rr_2004_07_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/199201_200712/Dados/RDRR0407.dbc | 2013-10-31T13:08 | 8960203d29ae9b0ed7ab84fc3587d5a2b068ea402c7265f3bc36fc86f6735138 | 91 | first record 481 of 1,314; a run with no CPF in CPF_AUT or GESTOR_CPF |
| dbc/sih_rd_rr_2007_12_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/199201_200712/Dados/RDRR0712.dbc | 2013-10-31T13:08 | d6c5838ec19f4cd595f44835cbc3468bf8691299fccdbdbde13ae4d9292d3371 | 1496 | |
| dbc/sih_rd_sp_2022_01_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RDSP2201.dbc | 2023-02-06T13:05 | 8ae4e3a106dbdd27e7c1a75591f4f692255364d8238044451fb00b7d85346c68 | 1 | first record 94063 of 199,070; espec '17' |
| dbc/sih_rd_sp_2023_08_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RDSP2308.dbc | 2024-09-05T10:32 | eb5d97e8e834b7bc4342bfa28eb00eaa20055490b688f466906d6bc7f42f3ebb | 5 | first record 152398 of 237,476; record 152400 holds AUD_JUST `PACIENTE REC\x90M NASCIDO ENCONTRADO NA ESTRADA RURAL`, the file's only byte cp1252 leaves undefined |
| dbc/sih_rj_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RJRR2401.dbc | 2025-02-09T21:36 | bae9610e625241a9ee83edc9fb0f6948fd47f3658c2e5be90d6019097535891a | 30 | |
| dbc/sih_rj_sp_2022_03_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RJSP2203.dbc | 2023-04-05T12:38 | f85760f7cf7befa7507266736e5ae5bda02b9b92cf5a7a020db30dc4e2873100 | 1 | first record 6042 of 10,948; espec '17' |
| dbc/sih_rj_sp_2022_07_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RJSP2207.dbc | 2023-08-03T17:09 | 3de15538f7ac622f691a2341106c2db5826833b701622d9fd04ae3fe872233c3 | 1 | first record 14750 of 20,138; financ '00' |
| dbc/sih_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RDRR2401.dbc | 2025-02-09T21:29 | 37741f8b16adcf0f19ff837f9abbf9c46af4b6c128f5599867fe0fa7940eccb5 | 3714 | |
| dbc/sih_sp_rr_2024_01_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/SPRR2401.dbc | 2025-02-09T21:46 | f8107486b08850860ea78a0d4517974cec92315b7268a690441031b7b6fd06ee | 35669 | |
| dbc/sim_cid9_rr_1995_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID9/DORES/DORRR95.DBC | 2020-01-31T14:47 | 587877c77247864bc3dbb30661ded1a1f17d2854bba0472ca4d742f632b65b55 | 967 | |
| dbc/sim_doext_br_2023_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOFET/DOEXT23.dbc | 2024-12-19T15:36 | a201fd5911c38e482760452644e4b9b13ebf0e090fd2acbe2e6dd9d1c4525b92 | 1000 | |
| dbc/sim_dofet_br_2023_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOFET/DOFET23.dbc | 2024-12-19T11:55 | 1c5837af833eb3f0d9cd8e7326293252571255c3daf6146ca8226241184b43d5 | 1000 | |
| dbc/sim_doinf_br_2023_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOFET/DOINF23.dbc | 2024-12-19T11:55 | 8634319e3555cfd4d88f6c544160b4947ed7c69d54705fd15400d9d5a8c3b0c9 | 1000 | |
| dbc/sim_domat_br_2023_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOFET/DOMAT23.dbc | 2024-12-26T12:53 | 8d27be60f635b81d465248b814eb8549d9eb22cd0f66a970632e88e973c27e7d | 1325 | |
| dbc/sim_rr_2022_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2022.dbc | 2023-12-21T16:19 | 6643344fe1ab587d648e5e0ea8cf7e3ef9e5b5b7021a12dcbbc54f5724d2ec65 | 3246 | holds tpresginfo 3 (2 rows) |
| dbc/sim_rr_2023_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES/DORR2023.dbc | 2024-12-19T11:56 | 15b5203507161b7c35f9c69a52c955bdac133629549099b85a88e03a9a45baf0 | 3311 | |
| dbc/sinan_chagas_br_2023.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/CHAGBR23.dbc | 2024-12-02T14:39 | a0ab9f568b52c565819466eba2cf312e40549cec707f28e5001de1532f79a10f | 6253 | |
| dbc/sinan_hanseniase_br_2026.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/HANSBR26.dbc | 2026-07-06T10:59 | 2a1d5b69008bf320c8aabff01a99cc0f12ed1884bf006a002997bc50de795a62 | 10354 | |
| dbc/sinan_tuberculose_br_2020_excerpt.dbc | excerpt | ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM/TUBEBR20.dbc | 2026-05-07T16:08 | 9ecf487348b6196c7af143376e10ad70bdb9ef5ecc6ed9026cfa52f39b0b0edc | 3000 | smallest file of the 94-field layout (2019-2025) |
| dbc/sinasc_rr_1995_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/1994_1995/Dados/DNRES/DNRRR1995.dbc | 2020-01-27T11:56 | bb06e2c576acbc036fd392e0c29005b4e7cb4e99b5b44ad0972586d57e5b4a99 | 7020 | |
| dbc/sinasc_rr_2022_mini.dbc | whole | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/1996_/Dados/DNRES/DNRR2022.dbc | 2024-01-11T17:54 | 55edaa6508cb58cc35e8ce7a74d5950198d91dd3c5c4c64d9e0c8199667601db | 13091 | both NOV/DNRES and 1996_/Dados/DNRES hold identical bytes; 1996_/Dados/DNRES preferred (registry moves there in W1) |
| dbc/vectors/microdatasus_three_fields.dbc | vector | https://github.com/rfsaldanha/microdatasus/blob/7109ec2c42cf674ba453e0d7a20d2f464890b543/tests/testthat/test-read_dbc.R#L2-L9 | 2026-07-29T12:55 | 2086c600b509d3554db9aaeeb26878046a3e7f9177544d38678e347f92bb2811 | 2 | MIT, Copyright (c) 2021 microdatasus authors; notice in dbc/vectors/README.md |
| listings/siasus_200801_dados.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados | 2026-09-21T14:07 | 1432563da6bf7fe4cf7a60b0673c889ad029f02fb1c5a343cd13e4c54c26a86c | 4186 | filter ^(BI&#124;PA&#124;AM&#124;ATD)[A-Z]{2}2[3-5] |
| listings/siasus_200801_dados_apac_sad.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/200801_/Dados | 2026-09-23T00:49 | 286a306668c4a47e1210343bd116352cea11d10f22d80e8524549cdffae9ea3e | 13992 | filter ^(AB&#124;ACF&#124;AMP&#124;AN&#124;AR&#124;SAD)[A-Z]{2}\d{4}[a-z]?\.dbc |
| listings/sigtap_tup_downloads_nlst.txt.gz | listing | ftp://ftp2.datasus.gov.br/public/sistemas/tup/downloads | 2026-09-22T22:45 | 6b147035482a02f6f47f25991d042378287ecb29a7995742b9d406551d36124d | 236 | NLST names, not LIST lines: this server answers LIST in Unix format |
| listings/sim_cid10_dofet.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DOFET | 2026-09-23T01:50 | da784b058d3dd585a5db57db55d4d230dfc25e803284006326b788fdb041c084 | 133 | |
| listings/sim_cid10_dores.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID10/DORES | 2026-09-21T14:07 | 877f967a7ba5694fc235f2c98199b4e04e1bb429497910fb9e673b30eada4dff | 812 | |
| listings/sim_cid9_dores.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/CID9/DORES | 2026-09-23T01:50 | 33f82eb10b10da9c3b5d41757b24dd1d4f25237300cc58b7e17d00e8f721276a | 466 | |
| listings/sinan_dados_finais.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/FINAIS | 2026-09-22T10:17 | 913e2d8f8090af95bcd8ea741a76bf4e5e75b6fadd545c998ea8a40e73369980 | 744 | |
| listings/sinan_dados_prelim.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/DADOS/PRELIM | 2026-09-22T10:17 | 078ab5a722e2048628743beb91ca20e23d243ef8c00b07f02fc4a83bfce1d2e3 | 356 | |
| listings/sinasc_1994_1995_dnres.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/1994_1995/Dados/DNRES | 2026-09-23T01:50 | 3db523d4a86f269aacfa9f2d1a6c83c8c0f45c39434116ed301e0efebbeb8638 | 56 | |
| listings/sinasc_1996_dados_dnres.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/1996_/Dados/DNRES | 2026-09-21T14:07 | c3ff1d409dcec1335846e29ceed963c57b4f1028e95fe7e6fea7a14609490b81 | 823 | |
| listings/sinasc_prelim_dnres.txt.gz | listing | ftp://ftp.datasus.gov.br/dissemin/publicos/SINASC/PRELIM/DNRES | 2026-09-21T14:07 | cc19149e203355266873469f06b24bde62bc5e1b307c9522391b2c2d00a61b61 | 59 | |
| sigtap/TabelaUnificada_200801.zip | whole | ftp://ftp2.datasus.gov.br/public/sistemas/tup/downloads/TabelaUnificada_200801.zip | 2009-01-08T00:00 | 96665399381c081ea7922d745b4489e4c022734070c86e1463234ed90a6774d9 | 4190 | server_modified from MDTM; records are tb_procedimento.txt lines |
| sigtap/tb_procedimento_layout_202609.txt | member | ftp://ftp2.datasus.gov.br/public/sistemas/tup/downloads/TabelaUnificada_202609_v2609171117.zip#tb_procedimento_layout.txt | 2026-09-17T11:17 | b1d967812f0895f6a4f0206d902e16d59213aa64cfa08b00dffb878aea179c5b | | archive SHA-256 19d612f6997b5c6fdf32d7d1f8186d110880b658c4776f6a7c22771a2d3f605f; the layout of the newest competência |
