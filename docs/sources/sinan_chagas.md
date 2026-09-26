# SINAN · doença de Chagas aguda (`sinan_chagas`)

## Em uma frase

Notificações de doença de Chagas aguda do Sistema de Informação de Agravos de
Notificação (SINAN), que o DATASUS publica em um arquivo nacional por ano, ora no
diretório final, ora no preliminar.

## O que um registro representa

- O dicionário do agravo diz que o número de notificação e os campos de 1 a 30
  correspondem aos mesmos campos da ficha de notificação, exceto a data de diagnóstico,
  e descreve os campos da investigação a partir do campo 31, data da investigação
  (Dicionário Chagas v5, p. 1).
- `tp_not` é o tipo de notificação: 1 = negativa, 2 = individual, 3 = surto,
  4 = agregado (Dicionário Notificação Individual v5, p. 1).
- `id_agravo` é o código CID-10 do agravo notificado, e ao exportar retira-se o ponto
  (Dicionário Notificação Individual v5, p. 1); a biblioteca espera `B571`
  (`src/omnisus/data/dicionarios/sinan_chagas.yaml`, `x-identity`).
- `classi_fin` é a classificação final, conclusão da investigação: 1 = confirmado,
  2 = descartado; é obrigatória quando a data de encerramento está preenchida
  (Dicionário Chagas v5, p. 10).
- `criterio` é o critério de confirmação ou descarte: 1 = laboratório,
  2 = clínico-epidemiológico, 3 = clínico (Dicionário Chagas v5, p. 10).
- `evolucao` é a evolução do caso: 1 = vivo, 2 = óbito por Chagas, 3 = óbito por outras
  causas, 9 = ignorado (Dicionário Chagas v5, p. 10).
- `nduplic_n` marca duplicidades: 0 ou branco = não identificado, 1 = não é duplicidade
  (não listar), 2 = duplicidade (não contar)
  (Dicionário Notificação Individual v5, p. 8).
- `nu_idade_n` é a idade na notificação: o primeiro dígito é a unidade (1 hora, 2 dia,
  3 mês, 4 ano) e os três seguintes a quantidade; `4088` = 88 anos (Dicionário
  Notificação Individual v5, pp. 3–4). `analytical_projection` só a interpreta para o
  CHAGBR23 preliminar auditado (`x-analytics.validated_sources`).
- O número da notificação (`NU_NOTIFIC`) é o campo chave do registro no sistema
  (Dicionário Notificação Individual v5, p. 1), mas não está entre os 108 campos
  observados no arquivo `CHAGBR23.dbc`
  (`src/omnisus/data/dicionarios/sinan_chagas.yaml`, `x-evidence` e `schema.fields`).
- O dicionário da biblioteca é um inventário físico daquele arquivo, sem auditoria
  semântica dos campos, exceto `nu_idade_n` e as categorias de `tp_not`, `cs_sexo`,
  `cs_gestant`, `cs_raca`, `cs_escol_n`, `nduplic_n`, `tpautocto`, `doenca_tra`,
  `classi_fin`, `criterio` e `evolucao`, decodificadas a partir das páginas citadas
  (Dicionário Notificação Individual v5, pp. 1, 4, 5, 8, 9, 13; Dicionário Chagas v5,
  p. 10; Anexo I da Notificação Individual v5, p. 18, para `classi_fin` 8). Branco fica
  indecodificado, salvo quando a página o nomeia. Onde o código `9` aparece,
  `cs_gestant`, `cs_raca`, `cs_escol_n` e `doenca_tra` trazem 9 = "Ignorado", distinto
  de branco, e `evolucao` traz 9 = "ignorado" (minúsculo, como grafado no Dicionário
  Chagas v5, p. 10); `tp_not`, `cs_sexo`, `nduplic_n`, `tpautocto`, `classi_fin` e
  `criterio` não têm o código 9. Os códigos armazenados não mudam
  (`src/omnisus/data/dicionarios/sinan_chagas.yaml`, `x-evidence.semantic_status`).
- A importação grava as colunas do arquivo com nomes em minúsculas e acrescenta
  `_source_ano` e `_source_release`; como o arquivo é nacional, não acrescenta `ano`,
  `uf` nem `mes` (`src/omnisus/sources/datasus_ftp/_runner.py`, `ingest_raw`;
  `src/omnisus/sources/datasus_ftp/staging.py`, `dbc_bytes_to_parquet`).

## Datas e geografia

- `dt_notific` é a data de preenchimento da ficha de notificação
  (Dicionário Notificação Individual v5, p. 2).
