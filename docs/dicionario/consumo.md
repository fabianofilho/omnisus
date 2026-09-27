# Consumo dos metadados

A biblioteca fornece `describe_dataset`, `label`, `display_row` e `analytical_projection`.
Elas funcionam offline com os recursos do wheel. Consultar metadados não abre um
lake nem baixa documentos. O contrato resolvido é `1.0.0`; a versão editorial do
dicionário e a versão da regra analítica são informações separadas.

## Definições e apresentação

```python
import omnisus as sus

metadata = sus.describe_dataset("sim_obitos")
sexo = next(item for item in metadata["fields"] if item["field"]["name"] == "sexo")
print(sexo["field"]["logical_type"])
print(sexo["claims"])
print(metadata["metadata_hash"])
print(sus.display_row("sim_obitos", {"idade": "469", "sexo": "2"}))  # sexo: "Feminino"
```

Cada chamada devolve dados independentes. `fields` contém documentos por coluna,
com referências resolvidas e estados de revisão; `schema.fields` preserva as
definições de autoria para consumidores de apresentação. Tipos legados são
**descritivos**: nenhum deles autoriza cast ou recodificação automática.
`label` (DataFrame) e `display_row` (uma linha) usam a mesma consulta: cada código
com mapa `x-decode` ganha o rótulo do dicionário, e um código que o mapa não
conhece fica sem rótulo (`None`). Datas, idades e horas saem como publicadas;
idade, sexo e datas comparáveis vêm só das projeções abaixo.

`physical_type` descreve o documento de origem, com comprimento desconhecido como
`null`. O tipo SQL efetivo vem de `DESCRIBE` no snapshot da consulta. Os valores
originais do lake continuam preservados.

## Projeções para análise

As regras confirmam apenas os arquivos SIM/SIH/SINASC/SINAN/SIA identificados por escopo,
modalidade e SHA-256 em `metadata["analytics"]["validated_sources"]`. Outro arquivo,
mesmo da mesma UF/ano, não herda automaticamente a interpretação. A função não
consulta o lake: o chamador deve fornecer schema e identidades do mesmo snapshot,
verificando que as publicações representam todas as linhas dos escopos selecionados.

```python
import omnisus as sus

target = "ducklake:./data/omnisus-v2.ducklake"
with sus.LakeReader(target, snapshot_id=5) as reader:
    con = reader.connect()
    schema = {row[0]: row[1] for row in con.sql("DESCRIBE lake.sim_obitos").fetchall()}
    publications = [row for row in reader.publications()
                    if row["dataset"] == "sim_obitos" and row["active"] and row["managed"]]
    contexts = [sus.SourceContext.from_publication(row) for row in publications]
    projection = sus.analytical_projection("sim_obitos", observed_schema=schema, scopes=contexts)
    print(projection.rule_version, projection.metadata_hash)
    print(projection.unavailable)
```

Depois de verificar a cobertura do manifesto, o consumidor compõe uma subconsulta
com `DerivedColumn.expression AS DerivedColumn.name`. Os nomes de origem são
resolvidos/escapados pela biblioteca. Filtros de usuário continuam vinculados por
parâmetros na consulta do consumidor. As expressões executam em SQL nativo, sem
UDF Python por registro e sem criar views persistentes.

As colunas disponíveis são `idade_anos_completos`, `idade_status`, `idade_quantidade`,
`idade_unidade`, `sexo_categoria`, `sexo_status`, `<campo>_data` e `<campo>_data_status`.
Estados distinguem `valid`, `missing`, `ignored`, `invalid` e `unsupported`; nenhum
deles deve virar zero por conveniência. Numa data, `valid` quer dizer só que o texto é um
dia do calendário no formato do dicionário: a projeção não julga se a data é possível.
`AMRR2401`, processado em 2024-01, autoriza APACs em 2027-12-29 e
2029-12-29; `BIRR2201` tem nascimento em 1892-11-05; o SIH tem nascimento em 1899-12-30.
A biblioteca não aplica limite de plausibilidade; a regra fica com a análise: compare com
a data do evento ou com o mês de processamento, e veja `date_min`/`date_max` em
`sus.check_columns`. `SIM 400` significa zero anos completos com
precisão menor de um ano, não zero dias. Faixas etárias pertencem ao relatório.

