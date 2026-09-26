# Evidência das regras analíticas — 2026-09-14

Auditoria exclusivamente por `LakeReader(snapshot_id=5)`. `audit.json` registra
revisão, hash do comando, dicionários, schemas, publicações e agregados; `queries.sql`
contém todas as consultas executadas pelo comando. Não há exportação de registros
individuais. O histórico dos snapshots permaneceu idêntico antes/depois. Os números
são a reprodução da hipótese de referência do plano; não conferem vigência universal
às regras e não substituem a validação da projeção pública.

```bash
python scripts/metadados/auditar_contrato.py \
  --target ducklake:./data/omnisus-v2.ducklake \
  --snapshot-id 5 --out evidence/2026-09-14-contrato-analitico
```

## Fontes conferidas

| Fonte | Localizador | SHA-256 |
|---|---|---|
| SIM, estrutura anterior, Mortalidade 2006 | p. 1, IDADE/SEXO | `13cabba0b9a19d32b836f57762b9bc571e573c4a87737440c8052b737072d890` |
| SIM, DOM (+ investigação materna) | p. 2–3, IDADE; p. 3 SEXO | `fb396a277981686f440e7a17ff2612a4c9f58fdb9ac70a10056334d9be757364` |
| SIM, Estrutura 07/2025 | p. 2, IDADE/SEXO | `b4195ac8e0f825a794cb487df93db41601a2f430a708172f494f1251b55eeeb1` |
| SIH, Informe processamento 2016-03 | p. 1–4, layout RD | `1e89d5f2cc41420385d7e30ba5541a387912ab3a0efb167d39def74502076220` |
| SIH, TAB_SIH.zip, entradas 2026-08-17 | RD2008.DEF; CNV/IDADEDET.CNV; CNV/IDADEBAS.CNV; CNV/SEXO.CNV | `714ed980d483c038dc8245be5c40c39062ebfa55a7f6288ab4a87587ef199874` |

URLs, tamanhos e datas das fontes novas: `registry-additions.json`. Fontes antigas:
registro empacotado/documental. Hash e datas de cada membro do ZIP:
`tab-sih-sources.json`. Os CNVs consultados foram preservados byte a byte; o DEF tem
um extrato das linhas que vinculam os campos às tabelas. Não é necessário executar
arquivos do pacote para ler essas definições. As páginas SIM DOM/2025 foram também
conferidas visualmente para excluir um erro de extração de texto.

## SIM: unidades, sentinelas e divergências

O documento DOM p. 3 define unidades 0 = menos de uma hora, quantidade 01–59;
1 = horas 01–23; 2 = dias 01–29; 3 = meses 01–11; 4 = anos 00–99;
5 = anos acima de 100, quantidade 00–99. O documento anterior p. 1 dá exemplos
que resolvem a unidade 0 e o deslocamento: `020` representa 20 minutos;
`505`, 105 anos. Também especifica `000` como idade ignorada e `400` como menor
de um ano sem informação de horas, dias ou meses. Logo `400` tem zero anos
completos, com precisão de intervalo, sem alegar zero anos exatos.

A edição 07/2025 p. 2 escreve 1 = minuto e 2 = hora, omite o identificador de dias
e preserva 3 = mês. A leitura visual confirma que não é artefato do extrator.
Ela não substitui automaticamente o mapa publicado nos documentos anteriores.
A mesma página descreve 9 = ignorado. `9xx` deve ser distinguido de unidade
inesperada 6–8. O snapshot contém apenas `999` nessa família; a semântica dos demais
`9xx` não foi testada empiricamente. Quantidade `99` não é uma sentinela global:
`499` é 99 anos e o domínio documental de unidade 5 inclui `599`.

Exceções de domínio: há **9 códigos `100` e 82 `200`**. São quantidades zero em
unidades cujo documento começa em 01. Não há valores superiores aos máximos
publicados nem `300`. A hipótese histórica atribui zero anos completos a esses
91 casos, mas a auditoria não transforma esse comportamento em autoridade
universal. Uma regra que exija estritamente os mínimos documentais terá 7.268 em
0–4 e 442 desconhecidos, em vez de 7.359 e 351. A regra implementada aceita esses zeros como zero anos completos
somente nos escopos confirmados e mantém a divergência documental nas notas da
regra; portanto conserva os números da hipótese de referência. Não é uma nova
definição documental universal. `000` e `400` não ocorrem no recorte e exigem fixtures.