- `nu_ano` é o ano da notificação, variável interna preenchida pelo sistema a partir da
  data de notificação (Dicionário Notificação Individual v5, p. 2).
- `dt_sin_pri` é a data dos primeiros sintomas no agravo agudo
  (Dicionário Notificação Individual v5, p. 3).
- `dt_invest` é a data da investigação, da primeira visita ao paciente, e deve ser igual
  ou posterior à data da notificação (Dicionário Chagas v5, p. 1).
- `dt_encerra` é a data do encerramento do caso, igual ou posterior à data da
  investigação (Dicionário Chagas v5, p. 16).
- `dt_digita` é a data da primeira inclusão da notificação no sistema e não é
  atualizada se os dados mudarem (Dicionário Notificação Individual v5, p. 14).
- `_source_ano` é o ano do arquivo (`CHAGBR23.dbc` → 2023), não uma data dos registros
  (`src/omnisus/sources/datasus_ftp/_runner.py`, `ingest_raw`).
- A biblioteca rejeita o arquivo inteiro quando o valor mais frequente de `nu_ano` não é
  o ano do arquivo, e mantém no lake os registros isolados de outro ano
  (`src/omnisus/sources/datasus_ftp/identity.py`, docstring do módulo e
  `validate_identity`).
- Todos os arquivos SINAN do FTP são nacionais e anuais, `<PREFIXO>BR<AA>.dbc`, sem
  arquivo por UF ([relatório de 2026-09-12](https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-12-sinan-e-dispensacao.md),
  §1.1).
- `sg_uf_not` é a UF da unidade de saúde que notificou, e `id_municip` o município dessa
  unidade (Dicionário Notificação Individual v5, p. 2).
- `sg_uf` é a UF de residência do paciente na notificação, e `id_mn_resi` o município de
  residência, com 6 caracteres (Dicionário Notificação Individual v5, p. 6).
- `coufinf`, `copaisinf` e `comuninf` são a UF, o país e o município prováveis da
  infecção (Dicionário Chagas v5, p. 13–14).
- O código de município da população do IBGE tem 7 dígitos
  (`src/omnisus/data/dicionarios/ibge_populacao.yaml`, `codigo_ibge`).

## Cobertura e modalidade

Um arquivo nacional por ano, de 2000 em diante, no diretório final
`/dissemin/publicos/SINAN/DADOS/FINAIS` ou no preliminar
`/dissemin/publicos/SINAN/DADOS/PRELIM`; veja o [catálogo de datasets](../datasets.md).
Em 2026-09-11, 2000–2022 estavam em `FINAIS` e 2023–2025 em `PRELIM`, e nenhum ano
estava nos dois (relatório de 2026-09-12, §1.1 e §1.2). A importação não aceita filtro
de UF nem de mês.

Para saber em qual diretório cada ano está hoje:

```python
import omnisus as odb

publicados = odb.available_releases("sinan_chagas", refresh=True)
```

## Armadilhas

- Uma notificação não é um caso confirmado: a classificação final separa confirmado
  (1) de descartado (2) (Dicionário Chagas v5, p. 10). Filtre `classi_fin` antes de
  contar casos.
- O Anexo I do dicionário da notificação lista para Chagas também 8 = inconclusivo
  (Dicionário Notificação Individual v5, p. 18), código que o dicionário do agravo não
  traz (Dicionário Chagas v5, p. 10), e o anexo começa com a nota "Falta concluir
  revisão" (Dicionário Notificação Individual v5, p. 17).
- Nem toda notificação é individual: `tp_not` tem negativa, surto e agregado
  (Dicionário Notificação Individual v5, p. 1).
- Duplicidades marcadas com 2 em `nduplic_n` não devem ser computadas na incidência
  (Dicionário Notificação Individual v5, p. 8–9).
- Quando a classificação final é descartado, o sistema apaga os campos de local provável
  de infecção e de doença relacionada ao trabalho (Dicionário Chagas v5, p. 11–16).
- `sg_uf_not` e `id_municip` descrevem onde se notificou, e `sg_uf` e `id_mn_resi` onde
  o paciente morava (Dicionário Notificação Individual v5, p. 2 e p. 6); contagens por
  um e por outro respondem a perguntas diferentes, como mostram as consultas
  `notificacoes_por_uf_de_notificacao` e `notificacoes_por_uf_de_residencia` do
  notebook (`notebooks/sinan.py`).
- `historia` tem o rótulo "História de uso de sangue ou hemoderivados nos últimos 120
  dias" e a descrição "nos últimos 90 dias" (Dicionário Chagas v5, p. 3).
