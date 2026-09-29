"""The DATASUS-FTP dataset registry — single source of truth.

One frozen row per dataset. The FTP path map, filename prefix map, CLI
choices and docs all derive from these rows. Adding a dataset is one row
here plus one ``data/dicionarios/<name>.yaml``.

The registry is a catalog, not a gate (ADR 0002): the pipeline
takes ``Dataset`` *values*, so a ``Dataset`` built by a caller flows through
the same path as a registered one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from omnisus.sources._base import ScopeKey

YM = tuple[int, int]
"""``(year, month)``, e.g. ``(2008, 1)``."""

Cadence = Literal["yearly", "monthly"]

Release = Literal["final", "prelim"]
"""Which DATASUS directory a file was published in. ``prelim`` files are
revised and later moved to the final directory under the same name."""


@dataclass(frozen=True, kw_only=True)
class Dataset:
    """Identity and location of one DATASUS-FTP dataset.

    Holds *only* identity and location. Anything behavioural
    belongs in an importer module, never as a flag here.
    """

    name: str
    """Registry key = lake table = YAML stem = CLI name (``sim_obitos``)."""

    prefix: str
    """DATASUS filename prefix: ``DO``, ``DN``, ``RD``, ``BI``, ``ATD``…"""

    ftp_dir: str
    """Directory on ``ftp.datasus.gov.br`` holding this dataset's files."""

    cadence: Cadence
    """How DATASUS publishes files. Decides filename shape (upstream fact)."""

    partition_by: tuple[str, ...]
    """How the lake table is laid out (our storage policy).

    Applied by ``Lake.ingest`` via ``SET PARTITIONED BY`` when the table is
    created, so files land under ``ano=…/uf=…/``. Each scope is already one
    ``(uf, ano[, mes])``, so partitioning costs nothing at write time and buys
    query pruning."""

    coverage: tuple[YM, YM | None]
    """``(first, last)`` published; ``last=None`` means ongoing.

    Provisional until the Tier 3 probe validates it against the server.
    """

    dictionary: Path | None = None
    """Frictionless YAML. ``None`` -> packaged ``dicionarios/<name>.yaml``."""

    geography: Literal["state", "national"] = "state"
    """Source coverage. National SINAN filenames use PREFIX + BR + YY."""

    year_digits: Literal[2, 4] = 4
    """Year width in a yearly state file name: 4 (``DORR2023.dbc``) or 2 (SIM CID-9's
    ``DORRR79.DBC``). Monthly and national names always carry two digits."""

    national_code: str = "BR"
    """What a national file name carries between prefix and year: ``BR`` for SINAN
    (``CHAGBR23.dbc``), nothing for the SIM subsets (``DOEXT23.dbc``)."""

    prelim_dir: str | None = None
    """Directory where DATASUS publishes this dataset's preliminary files,
    when it has one. Same filenames as ``ftp_dir``; a file is in one or the
    other, never both."""

    @property
    def monthly(self) -> bool:
        return self.cadence == "monthly"

    def directories(self) -> dict[Release, str]:
        """Every FTP directory this dataset is published in, final first.

        Returns:
            ``{"final": path}``, plus ``"prelim"`` when DATASUS publishes preliminary
            files elsewhere.

        Examples:
            >>> import omnisus as sus
            >>> sus.resolve("sim_obitos").directories()["prelim"]
            '/dissemin/publicos/SIM/PRELIM/DORES'
        """
        dirs: dict[Release, str] = {"final": self.ftp_dir}
        if self.prelim_dir is not None:
            dirs["prelim"] = self.prelim_dir
        return dirs


_SIM = "/dissemin/publicos/SIM/CID10/DORES"
_SINASC = "/dissemin/publicos/SINASC/1996_/Dados/DNRES"
_SIH = "/dissemin/publicos/SIHSUS/200801_/Dados"
_SIA = "/dissemin/publicos/SIASUS/200801_/Dados"
_CNES_ST = "/dissemin/publicos/CNES/200508_/Dados/ST"
_CNES = "/dissemin/publicos/CNES/200508_/Dados/"
_SIM_SUBSETS = "/dissemin/publicos/SIM/CID10/DOFET"
_SIM_CID9 = "/dissemin/publicos/SIM/CID9/DORES"
_SIH_1992 = "/dissemin/publicos/SIHSUS/199201_200712/Dados"
_SIA_1994 = "/dissemin/publicos/SIASUS/199407_200712/Dados"
_SINASC_1994 = "/dissemin/publicos/SINASC/1994_1995/Dados/DNRES"

_SINAN_FINAIS = "/dissemin/publicos/SINAN/DADOS/FINAIS"
_SINAN_PRELIM = "/dissemin/publicos/SINAN/DADOS/PRELIM"

_YEARLY = ("ano", "uf")
_MONTHLY = ("ano", "uf", "mes")

