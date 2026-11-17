# Códigos da CID-10 que o CID10.DBF não tem, e o S_CID.DBF do SIH: 2026-10-31

A `aux_cid10` 2.3.0 junta ao `CID10.DBF` os códigos do `tb_cid.txt` do SIGTAP que o
`CID10.DBF` não tem. Este registro diz quais são, de que arquivos vêm e o que o
`S_CID.DBF` do `TAB_SIH.zip` diz sobre eles (issue #151).

## Arquivos lidos

| Arquivo | SHA-256 |
| --- | --- |
| `SIM/CID10/TABELAS/CID10.DBF` (registrado, `sim-tabelas-cid10-5c755bcdabc5`) | `5c755bcdabc5396cfa1eff2aa3f6189aa7256b01eb10ce6ca890be0dda4dd717` |
| `TabelaUnificada_202610_v2610271043.zip` (registrado, `sigtap-525e5ef197da`) | `525e5ef197da5133ed3177f42b56cb341057668af8da2fdc7f6674bcc25af5cd` |
| `tb_cid.txt` desse zip | `611805b5e14c3495c0e28780b13d86c68cdd047c0668c614ef770160212a508d` |
| `SIHSUS/200801_/Auxiliar/TAB_SIH.zip`, lido em 2026-10-31 (6.083.658 bytes; não é nenhum dos TAB_SIH registrados) | `21e42384645a9386add9f3644264145f39fc00bbb602f305d87bd0793b7e476b` |
| `DBF/S_CID.DBF` desse zip (941.441 bytes, 2026-10-15 22:12) | `f8d3a5874035ecd2d974da6b7a5707fa4a04aebbfb1759a4ea44cac3ebde5a74` |

## Contagem

O `CID10.DBF` tem 14.257 códigos e o `tb_cid.txt` 14.246 (CO_CID nas colunas 1 a 4, pelo
`tb_cid_layout.txt`). 25 códigos do `tb_cid.txt` não estão no `CID10.DBF`:

- `A925` (doença pelo vírus Zika) e `A97` (dengue);
- `C823`, `C824`, `C825`, `C826` (linfoma folicular);
- `N182`, `N183`, `N184`, `N185` (doença renal crônica, estádios 2 a 5);
- `P354` (doença congênita do vírus Zika);
- `U09`, `U099`, `U10`, `U109` (covid-19);
- `W460` a `W469` (contato com agulha hipodérmica, por local).

A primeira versão desta mudança trazia só nove (N182 a N185, P354, U09, U099, U10 e
U109); a lista foi tirada do build, que agora inclui todo código do `tb_cid.txt` que o
`CID10.DBF` não tem. 36 códigos do `CID10.DBF` não estão no `tb_cid.txt` e continuam
como estão. `N181` e `O987` não estão em nenhum dos dois arquivos.

## O que o S_CID.DBF do TAB_SIH diz desses 25

Lido com `dbfread2`, coluna `CD_COD`:

- `N182` e `N185`: `CID NÃO IDENTIFICADO` (e `N181`, que não está na `aux_cid10`).
- `N183` e `N184`: sem linha.
- `W460` a `W469`: com o texto do `tb_cid.txt`, cortado em 50 caracteres.
- `A925`, `A97`, `C823` a `C826`, `P354`, `U09`, `U099`, `U10` e `U109`: sem linha.

`CID NÃO IDENTIFICADO` é o texto que o S_CID também usa para o `0` e para categorias
completadas com zero no SIA (`docs/sources/vocabularios.md`): marca que a tabela do
TabWin não tem nome para o código, não é um nome de doença. O `tb_cid.txt` dá nome a
`N182` e `N185`; a `aux_cid10` usa esse nome.
