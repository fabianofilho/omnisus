# Comece aqui

## O que é

O omnisus importa bases abertas do DATASUS e do IBGE para um lake, uma base de
dados em arquivos que pode ficar no seu computador, no Google Drive (útil no Colab) ou na
nuvem, com o catálogo num PostgreSQL e os arquivos num S3. Cada importação fica registrada num manifesto, com
o arquivo de origem, o SHA-256 dele e a execução que o publicou; é isso que permite
dizer de onde veio cada linha.

## Começar em cinco minutos

Escolha onde rodar. Os três caminhos usam a mesma biblioteca e chegam à mesma tabela.

=== "Google Colab"

    Nada para instalar no seu computador. Abra o notebook, rode as células em ordem e,
    se quiser que os dados fiquem guardados, monte o Google Drive na segunda célula.

    [![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/raphaelfh/omnisus/blob/main/notebooks/colab.ipynb)

    O notebook instala o omnisus, baixa os óbitos de Roraima em 2023, põe rótulos,
    confere as colunas e imprime a citação. Para outra base, troque o nome e o recorte
    (veja [Bases e argumentos](../datasets.md)).

=== "marimo no navegador (molab)"

    Os notebooks de cada base abrem no [molab](https://molab.marimo.io), o serviço do
    marimo, sem instalar nada. Cada um segue as seis etapas abaixo.

    [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py)

    Use a execução em **servidor**, não em WebAssembly: DuckDB e o FTP do DATASUS não
    rodam no navegador.

=== "marimo no seu computador"

    Com o [uv](https://docs.astral.sh/uv/) instalado, um comando abre o notebook num
    ambiente isolado, com a versão do omnisus fixada no próprio arquivo:

    ```bash
    git clone https://github.com/raphaelfh/omnisus.git
    cd omnisus
    uvx marimo edit --sandbox notebooks/sim_obitos.py
    ```

    Rode a partir da raiz do repositório (ou defina `OMNISUS_DATA_DIR`) para todos os
    notebooks usarem o mesmo lake. Para usar o código do checkout em vez da versão
    fixada: `uv sync --locked --extra notebooks` e
    `uv run --locked --extra notebooks marimo edit notebooks/sim_obitos.py`.

=== "Python ou Jupyter"

    ```bash
    pip install "omnisus @ git+https://github.com/raphaelfh/omnisus"
    ```

    ```python
    import omnisus as sus

    dados = sus.load("sim_obitos", years=[2023], ufs=["RR"])
    dados = sus.label("sim_obitos", dados, columns=["sexo", "racacor"])
    sus.check_columns("sim_obitos", dados)
    ```

Abrir um notebook marimo não baixa nem grava nada: rede e escrita ficam atrás de
`EXECUTAR = False` até você mudar a constante. No Colab, cada célula roda quando você
a executa.

## Qual base responde minha pergunta?

| Pergunta | Base | Perfil | Notebook |
| --- | --- | --- | --- |
| Quantas pessoas morreram, de quê, onde moravam? | SIM · óbitos | [perfil](../sources/sim_obitos.md) | [sim_obitos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py) |
| Quantos nasceram, com que peso, com quantas consultas de pré-natal? | SINASC · nascidos vivos | [perfil](../sources/sinasc_nascidos_vivos.md) | [sinasc_nascidos_vivos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinasc_nascidos_vivos.py) |
| Quantas internações hospitalares foram registradas, por qual diagnóstico? | SIH · AIH reduzida | [perfil](../sources/sih_aih_reduzida.md) | [sih_aih_reduzida.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sih_aih_reduzida.py) |
| Que produção ambulatorial foi registrada (sete tabelas: BPA-I, APAC, RAAS)? | SIA · produção ambulatorial | [perfil](../sources/sia.md) | [sia.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sia.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sia.py) |
| Quais estabelecimentos de saúde existem, onde, de que tipo? | CNES · estabelecimentos | [perfil](../sources/cnes_estabelecimentos.md) | [cnes_estabelecimentos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/cnes_estabelecimentos.py) |
| Qual população usar como denominador de uma taxa? | IBGE · população | [perfil](../sources/ibge_populacao.md) | [ibge_populacao.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/ibge_populacao.py) |
| Quantas notificações de doença de Chagas aguda? | SINAN · Chagas aguda | [perfil](../sources/sinan_chagas.md) | [sinan.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinan.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py) |
| Quantas notificações de hanseníase, e como terminou o tratamento? | SINAN · hanseníase | [perfil](../sources/sinan_hanseniase.md) | [sinan.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinan.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py) |
| Quantas notificações de tuberculose, e como terminou o tratamento? | SINAN · tuberculose | [perfil](../sources/sinan_tuberculose.md) | passo a passo genérico do SINAN, sem exemplo de tuberculose: [sinan.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinan.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py) |
| Que medicamentos o SUS registrou em APAC, e que estoque aparece? | Medicamentos | [perfil](../sources/medicamentos.md) | [medicamentos.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py) [![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/medicamentos.py) |

Leia o perfil antes de contar: ele diz o que uma linha representa, de onde vêm as datas
e os municípios e o que ainda está em aberto.

## As seis etapas

Todo notebook de `notebooks/` segue as mesmas etapas, com as mesmas funções da
biblioteca, `import omnisus as sus` e nada mais. Troque `BASE`, `UF`, `ANO` (e `MES`)
na célula de parâmetros para outra base ou outro recorte. Rede e escrita só correm com
`EXECUTAR = True`, ou com `-- --executar true` na exportação.

**1 · O que a base registra.** `sus.describe_dataset(base)` mostra os campos do
dicionário da biblioteca, sem rede.

**2 · Descobrir.** Pergunta ao FTP do DATASUS o que existe agora:
`sus.available_releases(base, ufs=[...], refresh=True)` diz se cada ano está no
diretório final ou no preliminar, e `sus.available(...)` devolve os escopos que podem
ser importados. A população do IBGE não tem inventário: o notebook mostra as edições que
a biblioteca aceita.

**3 · Baixar e ler.** `dados = sus.load(base, years=[...], ufs=[...])` importa o
recorte para o lake e devolve as linhas num DataFrame polars, com os códigos como o
DATASUS publicou. A política padrão (`skip_same`) faz com que rodar de novo não baixe nem
duplique nada. A população usa `sus.import_ibge_populacao`.

**4 · Conferir.** `sus.check_columns(base, dados)` mostra, por coluna, vazios, códigos
sem rótulo e datas fora do esperado. `sus.outdated(base, lake=...)` é usado quando a
base tem diretório preliminar (SIM, SINASC, SINAN); as demais bases do DATASUS são
publicadas num único diretório, e o notebook não chama `outdated` para elas.

**5 · Analisar.** `sus.label(base, dados, columns=[...])` põe o rótulo do dicionário
ao lado de cada código (`sexo` → `sexo_rotulo`), e a análise é polars sobre esse
DataFrame (`group_by`, `agg`, `join`).

**6 · Citar e guardar.** `sus.cite(lake, dataset=base)` nomeia o arquivo do servidor, o
SHA-256, a versão da biblioteca e o snapshot do lake. O notebook grava as tabelas em CSV
e a citação em `resultados/<base>/citacao.txt`. Veja
[Reprodutibilidade](reprodutibilidade.md).

## O lake de pesquisa

Os notebooks gravam no mesmo lake, `data/raw/omnisus.ducklake` (a variável de ambiente
`OMNISUS_DATA_DIR` troca a pasta), e os resultados em `resultados/`, a partir da pasta
onde o notebook roda.

O lake é um só porque uma taxa precisa de duas bases: óbitos por 100 mil habitantes
lê `sim_obitos` e `ibge_populacao`
(`notebooks/ibge_populacao.py`, tabela `obitos_por_100_mil`). Veja
[Indicadores](indicadores.md).

## Cuidados gerais

- **Confira os rótulos e as contagens.** Nem todo mapa de códigos foi conferido contra o
  documento oficial, e um código que o dicionário não conhece fica sem rótulo. Veja o
  status de cada mapa em [De onde vem cada rótulo](../dicionario/index.md) e compare os
  totais com o que o DATASUS publica antes de analisar.
- **Arquivos preliminares mudam.** O DATASUS publica anos preliminares que depois são
  revistos; para o SINAN Chagas, veja a nota citada no
  [perfil](../sources/sinan_chagas.md#armadilhas). Guarde o SHA-256 do arquivo e o
  `snapshot_id` e siga [Reprodutibilidade](reprodutibilidade.md).
- **Um registro não é uma pessoa.** Uma linha do SIM é uma declaração de óbito; uma
  linha do SINAN é uma notificação, não um caso confirmado nem um caso novo. Leia as
  Armadilhas de cada perfil, por exemplo as do
  [SINAN Chagas](../sources/sinan_chagas.md#armadilhas) e as do
  [SINAN hanseníase](../sources/sinan_hanseniase.md#armadilhas).
- **Uma data que passa no formato pode ser impossível.** `sus.check_columns` mostra
  `date_min` e `date_max` de cada campo de data; `*_data_status = 'valid'` só diz que o
  texto é uma data. Nos arquivos de RR e SP de 2022 lidos pelo notebook de linkage há
  autorizações de APAC em 9202, nascimentos em 1366 (RAAS) e mães nascidas em 0980
  (SINASC)
  ([relatório](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-23-linkage-ampliado.md#column-check-of-the-new-bases)).
  Defina a regra de exclusão no seu protocolo, a partir da data do evento
  ([consumo](../dicionario/consumo.md#projecoes-para-analise)).
- **Um escritor por lake de cada vez.** Uma importação local segura uma trava de
  escrita, e uma segunda importação no mesmo lake falha com `WriterBusyError`; um
  `LakeReader` não pega a trava e pode ler durante uma importação
  ([reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#coordinate-writers-and-bound-downloads);
  [getting started](../guides/getting-started.md#4-query)).
- **Abrir um notebook não baixa nada.** Um teste abre cada notebook e falha se houver
  conexão de rede ou escrita no lake de pesquisa
  (`tests/unit/notebooks/test_notebooks_abrem_offline.py`).