# fmt: off
_ROWS: tuple[Dataset, ...] = (
    Dataset(name="sinan_chagas",                  prefix="CHAG", ftp_dir=_SINAN_FINAIS, prelim_dir=_SINAN_PRELIM, cadence="yearly",  partition_by=("_source_ano",), coverage=((2000, 1), None), geography="national"),
    Dataset(name="sinan_hanseniase",              prefix="HANS", ftp_dir=_SINAN_FINAIS, prelim_dir=_SINAN_PRELIM, cadence="yearly",  partition_by=("_source_ano",), coverage=((2001, 1), None), geography="national"),
    Dataset(name="sinan_tuberculose",             prefix="TUBE", ftp_dir=_SINAN_FINAIS, prelim_dir=_SINAN_PRELIM, cadence="yearly",  partition_by=("_source_ano",), coverage=((2001, 1), None), geography="national"),
    Dataset(name="sim_obitos",                    prefix="DO",   ftp_dir=_SIM,     prelim_dir="/dissemin/publicos/SIM/PRELIM/DORES",     cadence="yearly",  partition_by=_YEARLY,  coverage=((1996, 1), None)),
    Dataset(name="sinasc_nascidos_vivos",         prefix="DN",   ftp_dir=_SINASC,  prelim_dir="/dissemin/publicos/SINASC/PRELIM/DNRES",  cadence="yearly",  partition_by=_YEARLY,  coverage=((1996, 1), None)),
    Dataset(name="sih_aih_reduzida",              prefix="RD",   ftp_dir=_SIH,     cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_bpa_individualizado",       prefix="BI",   ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_apac_medicamentos",         prefix="AM",   ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_apac_quimioterapia",        prefix="AQ",   ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_apac_tratamento_dialitico", prefix="ATD",  ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2014, 8), None)),
    Dataset(name="sia_apac_laudos_diversos",      prefix="AD",   ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_apac_cirurgia_bariatrica",  prefix="ABO",  ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2014, 1), None)),
    Dataset(name="sia_psicossocial",              prefix="PS",   ftp_dir=_SIA,     cadence="monthly", partition_by=_MONTHLY, coverage=((2012, 11), None)),
    Dataset(name="cnes_estabelecimentos",         prefix="ST",   ftp_dir=_CNES_ST, cadence="monthly", partition_by=("ano", "mes"), coverage=((2005, 8), None)),
    # Rows read from the server listings of 2026-09-22.
    Dataset(name="sia_producao_ambulatorial", prefix="PA", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sih_aih_rejeitada", prefix="RJ", ftp_dir=_SIH, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sih_servicos_profissionais", prefix="SP", ftp_dir=_SIH, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sih_aih_rejeitada_erro", prefix="ER", ftp_dir=_SIH, cadence="monthly", partition_by=_MONTHLY, coverage=((2011, 1), None)),
    Dataset(name="cnes_dados_complementares", prefix="DC", ftp_dir=_CNES + "DC", cadence="monthly", partition_by=_MONTHLY, coverage=((2005, 8), None)),
    Dataset(name="cnes_equipamentos", prefix="EQ", ftp_dir=_CNES + "EQ", cadence="monthly", partition_by=_MONTHLY, coverage=((2005, 8), None)),
    Dataset(name="cnes_equipes", prefix="EP", ftp_dir=_CNES + "EP", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 4), None)),
    Dataset(name="cnes_estabelecimentos_ensino", prefix="EE", ftp_dir=_CNES + "EE", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 3), (2021, 7))),
    Dataset(name="cnes_estabelecimentos_filantropicos", prefix="EF", ftp_dir=_CNES + "EF", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 3), None)),
    Dataset(name="cnes_gestao_metas", prefix="GM", ftp_dir=_CNES + "GM", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 3), None)),
    Dataset(name="cnes_habilitacoes", prefix="HB", ftp_dir=_CNES + "HB", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 3), None)),
    Dataset(name="cnes_incentivos", prefix="IN", ftp_dir=_CNES + "IN", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 10), None)),
    Dataset(name="cnes_leitos", prefix="LT", ftp_dir=_CNES + "LT", cadence="monthly", partition_by=_MONTHLY, coverage=((2005, 10), None)),
    Dataset(name="cnes_regras_contratuais", prefix="RC", ftp_dir=_CNES + "RC", cadence="monthly", partition_by=_MONTHLY, coverage=((2007, 3), None)),
    Dataset(name="cnes_servicos_especializados", prefix="SR", ftp_dir=_CNES + "SR", cadence="monthly", partition_by=_MONTHLY, coverage=((2005, 8), None)),
    Dataset(name="sim_obitos_fetais", prefix="DOFET", ftp_dir=_SIM_SUBSETS, cadence="yearly", partition_by=("_source_ano",), coverage=((1996, 1), None), geography="national", national_code=""),
    Dataset(name="sim_obitos_externos", prefix="DOEXT", ftp_dir=_SIM_SUBSETS, cadence="yearly", partition_by=("_source_ano",), coverage=((1996, 1), None), geography="national", national_code=""),
    Dataset(name="sim_obitos_infantis", prefix="DOINF", ftp_dir=_SIM_SUBSETS, cadence="yearly", partition_by=("_source_ano",), coverage=((1996, 1), None), geography="national", national_code=""),
    Dataset(name="sim_obitos_maternos", prefix="DOMAT", ftp_dir=_SIM_SUBSETS, cadence="yearly", partition_by=("_source_ano",), coverage=((1996, 1), None), geography="national", national_code=""),
    Dataset(name="sim_obitos_cid9", prefix="DOR", ftp_dir=_SIM_CID9, cadence="yearly", partition_by=_YEARLY, coverage=((1979, 1), (1995, 12)), year_digits=2),
    Dataset(name="sih_aih_reduzida_1992_2007", prefix="RD", ftp_dir=_SIH_1992, cadence="monthly", partition_by=_MONTHLY, coverage=((1992, 1), (2007, 12))),
    Dataset(name="sia_producao_ambulatorial_1994_2007", prefix="PA", ftp_dir=_SIA_1994, cadence="monthly", partition_by=_MONTHLY, coverage=((1994, 7), (2007, 12))),
    Dataset(name="sinasc_1994_1995", prefix="DNR", ftp_dir=_SINASC_1994, cadence="yearly", partition_by=_YEARLY, coverage=((1994, 1), (1995, 12))),
    # SIA families of Informe Técnico SIASUS 2019-07, coverage from the listing of
    # 2026-09-23.
    Dataset(name="sia_apac_acompanhamento_bariatrica", prefix="AB", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), (2025, 7))),
    Dataset(name="sia_apac_fistula_arteriovenosa", prefix="ACF", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2014, 8), None)),
    Dataset(name="sia_apac_acompanhamento_multiprofissional", prefix="AMP", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2016, 3), None)),
    Dataset(name="sia_apac_nefrologia", prefix="AN", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), (2014, 10))),
    Dataset(name="sia_apac_radioterapia", prefix="AR", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2008, 1), None)),
    Dataset(name="sia_atencao_domiciliar", prefix="SAD", ftp_dir=_SIA, cadence="monthly", partition_by=_MONTHLY, coverage=((2012, 4), (2018, 10))),
)
# fmt: on

