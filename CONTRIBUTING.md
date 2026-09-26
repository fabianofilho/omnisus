# Como contribuir

Obrigado por ajudar. O omnisus existe para que um número tirado do DATASUS possa ser
conferido e citado; toda contribuição segue essa ideia.

## Princípios

O [`AGENTS.md`](https://github.com/raphaelfh/omnisus/blob/main/AGENTS.md) é o contrato
de toda mudança, feita por uma pessoa ou por um agente; esta seção o resume. Se os dois
divergirem, vale o `AGENTS.md`.

**Os pilares**, o que o pesquisador pode esperar do omnisus:

1. **Citável.** Cada linha importada leva ao arquivo do servidor de onde veio: a
   publicação registra o recorte, o caminho e o SHA-256, e `odb.cite` gera a citação.
2. **Nada adivinhado.** O código fica como o DATASUS publicou; o rótulo vem só do
   dicionário, e um código desconhecido fica sem rótulo. Cada mapa de códigos diz se
   foi conferido no documento oficial.
3. **Conferível.** Quem duvida de um fato consegue checá-lo: documentos com URL e
   SHA-256, auditorias em `evidence/`, `odb.check_columns` para os dados.
4. **Simples.** Um mecanismo para cada coisa, nada de código morto, código e
   documentação que se leem uma vez.
5. **Público.** Nada sobre pessoas ou sobre o seu computador entra no repositório.

**As cinco regras**, como uma mudança cumpre os pilares (detalhes em
[`AGENTS.md`](https://github.com/raphaelfh/omnisus/blob/main/AGENTS.md#zero-assumption-policy)):

1. Todo fato vem do servidor do DATASUS ou de um arquivo com SHA-256 registrado;
   "não publicado" exige a mesma prova que "publicado".
2. Os testes rodam sobre trechos de arquivos reais, registrados no `FIXTURES.md`.
3. Teste vermelho primeiro; o PR mostra a execução vermelha.
4. Nada entra sem consumidor ou teste; o PR lista o que apagou.
5. Prefira o mais simples e legível.

**O repositório é público.** Nada de credenciais, caminhos do seu computador, dados
pessoais ou arquivos de trabalho (planos, logs, transcrições) em commits, issues ou
PRs; a lista completa está em
[`AGENTS.md`](https://github.com/raphaelfh/omnisus/blob/main/AGENTS.md#boundaries).
Planos e discussões vão para as issues, não para arquivos no repositório.

## Relatar um problema

Use os [formulários de issue](https://github.com/raphaelfh/omnisus/issues/new/choose).
Para um rótulo ou dado incorreto, diga a base, a coluna, o código, o arquivo e o
recorte (UF, ano, mês), o que o omnisus mostra e o que o documento oficial diz, com o
link e a página.

## Preparar o ambiente

```bash
git clone https://github.com/raphaelfh/omnisus.git
cd omnisus
uv sync --locked --all-extras
uv run pre-commit install
```

Abrir um lake instala a extensão `ducklake` do DuckDB; sem ela em cache, o ambiente
precisa de acesso ao repositório de extensões do DuckDB.

## Conferir antes do PR

Os mesmos passos do CI:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run marimo check --strict --ignore-scripts notebooks
uv run python scripts/gen_datasets_doc.py --check
uv run pytest -m "not e2e and not perf" -n auto
uv run mkdocs build --strict
```

Testes que acessam o servidor do DATASUS levam os marcadores `integration` e `e2e` e
ficam fora do CI de pull request.

## Como mudar o comportamento

1. **Teste vermelho primeiro**, sobre um trecho de arquivo real do DATASUS em
   `tests/fixtures/`. Registre o arquivo no
   [`tests/fixtures/FIXTURES.md`](https://github.com/raphaelfh/omnisus/blob/main/tests/fixtures/FIXTURES.md) com URL, data do servidor
   e SHA-256; `scripts/dbc_excerpt.py` corta um trecho válido de um DBC grande. Bytes
   sintéticos só para entrada malformada do decodificador.
2. **Mude o código** até o teste passar. Nada entra sem consumidor ou teste, e o que
   perde o último consumidor sai no mesmo PR.
3. **No PR**, cole a execução vermelha e liste o que foi apagado.

### Corrigir um rótulo ou uma descrição

Os dicionários ficam em `src/omnisus/data/dicionarios/<base>.yaml`; os códigos e
rótulos estão em `x-decode`, e cada afirmação tem uma `claim` com status e evidência.

1. Registre o documento oficial em
   `src/omnisus/data/dicionarios/sources/registry.json` (URL, SHA-256, tamanho, data).
2. Corrija o valor e a `claim` com a página ou o trecho que o sustenta.
3. Se o rótulo vem de uma tabela CNV do TabWin, regenere com
   `uv run python scripts/metadados/gerar_decode_cnv.py` em vez de editar à mão. Os
   dicionários do SINAN e dos subconjuntos do SIM também são gerados
   (`gerar_sinan.py`, `gerar_subconjuntos_sim.py`).

O passo a passo, com os critérios de revisão, está em
[Manutenção dos dicionários](https://github.com/raphaelfh/omnisus/blob/main/docs/dicionario/manutencao.md).

### Acrescentar uma base

1. Leia a listagem do diretório no servidor e acrescente a linha ao registro em
   `src/omnisus/sources/datasus_ftp/datasets.py`.
2. Gere o dicionário físico a partir de um arquivo real com
   `scripts/gen_dicionario.py`, e o trecho de teste com `scripts/dbc_excerpt.py`.
3. Regenere a página de datasets: `uv run python scripts/gen_datasets_doc.py`.

## Documentação

O site é gerado com MkDocs a partir de `docs/` (`uv run mkdocs serve`). Páginas para
pesquisadores (`docs/pesquisa/`, `docs/sources/`, `docs/dicionario/`) são em português;
guias técnicos e a referência da API, em inglês. `docs/datasets.md` é gerado: não edite
à mão.

## Versões

O procedimento de release está em [`RELEASE.md`](https://github.com/raphaelfh/omnisus/blob/main/RELEASE.md); as mudanças de cada
versão, no [`CHANGELOG.md`](https://github.com/raphaelfh/omnisus/blob/main/CHANGELOG.md).
