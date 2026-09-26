# Extensão das regras analíticas — 2026-09-14

## Resultado

| Arquivo final auditado integralmente | Registros | Idade interpretável | Ausente | Ignorada |
| --- | ---: | ---: | ---: | ---: |
| SINASC DNRR2023.dbc | 13.105 | 13.104 | 1 | 0 |
| SIH RDRR2301.dbc | 4.734 | 4.734 | 0 | 0 |
| SIM DORR2021.dbc | 4.306 | 4.299 | 0 | 7 |

Não há idade inválida ou não suportada nesses três arquivos. O novo escopo SIH
confirma também sexo e as datas NASC/DT_INTER/DT_SAIDA; GESTOR_DT está ausente em
todas as linhas. SIM tem dois sexos ignorados; os demais valores são suportados.
Os estados de cada data, os schemas físicos, os hashes e as expressões SQL estão
em `acceptance.json`. Os totais de todos os estados reconciliam com os registros
lidos. O arquivo de origem e o Parquet temporário permanecem byte a byte iguais
antes/depois das consultas. Nenhum lake foi alterado.

A leitura validou o arquivo DBC completo e a contagem do DBF, não o Parquet de
200 linhas da antiga amostra. `manifest.json` identifica os bytes de cada origem.
O arquivo SIM foi baixado do servidor oficial nesta auditoria; os outros dois
foram relidos do acervo de 10/09 e seus hashes reconferidos.

## SINASC: significado e limites

- `Estrutura_SINASC_para_CD.pdf`, p. 1, identifica IDADEMAE como C(02), idade da mãe
  em anos. Hash: `24e0d4388ea1d5fbe58a328136f1cb464e461985d3ed737210e0ecda5000cb08`.
- Manual de instruções da DN, 2011, p. 16, campo 19, confirma anos completos no
  momento do parto. Hash: `b88f538902ee` (prefixo; hash integral em `sources.json`).
  A página foi conferida visualmente, assim como a página da estrutura.
- `NASC_NOV_TAB.zip`, hash
  `ff0124f6aecf82c2f198cf4c7fd1e40fa40cc2a608f15331708d5751a88c0f05`, associa
  IDADEMAE a IDADEMAE.CNV e IDADET.CNV em NASCIDO.def. Os membros consultados e seus
  hashes estão em `tab-members.json`; as duas tabelas foram preservadas integralmente.

O decodificador `kind: years` exige declaração de unidade/domínio no contrato.
Não deduz anos pelo nome da coluna ou por seu tipo inteiro. A regra SINASC aceita
1–65, o domínio comum às duas tabelas consultadas. Isso é um limite de suporte
analítico, não um limite biológico nem uma definição universal de qualidade.

Ambas as tabelas colocam 00 e 99 no grupo de tabulação ignorado; esses valores
produzem `ignored`. Não se afirma que sejam sentinelas universais de coleta.
Valores 66–70 divergem: IDADET os agrupa em 66 e mais, IDADEMAE os deixa no grupo
ignorado. Eles permanecem `unsupported`, assim como 71–98 e quantidades fora do
intervalo. Não copiamos a faixa genérica 00–99 de ignorados sobre idades conhecidas.
Vazio/nulo produz `missing`; texto malformado produz `invalid`.

`idade_anos_completos` refere-se à **mãe** neste produto; o contrato explicita
`age.subject: mother`. `SEXO` descreve o recém-nascido. Esta extensão não cria uma
regra de sexo materno nem permite tratar idade materna/sexo do bebê como pirâmide
etária da mesma população. `display_row` fornece rótulos para apresentação;
`analytical_projection` exige a identidade auditada para disponibilizar SQL.

Das 13.104 idades com datas comparáveis, 13.101 coincidem com os anos completos
entre nascimento da mãe e parto; **três divergem**. As divergências ficam nos
agregados e não levam a recalcular/substituir a idade publicada.

### Diretório legado e procedência

DNRR2023 foi publicado em `SINASC/1996_/Dados/DNRES`. O portal oficial o identificou
como final; a resposta original está em `sinasc-portal.json`, com hash no manifesto.
O resolvedor atual `SourceContext.from_publication()` não reconhece esse diretório
legado e pode devolver `release=None`. Não preencher isso por suposição: construir
`SourceContext` com a modalidade final apenas quando comprovada pelo manifesto e
pela evidência do portal, como faz o comando de auditoria. A tentativa de obter o
mesmo arquivo em `SINASC/NOV/DNRES` não o encontrou. Esta alteração não muda o
catálogo de downloads nem presume que diretórios sejam intercambiáveis.

## SIM e SIH: expansão limitada e pendências

SIM/SIH passam à versão de regra 1.1.0, adicionando, respectivamente, RR/2021 e
RR/2023-01 com os hashes integrais do manifesto. Não se alteraram as fórmulas,
os códigos de sexo ou os formatos de data previamente confirmados. Aplicabilidade
continua por UF, ano, mês quando aplicável, modalidade e hash exatos. Combinar
um arquivo confirmado com outro desconhecido mantém o campo indisponível.

Os 4.287 registros SIM com datas comparáveis concordam com a idade publicada;
os 4.734 SIH também concordam na internação. O arquivo SIH contém duas idades
centenárias, unidades 5/quantidades 0 e 1. Isso complementa, sem substituir, a
[evidência documental anterior](../contrato-analitico/regras.md).

Continuam sem interpretação exata os códigos SIH fora do domínio documentado,
incluindo unidade 5/quantidades 31–99 e o composto 312, cuja classificação diverge
entre tabelas. `IDADE=999` não vira uma sentinela global. As fixtures verificam
que esses valores continuam sem idade calculada. Outros arquivos, anos, UFs e
releases exigem novos aceites; não foi estabelecida vigência universal.

## Reprodução

Com os arquivos de origem nos caminhos do manifesto, executar na raiz:

```bash
OMNISUS_DBC_BACKEND=python OMNISUS_DBF_BACKEND=python .venv/bin/python \
  scripts/metadados/auditar_arquivos.py \
  --manifest evidence/2026-09-14-extensao-regras/manifest.json \
  --out /tmp/aceite-regras.json
```

O backend Python foi escolhido explicitamente porque a extensão nativa instalada
no ambiente usa uma API incompatível; não houve fallback silencioso. O comando
não consulta rede nem adiciona identidades ao contrato. `--candidate` serve para
avaliar a regra antes da confirmação de um novo arquivo, e é marcado no resultado;
essa avaliação isolada não prova vigência documental. `candidate.json` conserva
a execução anterior à ampliação SIM/SIH. `acceptance.json` usa a projeção pública
após a revisão e a inclusão das identidades.

O aceite dos 2.007.691 registros anteriores foi repetido no snapshot 5 em
`snapshot5/acceptance.json`, usando o comando existente `auditar_contrato.py
--acceptance-only`. As faixas etárias, os estados, os schemas e as contagens
anteriores foram preservados. Os hashes de metadados mudam com esta extensão,
portanto consumidores devem atualizar conscientemente suas referências fixadas.

[Testes executados e limitação da extensão nativa](validation.md).
