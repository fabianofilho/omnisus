# Manutenção e atualização

## Fluxo de trabalho

1. **Identificar o produto.** Registrar categoria, subtipo, tabela física,
   período, situação preliminar/final e arquivo amostrado. Confirmar o dataset
   correspondente; não associar SIA/PA ao YAML de SIA/BI só pela categoria.
2. **Localizar a referência oficial.** Priorizar leiaute/dicionário do órgão
   produtor para a edição do produto. Tabelas auxiliares oficiais sustentam
   domínios. Material secundário serve como pista e deve ser identificado como
   tal, sem receber a autoridade de uma fonte primária.
3. **Congelar a evidência.** Registrar URL, órgão, título, edição, tamanho,
   SHA-256 e data da obtenção. Arquivos podem ficar em cache fora do Git;
   preservar uma cópia recuperável na infraestrutura do projeto quando existir
   um arquivo institucional autorizado. Uma URL com hash detecta alteração,
   mas não garante que a versão antiga continuará disponível.
4. **Extrair afirmações.** Preencher descrição, domínio, formato e relações com
   página/seção. OCR ou busca de nomes gera candidatos para revisão, não
   confirmação semântica.
5. **Fazer a segunda checagem.** Comparar a extração com o documento renderizado
   e conferir o vínculo com o leiaute/período do arquivo real. Registrar cada
   método e sua evidência. Comparar outra referência oficial aplicável quando
   disponível; uma inconsistência não deve ser resolvida por suposição.
6. **Revisar valores e estrutura.** Comparar nomes, tipos e valores observados
   com a definição, guardando o arquivo/hash/recorte. Frequências observadas
   não completam um domínio documental nem provam vigência histórica.
7. **Validar e publicar uma edição.** Validar contratos, referências, hashes,
   intervalos e cobertura; gerar docs/JSON; revisar o diff. Distribuir os
   metadados com a lib somente após passar pelos critérios abaixo.

“Double check” tem dois resultados independentes: **transcrição conferida** e
**aplicabilidade conferida**. No exemplo SIM, o primeiro foi realizado e o
segundo está pendente para os dados de 2023. Uma revisão por outra pessoa pode
ser registrada com identidade própria; não inventar essa etapa quando não houve.

## Quando atualizar

Rever o produto quando surgir documento com hash novo, campo novo/removido,
tipo incompatível, código fora do domínio ou divergência relatada por usuário.
Antes de cada publicação da lib, gerar o relatório de pendências e conferir as
fontes dos produtos alterados. Como política inicial, revisar trimestralmente o
índice de fontes de produtos ativos; o responsável pode ajustar a cadência por
produto. Nenhuma automação periódica foi instalada por estes documentos.

Uma consulta que encontra os mesmos bytes atualiza `last_checked_on` da fonte,
não a data de revisão de cada afirmação. Novo hash cria **nova revisão** da
fonte e abre a revisão dos campos dependentes. Conservar o histórico anterior.

## Critérios de validação para a integração

| Verificação | Resultado esperado |
| --- | --- |
| Contrato | JSON/YAML válido e versão suportada |
| Referências | IDs únicos; todos os IDs de fontes/domínios resolvidos |
| Evidência | Afirmação verificada com fonte oficial, localizador, responsável, método e data |
| Mudança editorial | Hash do valor checado coincide com o valor publicado |
| Identidade | Campo pertence ao produto e à edição corretos |
| Vigência | Sem ambiguidades silenciosas para o mesmo recorte |
| Domínio | Códigos string únicos, sem perda de zeros; desconhecidos preservados |
| Observação | Arquivo e hash identificados; diferenças explicitadas |
| Cobertura | Denominador por tabela/edição; campo ausente não desaparece do relatório |
| Compatibilidade | Decodificadores existentes e ingestão não mudam por edição bibliográfica |
| Distribuição | JSON, Arrow/Parquet e recursos no wheel conferidos |

Separar cobertura de descoberta, de descrição verificada, de códigos verificados
e de aplicabilidade confirmada. Não somar menções textuais com campos validados.
A contagem de ocorrências considera cada tabela; campos homônimos em tabelas
diferentes não são deduplicados globalmente.

## Falhas e conflitos

Quando não houver documentação, manter o campo com significado desconhecido e
registrar onde se procurou e a data. “Não encontrado” não significa “não existe”.
Em conflito, registrar as duas referências, as afirmações concorrentes e o
recorte afetado; impedir interpretação automática nova até resolução. Não
substituir o valor bruto por um palpite ou descartar códigos desconhecidos.