## SIH: a unidade 5 e os códigos oficiais de tabulação

`RD2008.DEF` vincula a idade a `COD_IDADE` e às tabelas de códigos compostos de três
posições. `IDADEDET.CNV` associa `200` a zero dias; `201`–`229` a dias; `230` junto
de `301` a um mês; `302`–`310` a meses; `311` e `312` a onze meses; `401`–`499`
a 1–99 anos; `500`–`530` a 100–130 anos. Assim o deslocamento **100 + quantidade**
é documentalmente verificável, não inferido apenas das datas. A tabela detalhada
não confirma idade exata para `531`–`599`; a tabela básica só os agrupa em 50 anos
ou mais. Essa lacuna não autoriza inventar uma idade exata.

`IDADEDET.CNV` chama os códigos compostos **`000` e `999` de idade inválida**;
`IDADEBAS.CNV` agrupa 000–099, 312–400 e 600–999 em ignorados. O segundo agrupamento
mistura falta de detalhe e valores inválidos; não é uma autoridade para chamá-los
todos de sentinelas de coleta. `312` inclusive diverge entre as tabelas detalhada
e básica. Para projeções exatas, preferir classificação conservadora e indicar
que a regra de tabulação é específica. Unidades 0 e 9 sem código composto
explicitamente reconhecido permanecem sem interpretação exata.

### Decisão para o valor bruto `IDADE = 999`

| COD_IDADE | Decisão documental |
|---|---|
| 0 | Não equivale ao composto `000`; fora da quantidade de duas posições, sem regra confirmada |
| 2 | Fora do domínio documentado em dias; não tratar como ignorado |
| 3 | Fora do domínio documentado em meses; não tratar como ignorado |
| 4 | Fora do domínio documentado em anos; não tratar como ignorado |
| 5 | Fora do domínio do deslocamento confirmado; não produzir 1.099 anos |
| 9 | Não equivale ao composto `999`, que corresponde a unidade 9 e quantidade 99; sem regra confirmada |

O snapshot não contém `IDADE=999`. Unidades observadas: dias 0–30, meses 1–11,
anos 1–99, centenários 0–27. Não há evidência para uma sentinela global do campo.

Comparação com nascimento/internação: 703 de 722 registros com unidade 5 têm
idade calculada idêntica a `100 + IDADE`; a comparação na saída concorda em 710.
Os desacordos permanecem no relatório, sem reescrever idade pelo nascimento.
Para unidade 4, 1.553.845 de 1.570.955 concordam na internação. Consistência
empírica não prova que o marco temporal seja sempre internação ou saída.

## Sexo

SIM anterior: 0 ignorado, 1 masculino, 2 feminino. DOM: M/F/I.
SIM 2025 explicita M ou 1 masculino, F ou 2 feminino, I/0/9 ignorado.
No recorte: 192.100 masculinos, 169.054 femininos e 74 ignorados.

SIH `SEXO.CNV`: 1 masculino, **2 e 3 feminino**. Uma faixa 0–9 serve ao grupo
ignorado, sobreposta aos códigos mais específicos. O mapa deve distinguir
valores definidos de desconhecidos e não copiar cegamente essa faixa como
sentinela de origem. No recorte existem 732.495 códigos 1 e 913.968 códigos 3.
Nenhuma dessas fontes estabelece uma categoria não binária para o campo; códigos
não documentados não recebem um significado presumido. Letras ou valores fora
do mapa SIH não herdam automaticamente a semântica do SIM.

## Datas

Formato SIM `ddmmaaaa` confirmado em DTOBITO (2025 p.1) e nas datas do DOM.
Formato SIH `aaaammdd` em NASC (2016 p.1), DT_SAIDA (p.2) e GESTOR_DT (p.3).
Na data de internação, o informe grafa DI_INTER e `aaammdd` (três letras a),
embora declare char(8). O nome `dt_inter` e o formato `aaaammdd` são a interpretação
consistente com o recorte, com essa inconsistência documental explícita.
`date-locators.json` localiza os 15 campos de data e mantém esta qualificação.
DTRECORIGA tem formato documentado, mas o PDF não informa seu comprimento físico.
No SIM há 562 nascimentos ausentes e nenhum inválido entre os demais; todos os
361.228 óbitos têm data válida. No SIH, nascimento/internação/saída têm 1.646.463
datas válidas cada; `gestor_dt` está ausente em todas as linhas. Não interpretar
`00000000` como data nem tolerar comprimento inadequado. Os contadores do comando
exigem oito dígitos e parse de calendário válido; valores brutos são preservados.