`idade_quantidade` e `idade_unidade` (`minute`, `hour`, `day`, `month` ou `year`)
guardam a idade como a fonte a registrou: no SIM, `310` vira 10 `month` e 0 anos
completos. Em unidade `year`, a quantidade é a mesma de `idade_anos_completos`
(`506` = 106 `year`). As duas colunas são nulas quando `idade_status` não é `valid`.
Em `SIM 400` (menor de um ano, sem unidade registrada), `idade_quantidade` é `0` e
`idade_unidade` é `year`, como a fonte registrou.

No SINASC, `idade_anos_completos` interpreta `idademae` e se refere à mãe
(`analytics.age.subject = "mother"`). A regra não disponibiliza sexo materno:
`sexo` é do recém-nascido. A versão 1.0.0 cobre somente o DNRR2023 final auditado,
com domínio 1–65 anos e estados explícitos para valores fora desse suporte.
A regra do SIM 1.1.0 cobre RR/2021 a RR/2024 e SP/2024; a do SIH 1.2.0 cobre RR/2023-01,
SP/2024-01 a SP/2024-05 e SP/2025-01 a SP/2025-02. As regras do SIA 1.0.0 cobrem o BPA-I
de RR/2022-01 e RR/2024-01, a RAAS psicossocial de RR/2024-01 e a atenção domiciliar de
MA/2018-10 (`x-analytics.validated_sources` de cada dicionário).
[Evidência e limites](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-14-extensao-regras/README.md).

No SINAN (`sinan_chagas`, `sinan_hanseniase`, `sinan_tuberculose`),
`idade_anos_completos` interpreta `nu_idade_n`: um dígito de unidade (1 hora, 2 dia, 3 mês, 4 ano) seguido de três de
quantidade, então `4088` são 88 anos. A regra 1.0.0 cobre só os arquivos preliminares
auditados CHAGBR23, HANSBR26 e TUBEBR20.
[Evidência](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-21-w3-idade-sinan/README.md).

Versão analítica solicitada e ausente gera erro. Colisão de nome derivado também.
Campo obrigatório ausente, dataset sem regra e contexto não confirmado retornam
indisponibilidade. Para reproduzir
resultados, fixar snapshot, versão do pacote/artefato, `rule_version` e
`metadata_hash`. Metadata hash deve ser conferido antes de reaplicar um preset.
A versão do pacote também fixa o conjunto de colunas da projeção: `idade_quantidade`
e `idade_unidade`, por exemplo, foram adicionadas nesta versão sem mudança de
`rule_version`.

## Fontes, limitação e auditoria

O registro canônico está em `src/omnisus/data/dicionarios/sources/registry.json`.
Definições e revisões de campo
ficam nos YAMLs. Uma alteração de valor revisado exige atualizar sua evidência e
hash; referências inexistentes geram erro. Campo sem revisão não ganha aprovação
por estar no pacote.

A auditoria do snapshot 5, com SQL e agregados, está em
`evidence/2026-09-14-contrato-analitico/`. A referência SIH `DT_INTER` possui
grafia/formato inconsistente no manual; o contrato registra o conflito e restringe
a interpretação ao recorte conferido. Idades SIH fora do domínio explicitamente
suportado ficam `unsupported`, incluindo `IDADE=999` sob unidade válida.

```bash
uv run --locked --extra dev python scripts/metadados/consultar.py --dataset sim_obitos --field sexo --json
uv run --locked --extra dev python scripts/metadados/consultar.py --dataset sih_aih_reduzida --field dt_inter --arrow
python scripts/metadados/auditar_contrato.py --target ducklake:./data/omnisus-v2.ducklake --snapshot-id 5 --out ./data/auditoria --acceptance-only
```

O script de consulta valida o documento e pode demonstrar transporte Arrow/Parquet
em tabela vazia. `--metadata arquivo.json` valida um exemplo arquivado. O exemplo
histórico `0.1.0-draft` permanece legível; não é fonte de produção. Não há transporte
automático de metadados em toda consulta/exportação: para SQL/CSV guardar o JSON e a
identidade da regra no contrato da consulta.

## Migração e limpeza

Use a interface pública em vez de importar o carregador interno. `Dicionario`
continua interno para ingestão/apresentação; `Dicionario.arrow_schema` foi removido,
pois não descrevia o lake e não tinha consumidor de produção. Helpers Polars de
`transforms.codes` usados apenas por testes também foram removidos.
`x-normalization-hint` substitui a antiga anotação `x-transform: lpad_6` e não executa
normalização. A ingestão física e seu schema Arrow continuam implementados.

A ampliação da aplicabilidade a outros arquivos e a curadoria dos demais campos
permanecem trabalho explícito. O contrato não declara validadas todas as bases.
