# Notebooks

Um notebook [marimo](https://marimo.io) por base, para pesquisa. Todos seguem as
mesmas seis etapas com as mesmas funções da biblioteca: o que a base registra
(`odb.describe_dataset`), descobrir (`odb.available`), baixar e ler (`odb.load`),
conferir (`odb.check_columns`), analisar (`odb.label` e polars) e citar (`odb.cite`).
Troque `BASE`, `UF` e `ANO` na célula de parâmetros para outra base ou recorte. Comece
pelo [guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/).

Abrir um notebook não baixa nem grava nada. Rede e escrita ficam atrás de
`EXECUTAR = False` até você mudar a constante (ou passar `-- --executar true`).

| Notebook | Molab | Base | Recorte inicial |
| --- | --- | --- | --- |
| [sim_obitos.py](sim_obitos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py) | SIM · óbitos | RR, 2022 |
| [sinasc_nascidos_vivos.py](sinasc_nascidos_vivos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py) | SINASC · nascidos vivos | RR, 2022 |
| [sih_aih_reduzida.py](sih_aih_reduzida.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py) | SIH · AIH reduzida | RR, jan/2024 |
| [sia.py](sia.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py) | SIA · sete tabelas | RR, jan/2024 |
| [cnes_estabelecimentos.py](cnes_estabelecimentos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py) | CNES · estabelecimentos | RR, jan/2024 |
| [ibge_populacao.py](ibge_populacao.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py) | IBGE · população | censo 2022 |
| [sinan.py](sinan.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py) | SINAN · Chagas aguda e hanseníase | nacional, 2023 |
| [medicamentos.py](medicamentos.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py) | SIA-AM, estoque Hórus | RR, jan/2024 |
| [linkage.py](linkage.py) | [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/linkage.py) | todas as bases de uma UF e ano: colunas com o decoder e linkage determinístico | RR, 2022 |

Para começar sem instalar nada, o [notebook do Colab](colab.ipynb)
[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/raphaelfh/omnisus/blob/main/notebooks/colab.ipynb)
faz o caminho inteiro com o SIM de Roraima: instalar, baixar, rotular, conferir e citar.

## Como abrir

No navegador, sem instalar nada: a badge **Open in molab** de cada notebook.
DuckDB, FTP e o lake local não rodam em `/wasm`.

No seu computador, com o commit fixado no cabeçalho PEP 723 de cada notebook:

```bash
uvx marimo edit --sandbox notebooks/sim_obitos.py
```

A partir de um checkout, com o código local (rode da **raiz do repositório** para
todos os notebooks usarem o mesmo lake):

```bash
uv sync --locked --extra notebooks
uv run --locked --extra notebooks marimo edit notebooks/sim_obitos.py
```

Para executar as etapas sem interface:

```bash
uv run --locked --extra notebooks marimo export html notebooks/sim_obitos.py \
  -o /tmp/sim_obitos.html -- --executar true
```

O lake fica em `data/raw/`; `OMNISUS_DATA_DIR` troca a pasta. As tabelas e a citação
de cada notebook vão para `resultados/<base>/`.
