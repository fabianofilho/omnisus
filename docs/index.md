# omnisus

Importa bases públicas de saúde do Brasil (DATASUS, IBGE, CNES) para um lake
[DuckLake](https://ducklake.select), no seu computador, no Google Drive ou na nuvem, com
a procedência necessária para citar cada resultado.

!!! warning "Trabalho em construção (v0.1)"
    A API ainda pode mudar entre versões menores, e nem todo dicionário foi conferido
    contra o documento oficial. Antes de publicar um número, confira as contagens com o
    DATASUS e os rótulos com a fonte ([como conferir](dicionario/index.md)). Um rótulo
    errado é um bug: [abra uma issue](https://github.com/raphaelfh/omnisus/issues/new/choose).

```python
import omnisus as odb

dados = odb.load("sim_obitos", years=[2023], ufs=["RR"])             # baixa e devolve as linhas
dados = odb.label("sim_obitos", dados, columns=["sexo", "racacor"])  # + sexo_rotulo, racacor_rotulo
odb.check_columns("sim_obitos", dados)                               # vazios, códigos sem rótulo, datas
```

## O que faz

- **Baixa** os arquivos DBC do FTP do DATASUS, a população do IBGE e os nomes de
  estabelecimentos da API do CNES.
- **Decodifica** DBC e DBF em lotes gravados em disco, em Rust quando o decodificador
  opcional está instalado e em Python nos outros casos.
- **Guarda** Parquet num catálogo DuckLake (SQLite ou PostgreSQL). Cada recorte importado
  fica registrado com os arquivos de origem e o SHA-256 de cada um.
- **Rotula** códigos e confere colunas com dicionários em que cada afirmação cita um
  documento oficial.

## Por onde começar

| Você quer | Leia |
| --- | --- |
| Responder uma pergunta de pesquisa com uma base | [Comece aqui](pesquisa/index.md) e os notebooks |
| Saber de onde vem um rótulo e como conferi-lo | [De onde vem cada rótulo](dicionario/index.md) |
| Instalar e fazer a primeira importação | [Getting Started](guides/getting-started.md) |
| Saber quais bases existem e o que passar em `years`, `ufs` e `months` | [Bases e argumentos](datasets.md) |
| Consultar uma função | [API](api.md) |
| Corrigir um rótulo ou acrescentar uma base | [Como contribuir](contributing.md) |