## Inventário e procedência

| Campo ausente | Classificação e evidência |
|---|---|
| `numerodo` | Histórico: estrutura 2006 p.1 e DOM p.1; ausente nesta disseminação. A causa da ausência não está documentada pelas fontes examinadas |
| `opor_do` | Campo criado no tratamento, SIM2025 p.6; não disseminado neste recorte; vigência por ano pendente |
| `ufinform` | Pendência sem evidência nas fontes examinadas; não inventar significado/vigência |
| `tp_altera` | Variável de crítica/tratamento, SIM2025 p.9; não disseminada neste recorte |
| `cb_alt` | Variável de sistema, SIM2025 p.9; não disseminada neste recorte; significado adicional desconhecido |
| `covid_clas` | Pendência sem evidência nas fontes examinadas |
| `mat_clas` | Pendência sem evidência nas fontes examinadas |
| `_fonte_arquivo`, `_data_extracao`, `_hash_arquivo`, `_sistema`, `_grupo` | Metadados legados da biblioteca, ausentes fisicamente nas duas tabelas; não são campos oficiais do DBF |

Campos extras: `_source_release` vem do staging da biblioteca (modalidade final/prelim),
não é uma coluna do documento de origem. SIH `diagsec1`–`diagsec9` são diagnósticos
secundários e `tpdisec1`–`tpdisec9` os respectivos tipos, explicitamente no informe
2016 p.4. O documento não enumera os valores de `tpdisec`; seus domínios seguem
como desconhecidos. `diag_secun` foi zerado a partir de 201501 (p.2); isso não
justifica apagar o campo histórico. Tipos observados de partições são refinamentos
inteiros (`USMALLINT`, `UTINYINT`), diferentes de coerção indevida de códigos.

`reader.publications()` fornece `publication_id`, `source_sha256`, `source_uri`,
`scope`, `release`, `active`, `managed` e versão do parser. Consulte pelo mesmo
snapshot usado na análise, selecione dataset/escopos/ativos e confira cobertura.
O manifesto registra hash do arquivo de origem por publicação; `_hash_arquivo`
ausente na linha não significa perda de procedência. Não há promessa de linhagem
unívoca por registro se houver publicações sobrepostas no mesmo escopo.

## Aplicabilidade e pendências

O recorte SIM é RR/2022–2024 e SP/2024, final; SIH SP/2024–2025, final. Os hashes
concretos das publicações em `audit.json` são a identidade desse aceite. Documentos
2006, sem data (DOM), 2016 e 2025/2026 não provam retrospectivamente todos os anos,
UFs, releases e layouts. Disponibilidade fora dos escopos confirmados exige nova
evidência, não um fallback amplo. Em especial continuam pendentes os significados
de UFINFORM/COVID_CLAS/MAT_CLAS, os tipos de diagnóstico secundário, a vigência
universal das regras e as quantidades zero SIM fora dos mínimos documentais.

Tentativas auxiliares: busca localizou o manual de auditoria MS/2004 e um estudo
IPEA/2019, mas downloads atuais responderam reset/404/login; não foram promovidos
a fonte canônica nem se atribuiu hash PDF ao HTML recebido. As regras SIH acima
são sustentadas pelo pacote oficial efetivamente obtido.

## Aceite da interface pública

`acceptance.json` e `acceptance.sql` são uma segunda execução, por
`analytical_projection()` e `SourceContext.from_publication()`, sem substituir
`audit.json`. Reproduzir com o mesmo comando acrescido de `--acceptance-only`.
Foram utilizados apenas os hashes de publicações ativas recuperados do snapshot.
Cada dataset registra a versão da regra, hash do contrato, expressões exatas,
schema e total antes/depois, faixas, sexo e todos os estados de datas derivados.

Todas as faixas coincidem com `aceitacao.md`: SIM 361.228 e SIH 1.646.463. SIM
contabiliza 351 idades ignoradas e 74 sexos ignorados; SIH inclui as 913.968
linhas femininas e nenhuma idade desconhecida. Cada contador de estado reconcilia
com o total. Schema, total bruto e histórico de snapshots permaneceram idênticos.
O aceite representa o estado local em desenvolvimento identificado no relatório;
qualquer mudança posterior da regra ou do hash exige uma nova execução de aceite.
