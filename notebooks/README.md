# Notebooks

Um notebook [marimo](https://marimo.io) por sistema, e `bases.py` para qualquer base,
para pesquisa. Cada um segue as mesmas seis etapas com as mesmas funções da biblioteca:
o que a base registra (`sus.describe_dataset`), descobrir (`sus.available`), baixar e
ler (`sus.load`), conferir (`sus.check_columns`), analisar (`sus.label` e polars) e
citar (`sus.cite`). Troque `BASE`, `UF`, `ANO` (e `MES`) na célula de parâmetros para
outra base ou recorte. `bases.py` lista todas as bases (`sus.describe_datasets()`) e
leva qualquer uma até a citação, sem análise própria. `explorar.py` é diferente: abre
um lake que já existe numa pasta do computador e, com widgets, escolhe
bases e escopos, mostra as linhas, o dicionário de cada base e o perfil de uma coluna e
cita os escopos escolhidos. Ele também importa vários anos, UFs e meses de uma vez, com
um relatório do que houve com cada escopo. Comece pelo
[guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/).

Abrir um notebook não baixa nem grava nada. Rede e escrita ficam atrás de
`EXECUTAR = False` até você mudar a constante (ou passar `-- --executar true`); em
`explorar.py`, atrás do botão *Importar* (ou de `-- --executar true`, ao rodar sem
interface).

| Notebook | Molab | Base | Recorte inicial |
| --- | --- | --- | --- |
| [sim_obitos.py](sim_obitos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py) | SIM · óbitos | RR, 2022 |
| [sinasc_nascidos_vivos.py](sinasc_nascidos_vivos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py) | SINASC · nascidos vivos | RR, 2022 |
| [sih_aih_reduzida.py](sih_aih_reduzida.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py) | SIH · AIH reduzida | RR, jan/2024 |
| [sia.py](sia.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py) | SIA · qualquer tabela, três com análise própria | RR, jan/2024 |
| [cnes_estabelecimentos.py](cnes_estabelecimentos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py) | CNES · estabelecimentos | RR, jan/2024 |
| [ibge_populacao.py](ibge_populacao.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py) | IBGE · população | censo 2022 |
| [sinan.py](sinan.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py) | SINAN · Chagas aguda, hanseníase e tuberculose | nacional, 2023 |
| [medicamentos.py](medicamentos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py) | SIA-AM, estoque Hórus | RR, jan/2024 |
| [bases.py](bases.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/bases.py) | todas as bases do FTP: a lista e qualquer uma até a citação | `cnes_leitos`, RR, jan/2024 |
| [explorar.py](explorar.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/explorar.py) | as bases já no lake, com widgets: importar, escolher escopos, ver as linhas e o dicionário, perfil de uma coluna e citação | o lake em `data/raw` |
| [linkage.py](linkage.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/linkage.py) | todas as bases de uma UF e ano: colunas com o decoder e linkage determinístico | RR, 2022 |

Para começar sem instalar nada, o [notebook do Colab](colab.ipynb)
[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/raphaelfh/omnisus/blob/main/notebooks/colab.ipynb)
percorre a biblioteca de ponta a ponta com Roraima: SIM 2022, SIH processado em janeiro de 2023
e o censo 2022 do IBGE, do download à taxa por 100 mil habitantes e à citação. O
[notebook de exploração do Colab](explorar_colab.ipynb)
[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/raphaelfh/omnisus/blob/main/notebooks/explorar_colab.ipynb)
faz no Colab o que `explorar.py` faz no computador, com o lake no seu Google Drive:
importa escopos, mostra as linhas de um recorte com rótulos, o perfil de uma coluna e a
citação.

## Como abrir

No navegador, sem instalar nada: a badge **Open in molab** de cada notebook.
DuckDB, FTP e o lake local não rodam em `/wasm`. No molab, o download do DATASUS quase
sempre falha: a conexão de dados do FTP cai na maior parte das vezes a partir da rede
dele ([medições](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-10-14-ftp-550-conexao-de-dados.md)). Para baixar dados, use o Colab ou o seu computador.

No seu computador, com a versão do PyPI fixada no cabeçalho PEP 723 de cada notebook:

```bash
uvx marimo edit --sandbox notebooks/sim_obitos.py
```

Para contribuir, com o código de `main` ainda não publicado (rode da **raiz do
repositório** para todos os notebooks usarem o mesmo lake):

```bash
uv sync --locked --extra notebooks
uv run --locked --extra notebooks marimo edit notebooks/sim_obitos.py
```

Para executar as etapas sem interface, com a versão fixada:

```bash
uvx marimo export html --sandbox notebooks/sim_obitos.py \
  -o /tmp/sim_obitos.html -- --executar true
```

Em `explorar.py`, `--base`, `--anos`, `--ufs` e `--meses` (separados por vírgula) e
`--substituir true` dão os valores dos seletores de *Importar*; *Escolher* começa na
base de `--base`. `--lake` indica a pasta do lake e `--linhas`, quantas linhas cada
tabela mostra (10.000 sem o flag; `--todas true` mostra todas). Só `true` liga
`--executar`, `--substituir` e `--todas`:

```bash
uvx marimo export html --sandbox notebooks/explorar.py -o /tmp/explorar.html -- \
  --base sih_aih_reduzida --anos 2023,2024 --ufs RR,AC --meses 1,2,3 --executar true
```

O lake fica em `data/raw/`; `OMNISUS_DATA_DIR` troca a pasta. As tabelas e a citação
dos notebooks de cada base vão para `resultados/<base>/`; `explorar.py` oferece a
citação para baixar.
