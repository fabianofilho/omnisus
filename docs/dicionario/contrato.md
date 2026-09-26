# Contrato por coluna

O [JSON Schema experimental](schemas/column-metadata.schema.json) valida o formato
resolvido mostrado em [SIM / DO / SEXO](exemplos/sim_obitos.sexo.json). É uma unidade
autossuficiente de transporte: o consumidor não precisa procurar a página de
origem em outro YAML para compreender a evidência do campo.

## Informação mínima

| Chave no JSON resolvido | Conteúdo e regra |
| --- | --- |
| `schema_version` | Versão do contrato, `1.0.0`; exemplo histórico `0.1.0-draft` |
| `dataset` | ID, categoria, subtipo e produto de origem |
| `dictionary_version` | Versão editorial da definição |
| `field.id`, `name`, `physical_name` | Identidade estável, nome exposto e nome físico |
| `field.label`, `description` | Nome de apresentação e significado; `null` se desconhecidos |
| `field.physical_type`, `logical_type` | Tipo declarado pela origem e tipo adotado pela lib, sem confundi-los |
| `field.unit`, `format` | Unidade e formato, se documentados |
| `field.codes` | Lista de códigos **strings**, rótulos e classificação de ausência |
| `field.domain` | Natureza do domínio: enum, referência, texto, número, data ou desconhecido; completude |
| `field.constraints`, `relationships`, `derivation` | Restrições, relações e transformações, se conhecidas |
| `claims` | Evidência por afirmação, separada de informações ainda sem revisão |
| `sources` | Fonte resolvida com URL, hash, edição e datas |
| `applicability` | Vigência/condições e estado da confirmação para um recorte de dados |
| `observations` | Referências a arquivos efetivamente examinados, sem generalização estatística |
| `issues` | Divergências e limitações que o consumidor deve poder inspecionar |

Um campo desconhecido continua no inventário com `description: null`,
`codes: []`, domínio `unknown` e alegações `unreviewed`. Lista de códigos vazia
não significa ausência de códigos na fonte. `complete_in_source` significa que
a lista foi conferida naquela edição; não significa cobertura histórica.

## Códigos, domínios e relações

Preservar `"01"` e `"1"` como códigos distintos, a menos que a fonte autorize
normalização. Números codificados não devem perder zeros ao passar por YAML/JSON.
Os classificadores de ausência são `not_missing`, `ignored`, `not_applicable`
ou `unknown`. Um código “ignorado” continua sendo um valor da origem; não é
automaticamente `null` do Arrow/SQL.

Pequenos enums podem ficar no `x-decode` existente. Listas extensas como
municípios, CID e procedimentos devem apontar para um recurso versionado, com
chave e regra temporal. Só compartilhar listas entre bases após confirmar que
significado, códigos e vigência são equivalentes. O exportador deve resolver
domínios pequenos em `codes`; para listas grandes, fornecer `domain.reference`
com recurso, versão e campo-chave.

Relações precisam de tabela/coluna de destino e evidência; semelhança de nomes não
prova chave estrangeira. Campos criados pela lib, como partições, exigem
`derivation` com regra e campos de entrada, em vez de uma atribuição falsa ao
dicionário oficial. A versão inicial do contrato deixa esses três blocos como
objetos extensíveis; especializá-los e testá-los antes de implementar execução
de regras ou joins automáticos.

## Evidência por afirmação

Cada item em `claims` aponta a um valor do documento JSON usando JSON Pointer,
por exemplo `/field/description` ou `/field/codes`. Sua checagem tem status,
data, método, responsável e referências com página (contada a partir de 1) e
localizador. O hash `value_sha256` vincula a revisão ao valor exato: mudar uma
descrição ou código exige nova revisão, sem reaproveitar a aprovação anterior.

O hash usa JSON UTF-8, chaves ordenadas, sem espaços, sem escape ASCII e sem
valores não finitos (`json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)` em Python). É uma convenção deste contrato;
antes de suportar hashes calculados em outras linguagens, formalizar a
canonicalização numérica ou adotar um padrão interoperável com nova versão.

