# omnisus

Importa bases públicas de saúde do Brasil (DATASUS, IBGE, CNES) para um lake
[DuckLake](https://ducklake.select), no seu computador, no Google Drive ou na nuvem, com
a procedência necessária para citar cada resultado.

*Brazilian public health data (DATASUS, IBGE, CNES) in a DuckLake lake (on your computer, on Google
Drive or in the cloud), with the provenance needed to cite it. Documentation: <https://raphaelfh.github.io/omnisus/>.*

> [!WARNING]
> **Trabalho em construção (v0.1).** A API ainda pode mudar entre versões menores, e
> nem todo dicionário foi conferido contra o documento oficial. Antes de publicar um
> número, confira as contagens, as colunas e os rótulos (veja
> [Confira antes de usar](#confira-antes-de-usar)). Um rótulo errado é um bug:
> [abra uma issue](https://github.com/raphaelfh/omnisus/issues/new/choose).

## Instalação

Python 3.12 ou mais novo:

```bash
pip install "omnisus @ git+https://github.com/raphaelfh/omnisus"
```

Com o decodificador Rust opcional (Linux x86_64, macOS arm64/x86_64, Windows x86_64),
instale os dois pacotes a partir da página da release:

```bash
pip install omnisus omnisus-dbf \
  --find-links https://github.com/raphaelfh/omnisus/releases/expanded_assets/v0.1.0
```

Sem ele, o Python decodifica os mesmos arquivos.

## Início rápido

Sem instalar nada:

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/raphaelfh/omnisus/blob/main/notebooks/colab.ipynb)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sim_obitos.py)

O Colab baixa os óbitos de Roraima em 2023, põe rótulos, confere as colunas e imprime a
citação, com o lake opcionalmente no seu Google Drive. O molab abre os notebooks marimo
de cada base. Outros caminhos (marimo no seu computador, Jupyter) estão em
[Comece aqui](https://raphaelfh.github.io/omnisus/pesquisa/).

Em Python:

```python
import omnisus as odb

dados = odb.load("sim_obitos", years=[2023], ufs=["RR"])             # baixa e devolve as linhas
dados = odb.label("sim_obitos", dados, columns=["sexo", "racacor"])  # + sexo_rotulo, racacor_rotulo
odb.check_columns("sim_obitos", dados)                               # vazios, códigos sem rótulo, datas
```

O lake fica em `data/raw/` no diretório de trabalho, e um segundo `load` do mesmo
recorte não baixa nada. Toda função documenta seus parâmetros com um exemplo:
`help(odb.load)`.

Para ir além:

- [Guia do pesquisador](https://raphaelfh.github.io/omnisus/pesquisa/): qual base
  responde a cada pergunta, o que um registro representa e como citar.
- [Notebooks](notebooks/README.md): um por base, com as mesmas seis etapas, que abrem no
  navegador pelo molab.
- [Getting Started](https://raphaelfh.github.io/omnisus/guides/getting-started/):
  onde fica o lake, Colab, linha de comando e lakes na nuvem.
- [Bases e argumentos](https://raphaelfh.github.io/omnisus/datasets/): cada base, com o
  que passar em `years`, `ufs` e `months` e quais colunas têm rótulo. É gerada do
  código a cada versão, como a [API](https://raphaelfh.github.io/omnisus/api/);
  `help(odb.load)` mostra o mesmo na versão instalada.

## Confira antes de usar

- **Contagens.** Compare o total de linhas com o que o DATASUS publica (TabNet, painéis
  oficiais) antes de analisar. `odb.check_columns` mostra, por coluna, a proporção de
  vazios, os códigos que o dicionário não conhece e as datas mínima e máxima.
- **Rótulos.** Um código que o dicionário não conhece fica sem rótulo (`None`); ele nunca
  é adivinhado. Cada mapa de códigos diz se foi conferido no documento oficial:

  ```python
  campo = next(f for f in odb.describe_dataset("sim_obitos")["fields"]
               if f["field"]["name"] == "sexo")
  [(c["status"], c["evidence"]) for c in campo["claims"] if c["target"] == "/field/codes"]
  # status: verified_in_source, conflicting ou unreviewed; evidence: documento e página
  ```

  Só use um rótulo `unreviewed` ou `conflicting` depois de conferir o documento você
  mesmo.
- **Escopo das regras.** Idade em anos, sexo e datas harmonizados só aparecem para os
  arquivos cujo SHA-256 foi auditado (`describe_dataset(...)["analytics"]`); os outros
  saem como publicados.

## De onde vêm os dados e os rótulos

| O que | Onde |
| --- | --- |
| Arquivo de origem de cada linha importada | `reader.publications()` e `odb.cite(reader)` num `odb.LakeReader()`: caminho no servidor, SHA-256, `snapshot_id` |
| Diretório do FTP de cada base | [Bases e argumentos](https://raphaelfh.github.io/omnisus/datasets/) |
| Dicionários (de-para de códigos, descrições, tipos) | [`src/omnisus/data/dicionarios/<base>.yaml`](src/omnisus/data/dicionarios/), campo `x-decode` |
| Documentos oficiais citados (PDF, TabWin), com URL e SHA-256 | [`src/omnisus/data/dicionarios/sources/registry.json`](src/omnisus/data/dicionarios/sources/registry.json) |
| Tabelas CNV do TabWin de onde saem muitos rótulos | [`src/omnisus/data/dicionarios/sources/cnv/`](src/omnisus/data/dicionarios/sources/cnv/) |
| Auditorias que sustentam as regras (contagens, hashes, reprodução) | [`evidence/`](evidence/) |

O [dicionário de dados](https://raphaelfh.github.io/omnisus/dicionario/) explica como
ler esses arquivos e como conferir um rótulo.

## Como contribuir

Leia o [CONTRIBUTING.md](CONTRIBUTING.md). Em resumo: todo fato no código ou na
documentação vem do servidor do DATASUS ou de um arquivo com SHA-256 registrado, todo
teste roda sobre trechos de arquivos reais, e o repositório é público. Um rótulo
errado, uma base que falta ou uma contagem que não bate com o DATASUS são boas
primeiras issues.

## Licença

[MIT](LICENSE).
