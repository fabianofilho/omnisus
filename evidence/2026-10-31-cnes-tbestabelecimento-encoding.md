# Encoding do tbEstabelecimento do CNES: latin-1 ou cp1252? 2026-10-31

`import_cnes_master_ftp` lê `tbEstabelecimentoAAAAMM.csv` como `latin-1`
(`src/omnisus/sources/cnes/importers/master_ftp.py`, `read_base`). O SIGTAP, do mesmo
servidor, é lido como `cp1252` (`src/omnisus/sources/sigtap/__init__.py`). Este registro
mede o arquivo real para decidir.

## O arquivo

Baixado por FTP anônimo de `ftp://ftp.datasus.gov.br/cnes/BASE_DE_DADOS_CNES_202312.ZIP`
em 2026-10-31.

| Item | Valor |
| --- | --- |
| Tamanho do ZIP (`SIZE`) | 576.187.912 bytes |
| `MDTM` | `20240112212745` |
| SHA-256 do ZIP | `b7933bb5af98e594d3b39652d28c1129b03844c2715594138cb264cc8d51bd42` |
| Membro lido | `tbEstabelecimento202312.csv`, 233.372.582 bytes |
| SHA-256 do membro | `e58b27ca69d1c2a0d938d8841df3359db3420ffae4571e8c194f1c9e1c7dcf9c` |

O SHA-256 do ZIP é o mesmo de `tests/fixtures/FIXTURES.md` para
`cnes_base/BASE_DE_DADOS_CNES_202312.ZIP`: é o mesmo arquivo do servidor.

## O que os bytes dizem

Contagem de bytes do membro inteiro (um `collections.Counter` sobre o conteúdo):

| Faixa | Bytes |
| --- | --- |
| `0x80` a `0x9F` | **0** |
| `0x81`, `0x8D`, `0x8F`, `0x90`, `0x9D` (sem caractere em cp1252) | 0 |
| `0xA0` a `0xFF` | 12.054 |
| Decodifica como UTF-8? | não (`0xAA` na posição 4939 não é início válido) |

Os 12.054 bytes acima de `0xA0` estão em 10 colunas, nenhuma delas de nome de
estabelecimento: `CO_REGIAO_SAUDE` (8.177), `NU_ALVARA` (3.055), `CO_USUARIO` (447),
`NO_USUARIO_GEO` (260), `REG_DIRETORCLN` (49), `NO_EMAIL` (48), `NU_TELEFONE` (11),
`NO_URL` (5), `CO_DISTRITO_SANITARIO` (1) e `CO_DISTRITO_ADMINISTRATIVO` (1). Exemplos
decodificados: `ª` e `§` em `CO_REGIAO_SAUDE` (`7ª`), `º` e `°` em `NU_ALVARA`, `Ã` e `Ç`
em `CO_USUARIO`. `NO_RAZAO_SOCIAL` e `NO_FANTASIA` só têm ASCII nas 509.875 linhas.

## Decisão

Fora de `0x80` a `0x9F`, `latin-1` e `cp1252` dão o mesmo caractere para cada byte. Como o
arquivo não tem nenhum byte nessa faixa, as duas decodificações são idênticas nele, e nos
campos que o importador usa (os dois nomes) não há sequer byte acima de `0x7F`. O arquivo
não distingue as duas.

Fica `latin-1`: ela define os 256 bytes e nunca levanta erro, enquanto `cp1252` levantaria
`UnicodeDecodeError` se um mês futuro trouxesse `0x81`, `0x8D`, `0x8F`, `0x90` ou `0x9D`
(mesmo critério dos dicionários DBF, por exemplo
`src/omnisus/data/dicionarios/cnes_estabelecimentos.yaml`). O `cp1252` do SIGTAP vale para
outro arquivo, texto de largura fixa de outro servidor (`ftp2.datasus.gov.br`); esta
medida não o altera.

Medido só em 202312. Outro mês pode ter bytes em `0x80` a `0x9F`; se tiver, a decisão
pede nova medida.

## Outras contagens do mesmo arquivo

Medidas com `csv.DictReader` (`;`, latin-1) sobre o mesmo membro; as decisões de
`read_base` citam estas linhas.

| Contagem | Valor |
| --- | --- |
| Linhas | 509.875 |
| `TP_PFPJ=3` (pessoa jurídica) | 354.732 |
| `TP_PFPJ=1` (pessoa física) | 155.143 |
| Pessoa física com `NO_FANTASIA` preenchido | 155.139 |
| Pessoa física com `NO_RAZAO_SOCIAL` preenchido | 155.142 |
| Linhas sem `NO_FANTASIA` e sem `NO_RAZAO_SOCIAL` | 0 |
| `CO_CNES` que aparece em mais de uma linha | 0 |