| Status de uma afirmação | Significado |
| --- | --- |
| `unreviewed` | Ausência de checagem semântica |
| `verified_in_source` | Conteúdo conferido no documento e localizador indicados |
| `conflicting` | Evidências incompatíveis; manter alternativas e pendência |
| `not_found` | Não localizado nas fontes efetivamente consultadas |

`method: cnv-parse` marca uma lista de códigos gerada a partir de uma tabela CNV
oficial do TabWin por `scripts/metadados/gerar_decode_cnv.py`. O localizador traz a
linha do DEF que liga o campo ao CNV e o membro do arquivo lido
(`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`). O status
`conflicting` desse método significa que o mapa manual anterior discordava do CNV;
os rótulos anteriores ficam preservados como texto no issue
`cnv-difere-do-mapa-anterior`, não como um segundo mapa.

`method: dbf-parse` marca uma lista gerada pelo mesmo script a partir de um DBF que o DEF
relaciona ao campo (a segunda forma de linha do DEF, TabWin.pdf p. 88): a chave é o campo
de mesmo nome do DBF ou, sem ele, o primeiro campo, e o rótulo é a coluna que o DEF nomeia.
O localizador traz a linha do DEF e o membro lido. É o caso de `co_erro` no ER
(`Motivo_de_Erro.DEF`, `DBF/MOTERRO.dbf`).

`verified_in_source` **não confirma** vigência nos dados. A dimensão separada
`applicability.status` pode ser `unknown`, `confirmed`, `conflicting` ou
`not_applicable`. Aplicar uma interpretação automaticamente a um recorte pede as
afirmações pertinentes verificadas e aplicabilidade confirmada naquele recorte. Um campo pode ter a descrição
conferida e o formato ainda desconhecido.

Datas também têm papéis distintos: `retrieved_on` é obtenção do documento;
`published_on` é a data exata declarada, quando conhecida; `edition` pode guardar
apenas o mês declarado; `checked_at` é conferência semântica; `data_period` é o
período observado. Não preencher um dia fictício quando a fonte só informa mês.

## Extensão de autoria

Nos YAMLs atuais, conservar `description`, `type`, `x-decode`, `x-format` e
demais propriedades usadas pela lib. Acrescentar `x-metadata` com identidade,
tipo físico, domínio, procedência e aplicabilidade. O resolvedor transforma essa autoria no contrato resolvido:

| Autoria | Exportação |
| --- | --- |
| `schema.fields[].name` | `field.name` |
| `label`, `description`, `type` | `field.label`, `description`, `logical_type` |
| `x-decode` + classificação editorial dos códigos | `field.codes` |
| `x-metadata.physical_name` e `physical_type` | `field.physical_name`, `physical_type` |
| `x-metadata.claims` + IDs em `sources/` | `claims` + `sources` resolvidos |
| `x-metadata.applicability` | `applicability` |

O resolvedor `describe_dataset` implementa esta separação. Nunca preencher evidência por padrão
para todos os `x-decode` antigos. A migração inicial deve marcá-los como
`unreviewed`, preservando as decodificações existentes até uma revisão específica.

## Double check do exemplo real

A página 2 de **Estrutura do SIM**, edição declarada 07/2025, descreve `SEXO`
como caractere de tamanho 1 e apresenta os sete códigos do exemplo. A extração
de texto e a página renderizada foram conferidas em 10/09/2026; o SHA-256
identifica os bytes consultados. A descrição foi parafraseada e os códigos
mantêm a correspondência documentada. A revisão foi feita por Codex; não é
uma assinatura de revisão humana independente.

Havia uma divergência relevante para a integração: o YAML da biblioteca usava
`type: integer`, embora o documento também liste códigos alfabéticos. O exemplo histórico
mostra separadamente esse tipo lógico legado e o tipo físico documental. A versão
atual corrige o tipo lógico de `sexo` para string e mantém os códigos. A
aplicabilidade do manual de 2025 ao arquivo amostrado `DORR2023.dbc` permanece
`unknown`; o exemplo não autoriza uma conversão de tipo ou recodificação desses
dados. Veja a URL oficial e o hash no próprio [JSON](exemplos/sim_obitos.sexo.json).
