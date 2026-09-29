# Ferramentas de metadados

Utilitários de desenvolvimento e consulta ao contrato público do pacote. Pela
biblioteca, `sus.describe_dataset` devolve os mesmos metadados.

| Local | Responsabilidade |
| --- | --- |
| `scripts/metadados/` | Consultar, validar e gerar os dicionários |
| `scripts/metadados/validar_fonte.py` | Audita mais uma fonte para as regras analíticas de um dataset; com `--accept`, registra-a |
| `scripts/metadados/gerar_decode_cnv.py` | Escreve o `x-decode` dos campos que uma tabela CNV do TabWin decodifica |
| `scripts/metadados/gerar_sinan.py` | Copia os campos de `sinan_bloco_comum.yaml` para os dicionários SINAN |
| `scripts/metadados/gerar_subconjuntos_sim.py` | Escreve em DOINF, DOMAT e DOEXT a definição de `sim_obitos` de cada campo comum |
| `docs/dicionario/` | Documentação, contrato público e exemplos históricos identificados |
| `src/omnisus/data/dicionarios/` | Dicionários usados pela biblioteca |
| `evidence/` | Evidências das auditorias, com SHA-256 |

Na raiz do checkout, usando o ambiente do projeto:

```bash
# Coluna resolvida pelo pacote; JSON validado pode ser consumido por outros programas
uv run --locked --extra dev python scripts/metadados/consultar.py --json

# Outro campo, com fontes e revisão declaradas
uv run --locked --extra dev python scripts/metadados/consultar.py \
  --dataset sih_aih_reduzida --field cod_idade --json

# Exemplo histórico 0.1.0-draft, preservado para comparação
uv run --locked --extra dev python scripts/metadados/consultar.py \
  --metadata docs/dicionario/exemplos/sim_obitos.sexo.json --json

# Verificação de transporte por coluna
uv run --locked --extra dev python scripts/metadados/consultar.py --arrow
```

`consultar.py` usa `jsonschema` (extra `dev`); o modo `--arrow` também usa `pyarrow`. Os
caminhos padrão são independentes do diretório de execução; caminhos fornecidos
como argumentos são relativos ao diretório atual. Só `validar_fonte.py` usa a rede:
baixa do FTP do DATASUS o arquivo listado para o escopo. Veja
[contrato e limitações](../../docs/dicionario/index.md).

`auditar_contrato.py --target <target> --snapshot-id 5 --out <diretorio>` registra
schemas, publicações, SQL e agregados via `LakeReader` somente leitura.
`--acceptance-only` verifica a projeção pública, os estados de conversão e a
preservação de contagens, schemas e histórico de snapshots. Não exporta linhas
individuais; requer acesso ao lake indicado e não faz parte da CI com fixtures.
`--decode-coverage` lista, por dataset do snapshot, os valores sem chave exata no
`x-decode` (sem aparar espaços nem converter para inteiro).

`auditar_arquivos.py --manifest <json> --out <json>` audita DBCs completos fora do
lake: confere hash, nome/escopo e modalidade, valida o parsing e executa a projeção
pública, reconciliando contagens e comparando SQL com Python por valor distinto.
Exporta apenas schemas e agregados; não altera dados ou regras. `--candidate`
avalia as regras antes de incluir uma identidade, sem conferir aplicabilidade.
O [manifesto e o relatório de exemplo](../../evidence/2026-09-14-extensao-regras/README.md)
registram também a comprovação de modalidade do SINASC no diretório legado.
