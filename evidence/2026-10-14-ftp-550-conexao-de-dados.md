# O 550 do FTP do DATASUS que não é "não existe" — 2026-10-14

O servidor `ftp.datasus.gov.br` responde `550` em dois casos diferentes. O omnisus
tratava todo `550` como "o caminho não existe" e não tentava de novo
(`src/omnisus/sources/datasus_ftp/_ftp.py`, `is_missing`). Este registro mostra as duas
respostas e como distingui-las sem comparar texto.

## O que o servidor responde quando o caminho não existe

Sessão anônima a partir de uma rede no Brasil, em 2026-10-14. Saudação:
`220 Microsoft FTP Service`.

| Comando | Resposta |
| --- | --- |
| `CWD /dissemin/publicos/NAOEXISTE` | `550 The system cannot find the file specified. ` |
| `CWD /dissemin/publicos/SIM/CID10/DORES` | `250 CWD command successful.` |
| `SIZE DORR2022.dbc` | `213 275221` |
| `SIZE NAOEXISTE.dbc` | `550 The system cannot find the file specified. ` |
| `RETR NAOEXISTE.dbc` | `550 The system cannot find the file specified. ` |
| `LIST /dissemin/publicos/NAOEXISTE` | `550 The system cannot find the file specified. ` |

`DORR2022.dbc` baixado nessa sessão: 275.221 bytes, SHA-256
`6643344fe1ab587d648e5e0ea8cf7e3ef9e5b5b7021a12dcbbc54f5724d2ec65`.

`SIZE` e `CWD` usam só a conexão de controle: respondem sem abrir conexão de dados.

## O que o servidor responde quando a conexão de dados cai

Sessão anônima a partir de um kernel do molab (rede AS33425, CoreWeave, EUA), em
2026-10-13, no diretório `/dissemin/publicos/SIM/CID10/DORES`. O `CWD` respondeu `250` e
o `PASV`, `227 Entering Passive Mode (...)`. Na mesma conexão de controle, 12 operações
que abrem conexão de dados, alternando `LIST` e `RETR DORR2022.dbc`:

| Resultado | `LIST` | `RETR` |
| --- | --- | --- |
| deu certo | 1 | 2 |
| `550 The network connection was aborted by the local system. ` | 1 | 2 |
| `425 Cannot open data connection.` | 4 | 2 |

Os `RETR` que deram certo trouxeram os 275.221 bytes. Em 8 importações seguidas de
`sim_obitos` RR 2022 com o omnisus 0.2.3 (2 listagens e 1 download cada), nenhuma
terminou: 7 pararam em `FtpPathNotFound` com o `550 ... aborted` e uma em
`FtpUnavailable` depois de 3 tentativas.

## Como o omnisus distingue os dois

- **Listagem.** O `CWD` vem antes do `LIST`. Se ele respondeu `250`, o diretório existe,
  e um `550` no `LIST` que vem depois é a conexão de dados caindo: falha transitória,
  com nova tentativa. Um `550` no próprio `CWD` continua sendo "não existe".
- **Download.** Um `550` no `RETR` é "não existe" só se o `SIZE` do mesmo arquivo também
  responder `550`. Se o `SIZE` responder `213`, o arquivo está lá e a falha é
  transitória.

O `425` já era transitório (`ftplib.error_temp`).

Isso deixa o erro honesto, mas não faz a importação funcionar no molab: com ~25% de
acerto por operação e 3 tentativas, cada operação passa em ~58% das vezes. Os notebooks
dizem para importar no computador ou no Colab.
