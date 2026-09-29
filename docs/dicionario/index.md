# Dicionário de dados: de onde vem cada rótulo

Cada base tem um dicionário: o que cada coluna significa, os códigos e seus rótulos (o
de-para), e de onde veio cada uma dessas afirmações. Esta página mostra onde ele está e
como conferir um rótulo antes de usá-lo.

!!! warning "Confira antes de publicar"
    Nem todo mapa de códigos foi conferido contra o documento oficial. Um rótulo
    `unreviewed` ou `conflicting` pode estar errado; confira a fonte você mesmo e,
    se estiver, [abra uma issue](https://github.com/raphaelfh/omnisus/issues/new/choose).

## Onde está

| O que | Arquivo |
| --- | --- |
| Dicionário de uma base (colunas, tipos, códigos em `x-decode`, afirmações e evidências) | `src/omnisus/data/dicionarios/<base>.yaml` |
| Documentos oficiais citados, com URL, SHA-256, tamanho e data | `src/omnisus/data/dicionarios/sources/registry.json` |
| Tabelas CNV e DEF do TabWin de onde saem muitos rótulos | `src/omnisus/data/dicionarios/sources/cnv/` |
| Auditorias das regras de idade, sexo e datas | [`evidence/`](https://github.com/raphaelfh/omnisus/tree/main/evidence) |

Os arquivos vão dentro do pacote instalado: a biblioteca lê tudo offline.

## Conferir um rótulo

```python
import omnisus as sus

meta = sus.describe_dataset("sim_obitos")
campo = next(f for f in meta["fields"] if f["field"]["name"] == "sexo")

campo["field"]["codes"]      # [{'value': '0', 'label': 'Ignorado', ...}, ...]
[(c["status"], c["evidence"]) for c in campo["claims"] if c["target"] == "/field/codes"]
# [('verified_in_source', [{'source_id': 'sim-b4195ac8e0f8', 'pages': [2], ...}])]
campo["sources"]             # URL, SHA-256 e edição do documento citado
```

| `status` | Quer dizer |
| --- | --- |
| `verified_in_source` | O mapa foi comparado com o documento citado, na página indicada. |
| `conflicting` | O mapa atual discorda de outro registrado para o mesmo campo; a `note` e as `issues` do campo dizem o quê. |
| `unreviewed` | Ninguém conferiu ainda. Trate como pista, não como fato. |
| `not_found` | Não aparece nas fontes consultadas; isso não prova que não exista. |

`verified_in_source` confere a transcrição, não a vigência: um mapa conferido no
documento de 2025 não prova que vale para os arquivos de 1996.

## O que a biblioteca faz com o dicionário

- **`sus.label`** acrescenta `<coluna>_rotulo` a partir do `x-decode`. Um código que o mapa
  não conhece fica sem rótulo (`None`); ele nunca é adivinhado.
- **`sus.check_columns`** mostra, por coluna, vazios, códigos sem rótulo e as datas mínima
  e máxima.
- **Categorias harmonizadas** (idade em anos, sexo, datas) só aparecem para arquivos cujo
  SHA-256 foi auditado, listados em `describe_dataset(...)["analytics"]["validated_sources"]`
  ([ADR 0003](../decisions/0003-harmonised-categories-only-for-validated-sources.md)).

## Para ir além

- [Contrato por coluna](contrato.md): os campos de um dicionário e as regras de evidência.
- [Consumo e integração](consumo.md): metadados em JSON e Arrow, projeções analíticas.
- [Manutenção](manutencao.md): como corrigir ou acrescentar um rótulo.
