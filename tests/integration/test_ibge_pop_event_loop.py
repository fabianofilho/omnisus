"""`sus.import_ibge_populacao` from inside a running event loop (marimo, Jupyter).

Real data: the IBGE aggregate 4714 responses in `tests/unit/sources/ibge/fixtures`.
"""

import asyncio

import pytest
import respx

import omnisus as sus
from tests.integration.test_ibge_pop_e2e import mock_source


@pytest.mark.integration
@respx.mock
def test_import_ibge_populacao_runs_inside_a_running_event_loop(tmp_path):
    mock_source()
    target = f"ducklake:{tmp_path}/lake.ducklake"

    async def notebook_cell():
        return sus.import_ibge_populacao(years=[2022], census=True, target=target)

    (result,) = asyncio.run(notebook_cell())

    assert result.rows == 2


def test_import_ibge_populacao_requires_choosing_census_or_estimate():
    """No default: nobody gets an estimate while thinking it is the census."""
    with pytest.raises(TypeError, match="census"):
        sus.import_ibge_populacao(years=[2022])