REGISTRY: dict[str, Dataset] = {d.name: d for d in _ROWS}


def resolve(dataset: str | Dataset) -> Dataset:
    """The :class:`Dataset` for a name; a ``Dataset`` value passes through.

    A value passing through untouched is how an uncurated dataset reaches the
    pipeline.

    Args:
        dataset: Dataset name, e.g. ``"sim_obitos"``, or a ``Dataset``.

    Returns:
        The registry row: name, FTP directories, geography, monthly or yearly.

    Raises:
        ValueError: the name is not in the registry.

    Examples:
        >>> import omnisus as sus
        >>> d = sus.resolve("sih_aih_reduzida")
        >>> (d.geography, d.monthly)
        ('state', True)
    """
    if isinstance(dataset, Dataset):
        return dataset
    try:
        return REGISTRY[dataset]
    except KeyError:
        raise ValueError(f"unknown dataset: {dataset!r}") from None


def in_coverage(dataset: str | Dataset, scope: ScopeKey) -> bool:
    """Whether ``scope`` falls inside the dataset's declared coverage window.

    The cheapest possible filter: a scope outside coverage cannot exist
    upstream, so rejecting it here saves a full FTP connect, login, CWD and
    PASV setup before the 550 that would have said the same thing.

    Yearly datasets carry no month, so their scopes are compared at month 1.
    A ``last`` of ``None`` means the dataset is ongoing and has no end bound.
    """
    d = resolve(dataset)
    first, last = d.coverage
    ym = (scope.ano, scope.mes if scope.mes is not None else 1)
    if ym < first:
        return False
    return not (last is not None and ym > last)


def release_of(d: Dataset, directory: str) -> Release | None:
    """Which of ``d``'s directories ``directory`` is, or ``None``."""
    directory = directory.rstrip("/")
    for release, path in d.directories().items():
        if path == directory:
            return release
    return None


def release_from_uri(dataset: str, source_uri: str | None) -> Release | None:
    """Which release a stored ``source_uri`` came from, or ``None`` when the
    dataset is not registered, the URI is unknown or its directory is not
    one this row declares. The host is ignored, so an overridden host
    (``OMNISUS_FTP_HOST``) resolves like the default one."""
    d = REGISTRY.get(dataset)
    if d is None or not source_uri or not source_uri.startswith("ftp://"):
        return None
    return release_of(d, urlparse(source_uri).path.rsplit("/", 1)[0])