- Um ano preliminar muda: a nota técnica do TABNET de Chagas diz que a base preliminar é
  exportada no segundo semestre do ano seguinte e considerada fechada após dois anos, e
  lista UFs de 2024 cuja classificação final foi ajustada pela área técnica nacional
  (relatório de 2026-09-12, §1.2, item 3).
- Os dois diretórios são reescritos: a data de modificação no FTP prova reescrita, não
  mudança de conteúdo, e só `CHAGBR23` tem hash gravado desde 2026-09-10
  (relatório de 2026-09-12, §1.2, item 4).
- Doença de Chagas crônica não está nesta base: seus arquivos (`DCCRBR*.dbc`) ficam em
  `/dissemin/publicos/ESUSNOTIFICA` (relatório de 2026-09-12, §1.1).
- `CHAGBR00` não tem a coluna `ID_AGRAVO` (relatório de 2026-09-12, §3.3); nesse caso a
  biblioteca só confere o ano (`src/omnisus/sources/datasus_ftp/identity.py`,
  `validate_identity`).
- Os códigos ficam no lake como publicados: a decodificação de categorias (11 campos,
  acima) é aplicada pela biblioteca na leitura, não regrava os dados armazenados
  (`src/omnisus/data/dicionarios/sinan_chagas.yaml`,
  `x-evidence.semantic_status`).

### Em aberto

- Como identificar pessoas únicas: o número da notificação é o campo chave no sistema
  (Dicionário Notificação Individual v5, p. 1), mas não está no arquivo observado
  (`sinan_chagas.yaml`). Não trate linhas como pessoas.
- Se `classi_fin` traz 8 = inconclusivo ou valores vazios nos seus dados: os dois
  documentos divergem (p. 10 do agravo, p. 18 da notificação). Olhe a distribuição com a
  consulta `classificacao_e_evolucao` do notebook.
- Se o dicionário v5, revisado em julho de 2010 (rodapé das páginas), vale para os
  arquivos atuais: o inventário da biblioteca vem de `CHAGBR23.dbc`, e os campos não
  foram cruzados com o PDF (`sinan_chagas.yaml`, `x-evidence`; relatório de 2026-09-12,
  §1.5).
- Como a passagem de preliminar para final acontece: pela ausência de sobreposição, o
  provável é que o arquivo saia de `PRELIM` quando entra em `FINAIS`, mas isso é
  inferência, não observação (relatório de 2026-09-12, §1.2, item 5).

## Como usar

```python
import omnisus as odb

alvo = "ducklake:./data/raw/omnisus.ducklake"  # o padrão de Lake.local() e load()
print(odb.available_releases("sinan_chagas", refresh=True))  # ano -> final ou prelim
escopos = odb.available("sinan_chagas", years=[2022])
relatorio = odb.import_dataset(
    "sinan_chagas", scopes=escopos, target=alvo, policy="skip_same", run_id="chagas-2022"
)
with odb.LakeReader(alvo) as leitor:
    print(leitor.connect().sql("SELECT _source_ano, _source_release, count(*) FROM lake.sinan_chagas GROUP BY ALL").pl())
```

