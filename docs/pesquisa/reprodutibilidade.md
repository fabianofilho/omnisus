# Reprodutibilidade

Um resultado é reprodutível quando outra pessoa consegue saber exatamente quais arquivos
entraram, com qual versão da biblioteca, e ler o lake no mesmo estado. Esta página mostra
o que registrar e onde cada informação fica.

## Antes de importar

- **Escolha o `run_id` antes de começar e nunca o reutilize.** Se uma importação for
  interrompida, um escopo ausente de `publications(run_id=...)` não foi gravado com
  aquele `run_id`, porque dados e manifesto são gravados na mesma transação; com um
  `run_id` repetido essa conclusão não vale
  ([reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#inspect-an-interrupted-run)).
  `odb.load`, que os notebooks usam, gera um `run_id` novo a cada chamada; a citação
  de `odb.cite` o nomeia.
- **Use `policy="skip_same"`.** A política padrão é `append`, que acrescenta de novo um
  escopo já importado. `skip_same` compara primeiro a listagem do FTP (caminho,
  tamanho e horário do servidor de cada arquivo) e a versão do parser com a publicação
  ativa: se nada mudou, pula o escopo sem baixar. Qualquer diferença baixa o arquivo e
  compara o SHA-256; com SHA-256 e versão iguais o escopo é pulado, e nos outros casos
  falha
  ([reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#choose-a-replay-policy)).

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
escopos = odb.available("sim_obitos", years=[2022], ufs=["RR"], refresh=True)
relatorio = odb.import_research(
    "sim_obitos", scopes=escopos, target=alvo, run_id="sim-rr-2022-01"
)
for desfecho in relatorio.outcomes:
    print(desfecho.scope, desfecho.status, desfecho.reason)
```

`import_research` exige `run_id` e usa `policy="skip_same"`. Recusa `append`.
`import_dataset(..., policy="append")` continua sendo o comportamento do
importador genérico.

O que cada desfecho quer dizer:

- `ok`: o escopo foi publicado.
- `skipped` com o código `unchanged` e o motivo *same listed files and parser version
  already published* (sem download) ou *same source and parser version already
  published* (depois de baixar e comparar o SHA-256): o mesmo arquivo já estava no lake
  e nada foi duplicado
  (`src/omnisus/sources/datasus_ftp/_runner.py`). Na validação de 2026-09-13, a
  segunda execução do notebook do SIM terminou assim, com 0 linhas importadas e nenhum
  snapshot novo
  ([relatório, §3](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)).
- `skipped` com o código `not_listed`: o arquivo não está na listagem do servidor e
  nada é baixado. Um arquivo listado que responde 550 no download termina em `failed`
  com o código `fetch_failed`, e vale tentar de novo
  (`src/omnisus/sources/datasus_ftp/_runner.py`, docstring de `run_scopes`).
- `failed` com o motivo *different source/parser version exists; request replace
  explicitly*: o escopo já está no lake com outro arquivo ou outra versão do parser
  (`src/omnisus/lake/publication.py`). Não é um erro de rede: veja
  [Quando o DATASUS revisa](#quando-o-datasus-revisa).
- `failed` com *legacy or unmanaged rows in scope*: há linhas sem manifesto nesse escopo
  (`src/omnisus/lake/publication.py`), gravadas por um importador antigo ou por SQL
  direto.

Confira `relatorio.failed`, não o valor verdadeiro ou falso do relatório
([inventory](../guides/inventory.md)).

## O que o manifesto guarda

`LakeReader.publications()` devolve uma linha por publicação
(`src/omnisus/lake/publication.py`, `publications`):

| Campo | O que é | Fonte |
| --- | --- | --- |
| `publication_id` | identificador único (UUID) da publicação | `publication.py`, `uuid4()` |
| `dataset` | a tabela do lake, por exemplo `sim_obitos` | `publication.py` |
| `scope` | o escopo (UF, ano, mês) lido de `scope_json` | `publication.py`, `publications` |
| `release` | `final` ou `prelim`, deduzido de `source_uri` | `publication.py`, `publications` |
| `source_uri` | o endereço do arquivo de origem | `publication.py` |
| `source_sha256` | o SHA-256 do arquivo comprimido baixado | [reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#choose-a-replay-policy) |
| `parser_version` | `dbc-staging-v1:` seguido do SHA-256 do dicionário | `src/omnisus/sources/datasus_ftp/dbf_contract.py`, `publication_parser_version` |
| `run_id` | o `run_id` passado à importação | `publication.py` |
| `published_at` | o instante UTC em que a publicação foi gravada | `publication.py`, `datetime.now(UTC)` |
| `rows` | as linhas publicadas | `publication.py` |
| `active` | `false` depois de um `replace` ou de `delete_scope` | [reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#remove-a-scope) |
| `sources` | um item por arquivo, em ordem (`ordinal`, `source_uri`, `source_sha256`, `source_bytes`, `source_modified`); tamanho e horário ficam vazios em publicações que não os registraram | `publication.py`, `publications` |

O manifesto também guarda `batch_id` e `managed` (`src/omnisus/lake/publication.py`).

```python
with odb.LakeReader(alvo) as leitor:
    for p in leitor.publications(run_id="sim-rr-2022-01"):
        print(p["dataset"], p["scope"], p["release"], p["source_uri"], p["source_sha256"], p["rows"])
```

## Fixar a leitura

O lake guarda um histórico de snapshots. `snapshots()` devolve o histórico do catálogo
inteiro, do mais antigo ao mais novo, com `snapshot_id`, `snapshot_time` e `changes`;
`LakeReader(alvo, snapshot_id=...)` prende a sessão a um snapshot, e sem esse argumento
cada consulta lê o snapshot mais recente (`src/omnisus/lake/session.py`,
`Session.snapshots` e `LakeReader`).

```python
with odb.LakeReader(alvo) as leitor:
    snapshot_id = leitor.snapshots()[-1]["snapshot_id"]

with odb.LakeReader(alvo, snapshot_id=snapshot_id) as leitor:
    print(leitor.connect().sql("SELECT count(*) FROM lake.sim_obitos").pl())
```

Um `snapshot_id` desconhecido gera `CatalogAttachError` (`src/omnisus/lake/session.py`).
Na validação de 2026-09-13, cada um dos oito notebooks criou um snapshot (1 a 8) e a
repetição do SIM não criou nenhum
([relatório, §2 e §3](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-13-guia-pesquisador-validacao.md)).

Cuidado deste guia: `lake.expire_snapshots` remove histórico antigo
([reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#compact-expire-history-and-clean-files));
não expire um snapshot que um trabalho seu cita.

## Quando o DATASUS revisa

Quando o DATASUS move um ano do diretório preliminar para o final, nada muda no lake
sozinho. `odb.outdated(dataset, lake=leitor)` compara os arquivos de cada publicação
ativa (caminho, e tamanho/mtime quando registrados) com o que o servidor lista hoje e
devolve só os escopos que mudaram; não escreve nada, e um escopo que o servidor deixou
de listar não é devolvido (`src/omnisus/__init__.py`, `outdated`).

```python
with odb.LakeReader(alvo) as leitor:
    movidos = odb.outdated("sim_obitos", lake=leitor)
odb.import_dataset(
    "sim_obitos", scopes=movidos, target=alvo, policy="replace", run_id="sim-final-2026-01"
)
```

`replace` valida os dados novos, apaga as linhas do escopo e grava a nova publicação na
mesma transação; a publicação antiga fica no manifesto com `active = false`
([reprocessing and maintenance](../guides/reprocessing-and-maintenance.md#choose-a-replay-policy);
`src/omnisus/lake/publication.py`).

Cuidado deste guia: uma nova importação de um escopo já publicado com `skip_same`
termina em `failed` quando o arquivo mudou, pedindo `replace`
(`src/omnisus/lake/publication.py`). Anote o `snapshot_id` anterior antes de
substituir: um leitor preso a ele continua lendo o lake como estava.

## IBGE

A população do IBGE tem outro modelo de publicação. `odb.import_ibge_populacao` não
aceita `run_id` nem `policy` e não aparece em `publications()`: cada edição é uma
publicação identificada pelo `publication_id` em `ibge_population_manifest`, que guarda
produto, agregado, variável, URL, SHA-256 do corpo da resposta e instante da coleta
([perfil da população](../sources/ibge_populacao.md#detalhes-tecnicos)).

```python
with odb.LakeReader(alvo) as leitor:
    print(
        leitor.connect().sql(
            "SELECT publication_id, product, ano, sha256, url, collected_at "
            "FROM lake.ibge_population_manifest"
        ).pl()
    )
```

Importar a mesma edição duas vezes cria duas publicações, e a visão `ibge_populacao`
passa a falhar (`src/omnisus/sources/ibge/importers/pop.py`, `import_pop_year`). O
notebook da população consulta esse manifesto e não importa uma edição que já está lá
(`notebooks/ibge_populacao.py`).

## Como citar

Use `odb.cite` no lake que você leu. O texto segue o modelo abaixo; os notebooks
gravam o mesmo parágrafo em `resultados/<base>/citacao.txt`, ao lado das tabelas.

```python
with odb.LakeReader(alvo) as leitor:
    snapshot_id = odb.latest_snapshot_id(leitor)
    print(odb.cite(leitor, dataset="sim_obitos", snapshot_id=snapshot_id).text)
```

Modelo para uma base do DATASUS:

```text
<Base> (<dataset>), arquivo <nome do arquivo> (<source_uri>), SHA-256 <source_sha256>,
acessado em <AAAA-MM-DD> pelo DATASUS. Importado com omnisus <versão>, lake snapshot
<snapshot_id>, execução <run_id>.
```

Onde encontrar cada valor:

- `<dataset>`, `<source_uri>`, `<source_sha256>` e `<run_id>`: na publicação, em
  `publications()`; o nome do arquivo é o fim de `source_uri`.
- `<AAAA-MM-DD>`: sugestão deste guia, a data de `published_at`.
- `<versão>`: `odb.__version__`.
- `<snapshot_id>`: o snapshot em que você leu os dados.

Nos notebooks, a citação e o próprio notebook bastam para refazer o resultado: o
código diz o recorte e cada tabela, e a citação diz os arquivos, a versão e o
`snapshot_id`.

Para a população do IBGE, sugestão deste guia: troque o arquivo pelo `url`, o
`source_sha256` pelo `sha256`, a data pela de `collected_at` e a execução pelo
`publication_id` de `ibge_population_manifest`.
