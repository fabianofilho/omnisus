"""Explicit, verified municipal population products (never substitute products)."""

from dataclasses import dataclass
from datetime import date

_ESTIMATE_REFERENCE_SOURCE = (
    "https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativasde-populacao.html"
)
_CENSUS_REFERENCE_SOURCES = {
    2010: "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2010/"
    "metodologia/metodologia_censo_dem_2010.pdf",
    2022: "https://www.ibge.gov.br/Estatisticas/Sociais/Populacao/"
    "22827-censo-demografico-2022.html?edicao=41815",
}
CENSUS_YEARS: tuple[int, ...] = tuple(sorted(_CENSUS_REFERENCE_SOURCES))
"""Census editions with a verified municipal population product, ascending."""
ESTIMATE_UNAVAILABLE_YEARS: tuple[int, ...] = (2007, 2010, 2022, 2023)
"""Years without an estimate edition; census years are never substituted."""


@dataclass(frozen=True)
class PopulationProduct:
    name: str
    aggregate: int
    variable: int
    population_reference_date: date
    population_reference_source_url: str
    population_reference_note: str
    classifications: tuple[tuple[str, str], ...] = ()


def resolve_product(product: str, year: int) -> PopulationProduct:
    if type(year) is not int or not 1900 <= year <= 9999:
        raise ValueError("year must be an explicit four-digit integer")
    if product == "estimate":
        if year in ESTIMATE_UNAVAILABLE_YEARS:
            raise ValueError(f"estimate unavailable for {year}; no automatic census substitution")
        return PopulationProduct(
            "estimate",
            6579,
            9324,
            date(year, 7, 1),
            _ESTIMATE_REFERENCE_SOURCE,
            "1º de julho do ano calendário, conforme definição oficial do produto; "
            "não é data de publicação ou revisão.",
        )
    if product == "census" and year in CENSUS_YEARS:
        return PopulationProduct(
            "census",
            202 if year == 2010 else 4714,
            93,
            date(year, 8, 1),
            _CENSUS_REFERENCE_SOURCES[year],
            f"No IBGE: noite de 31/07/{year} para 01/08/{year}; "
            "DATE representa o limite à meia-noite no início de 01/08, "
            "sem atribuição de fuso UTC ou data de coleta.",
            (("2", "0"), ("1", "0")) if year == 2010 else (),
        )
    census_years = ", ".join(map(str, CENSUS_YEARS))
    raise ValueError(f"product must be 'estimate' or 'census' (census years: {census_years})")