Passo a passo com Chagas e hanseníase, análise e procedência:
[notebooks/sinan.py](https://github.com/raphaelfh/omnisus/blob/main/notebooks/sinan.py)
[![Open in molab](https://molab.marimo.io/molab-shield.svg)](https://molab.marimo.io/github/raphaelfh/omnisus/blob/main/notebooks/sinan.py).

## Fontes

- Sistema de Informação de Agravos de Notificação, Dicionário de Dados – SINAN NET –
  Versão 5.0, agravo doença de Chagas (`DIC_DADOS_Chagas_v5.pdf`), Ministério da Saúde /
  SVS / GT-SINAN, revisado em julho de 2010:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/Chagas/DIC_DADOS_Chagas_v5.pdf>
  — consultado em 2026-09-10; SHA-256
  `16c598f86fbfedd8040ebb34ad03c3351ff25c9bf1558354fe86ccb8b4bf8bd1`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Dicionário de Dados – SINAN NET – Versão 5.0, Notificação Individual
  (`DIC_DADOS_Notificacao_Individual_v5.pdf`), Ministério da Saúde / SVS / GT-SINAN,
  revisado em julho de 2010:
  <https://portalsinan.saude.gov.br/images/documentos/Agravos/NINDIV/DIC_DADOS_Notificacao_Individual_v5.pdf>
  — consultado em 2026-09-10; SHA-256
  `b3e0561c7a2d0a83d717286e07d01ca75b0d4499a38d3b3ba2b602a4fc983004`, conferido de novo
  em 2026-09-13. Registro: `src/omnisus/data/dicionarios/sources/registry.json`.
- Relatório "SINAN além de Chagas e fontes públicas de dispensação", revisado em
  2026-09-12, §1.1–1.5 e §3.3:
  <https://github.com/raphaelfh/omnisus/blob/main/evidence/2026-09-12-sinan-e-dispensacao.md>.
- Página oficial do agravo no Portal SINAN:
  <https://www.portalsinan.saude.gov.br/doenca-de-chagas-aguda> — fonte da página
  anterior; não relida nesta revisão.
- Catálogo gerado do registro da biblioteca: [Datasets](../datasets.md).

## Detalhes técnicos

### Linha de comando

```bash
omnisus inventory sinan_chagas
omnisus import sinan_chagas --years 2023 --plan inventory --policy skip_same
```

O recorte nacional é `ScopeKey(uf=None, ano=2023)`; filtros de UF ou mês na aquisição
são rejeitados. Filtre a geografia na consulta, por `sg_uf_not` ou pelos campos de
residência, conforme a pergunta.

### Final e preliminar

Cada arquivo é buscado no diretório em que foi listado, e a linha registra a modalidade
em `_source_release` (`final` ou `prelim`), ao lado de `_source_ano`. Anos finais e
preliminares convivem na mesma tabela; a coluna diz qual é qual, e
`publications()` repete a modalidade por publicação. A biblioteca não converte uma
modalidade na outra em silêncio. Quando o DATASUS republica um ano preliminar como final:

```python
with odb.LakeReader(alvo) as leitor:
    movidos = odb.outdated("sinan_chagas", lake=leitor)
odb.import_dataset("sinan_chagas", scopes=movidos, target=alvo,
                   policy="replace", run_id="chagas-final-2026")
```

`outdated()` compara os arquivos publicados no lake (caminho, e tamanho/mtime quando
registrados) com o que o servidor lista hoje e devolve só os escopos que mudaram —
incluindo um diretório que se moveu ou uma republicação sob o mesmo caminho. A
substituição é sempre explícita: `replace` valida
antes de substituir exatamente aquele ano nacional, e dados e manifesto são publicados
atomicamente. Nada é atualizado por conta própria.

### Contrato de integridade e publicação

- O arquivo inteiro passa pela verificação de tamanho e contagem DBF, pelo staging
  Arrow/Parquet e pela mesma transação dos importadores estaduais.
- A identidade da fonte é declarada no YAML (`x-identity`) e verificada pela moda, não
  registro a registro: o `nu_ano` mais frequente deve ser o ano do arquivo e, se a
  coluna existir, o `id_agravo` mais frequente deve ser `B571`. Um erro de moda rejeita
  o arquivo inteiro; não há descarte silencioso de linhas.
- `_source_ano` e `_source_release` são reservados à biblioteca; um arquivo que traga
  colunas com esses nomes é rejeitado.
- Misturar publicação nacional e estadual na mesma tabela é rejeitado.
- `skip_same` compara primeiro a listagem do FTP: mesmo caminho, tamanho e horário no
  servidor, com o mesmo dicionário, pulam o escopo sem download. Qualquer diferença baixa
  o arquivo e compara o SHA-256. Se o hash, o parser ou o dicionário mudou, exige uma
  decisão explícita de substituição. O padrão geral da API continua `append`; os
  exemplos para pesquisa usam `skip_same`.
- O manifesto guarda SHA-256, versão, URL de origem, IDs de execução e de publicação e
  situação ativa. Manifestos antigos recebem URL nula, sem inventar origem. A URL não é
  um identificador imutável: o hash identifica os bytes adquiridos.

Uma falha de commit pode ter resultado desconhecido. Reabra o lake, consulte
`publications(run_id=...)` e reconcilie antes de repetir a escrita. O lock é local e
cooperativo; isso não estabelece recuperação distribuída.

### Dicionário

Os 108 campos de `src/omnisus/data/dicionarios/sinan_chagas.yaml` são um inventário
físico observado em `CHAGBR23.dbc`, não uma auditoria semântica. Campos adicionais são
preservados; incompatibilidades de tipo seguem a política geral de esquema. A validação
da identidade da fonte não comprova qualidade clínica, completude da vigilância nem
classificação final do caso.

### Notebook

```bash
uv run --locked --extra notebooks marimo edit notebooks/sinan.py
```

Abrir ou exportar o notebook não usa rede nem grava nada. Interromper uma célula não
cancela a thread do importador; espere a conclusão antes de reabrir o mesmo destino.
