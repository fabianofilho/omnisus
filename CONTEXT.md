# omnisus

Brings Brazilian public health data (DATASUS, IBGE, CNES) into a lake on a computer, on Google Drive or in the cloud, with the
provenance a researcher needs to cite it.

## Language

### What is imported

**Dataset**:
One family of DATASUS FTP files the package curates, named by its registry key (`sim_obitos`).
_Avoid_: base, table, system

**Scope**:
The unit of import and citation: a UF and a year, plus a month for monthly datasets, or only
a year for national ones.
_Avoid_: recorte, partition, slice

**Population edition**:
One IBGE publication of population by municipality for a year: either the census (2010,
2022) or that year's latest estimate.
_Avoid_: product, IBGE product

**Publication**:
The record that one scope of a dataset was imported from specific server files, with their
hashes.
_Avoid_: import, load, run

### Where it is kept

**Lake**:
Where the imported scopes live, made of one catalog and one storage. It can sit on a
computer, on Google Drive, or in the cloud (a PostgreSQL catalog with S3 storage).
_Avoid_: database, warehouse

**Catalog**:
The database that records the lake's tables, snapshots and publications, and where its
storage is. It is the authority on what the lake contains.
_Avoid_: metadata, index

**Storage**:
The folder that holds the lake's Parquet files. It is fixed when the lake is created; the
catalog remembers it.
_Avoid_: data dir, data path

### What the values mean

**Dictionary**:
The packaged description of a dataset's fields: names, types, labels and code maps.
_Avoid_: schema, metadata, layout

**Code**:
A field value exactly as DATASUS published it (`"2"`, `"I219"`).
_Avoid_: raw value

**Label**:
The text the dictionary gives to a code (`"2"` → `"Feminino"`). A code the dictionary does
not know has no label; it is never guessed. In Portuguese docs and in column names
(`sexo_rotulo`) it is *rótulo*.
_Avoid_: decoded value, display value

**Harmonised category**:
A value derived by an audited rule so that the same concept compares across datasets
(`sexo_categoria`, `idade_anos_completos`). It exists only for validated sources.
_Avoid_: normalised value, first-letter sex

**Validated source**:
A scope's file, identified by its hash, whose codes were checked against a rule's edition.
_Avoid_: confirmed scope

### Record linkage

**Exact key**:
A record identifier published in both files, such as the AIH number (`n_aih`, `sp_naih`) or
the encrypted patient CNS.
_Avoid_: ID key, hard key

**Composite key**:
A combination of person attributes, such as birth date + sex + municipality of residence,
used when no exact key exists.
_Avoid_: probabilistic key, soft key

**Shared event**:
A fact that both records describe the same way, such as death date = discharge date.
Adding one to a composite key is what makes the key identify a person.
_Avoid_: common variable

**Linkage pass** (passo):
One join on one key in a cascade from the strictest key to the loosest. Each pass sees only
the records that earlier passes left unlinked.
_Avoid_: step, round

**Negative control** (controle negativo):
The same pass, run on the same remaining records, with one key deliberately shifted: birth
date by 7 days, or age or birth year by 1. Every pair it finds is a coincidence, so the
count estimates the chance pairs in the real pass.
_Avoid_: placebo, null model

**Viable linkage**:
Every kept pass has at most 5% estimated chance, and the strongest validation on a
variable that was not a key agrees in at least 90% of pairs. Between 5% and 20% chance, or
between 75% and 90% agreement, the linkage is "use with caution". Above 20% chance, or
when a pass's control finds as many pairs as the pass itself, it is "not viable".
_Avoid_: reliable, good linkage