## Regenerar os rótulos

Para os rótulos gerados de CNV do TabWin (`method: cnv-parse`), regenerar com:

```bash
uv run --locked python scripts/metadados/gerar_decode_cnv.py
```

Um campo ligado a um DBF relacionado (TabWin.pdf p. 88) também entra em `campos`,
com o membro `.dbf`, e é escrito com `method: dbf-parse`. `largura` (por dataset, por
campo) guarda só os códigos com esse número de caracteres: `MOTERRO.dbf` tem uma série de 4
caracteres com texto em CP850, que o gerador recusaria pelo byte C1, e os arquivos ER só
publicam a de 6.

Rodar de novo não muda nada quando os vínculos e os membros empacotados não
mudaram; em revisão, usar `--check`, que falha se algum dicionário mudaria. Um
arquivo TabWin republicado entra no registro com um novo id e novos membros —
não sobrescreve o registro existente. `vinculos.json`
(`src/omnisus/data/dicionarios/sources/cnv/vinculos.json`) é o único lugar
onde o CNV de um campo é escolhido; o gerador não decide isso sozinho.

O gerador só escreve campo sem claim `/field/codes`; o mapa anterior que discorda
fica no issue `cnv-difere-do-mapa-anterior`. Uma claim de códigos já existente nunca
é descartada: se o método não é `cnv-parse` (por exemplo, rótulos lidos de uma página),
o gerador para e nomeia dataset, campo, método e evidência; se é `cnv-parse` e o CNV
dá o mesmo mapa, nada muda; se o mapa difere, ele para e lista os códigos que mudaram.
Nos dois casos de parada, a mudança é revista e escrita à mão.
Um `conflicting` de `cnv-parse` cujo mapa anterior não tinha fonte também se resolve à
mão: a claim passa a `verified_in_source` e o issue `cnv-difere-do-mapa-anterior` passa a
`resolved`, guardando o texto do mapa anterior.

Os campos de `sim_obitos_infantis`, `sim_obitos_maternos` e `sim_obitos_externos` são os
de `sim_obitos` (os registros são do DO). Depois de mudar `sim_obitos.yaml`,
regenerar com `uv run --locked python scripts/metadados/gerar_subconjuntos_sim.py`; o teste
`tests/unit/scripts/test_gerar_subconjuntos_sim.py` falha enquanto não se regenera.

Para os campos comuns da Notificação Individual do SINAN (`method: page-read`),
escritos uma vez em `scripts/metadados/sinan_bloco_comum.yaml`, regenerar com:

```bash
uv run --locked python scripts/metadados/gerar_sinan.py
```

Rodar de novo não muda nada quando o bloco comum não mudou; em revisão, usar
`--check`, que falha se algum dicionário SINAN mudaria. Um código só entra em
`x-decode` depois de entrar na lista `codigos` de uma entrada de `fontes`, com a
página do dicionário oficial que o cita ou o CNV empacotado de `TAB_SINANNET` que o
lista; o gerador para se a união dos `codigos` de todas as fontes de um campo não for
exatamente o conjunto de chaves de `x-decode`, ou se um código citado por uma fonte
com `membro` não estiver naquele CNV. Um campo do bloco nunca é também um campo de
`campos` em `sources/cnv/vinculos.json`: cada campo SINAN tem exatamente uma fonte de
decodificação, a página ou o CNV, nunca as duas.

Numa entrada de `agravo.<dataset>`, o campo substitui, só naquele dicionário, a entrada
de `comum` de mesmo nome (é o caso de `sinan_tuberculose.doenca_tra`). Os dois geradores
têm campos disjuntos e podem rodar em qualquer ordem, mas mover um campo de um para o
outro é barrado nos dois sentidos. Do bloco comum para o CNV: se o campo sair do bloco (ou
de `agravo.<dataset>`) e entrar em `campos` de `vinculos.json` sem apagar a claim
`/field/codes` antiga à mão, os dois geradores param —
`gerar_decode_cnv.regenerate` recusa uma claim cujo `method` não é `cnv-parse` ("review
it by hand before the CNV map may replace it"), e `gerar_sinan.generate` recusa uma
claim `page-read` sem entrada no bloco. Do CNV para o bloco comum, também: `gerar_sinan.
generate` recusa escrever um campo do bloco cuja claim atual tem `method: cnv-parse`
("review it by hand before the block may replace it"). Nos dois sentidos, quem move o
campo apaga a claim antiga à mão e confere o campo regenerado.
