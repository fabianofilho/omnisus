"""Optional live verification; source availability is distinct from offline CI."""

import pytest

import omnisus as sus

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def test_live_chagas_publication_and_replay(tmp_path):
    scopes = sus.available("sinan_chagas", refresh=True)
    assert scopes, "Source disappeared or no filenames match the contract"
    scope = scopes[-1]
    target = f"ducklake:{tmp_path}/chagas.ducklake"
    initial = sus.import_dataset(
        "sinan_chagas",
        scopes=[scope],
        target=target,
        policy="skip_same",
        run_id="initial",
        batch_size=1,
        concurrency=1,
    )
    assert initial.ok and not initial.failed and initial.rows > 0
    replay = sus.import_dataset(
        "sinan_chagas",
        scopes=[scope],
        target=target,
        policy="skip_same",
        run_id="replay",
        batch_size=1,
        concurrency=1,
    )
    assert not replay.failed and replay.rows == 0 and len(replay.skipped) == 1
    with sus.Lake.local(target) as lake:
        publications = lake.publications()
        assert len(publications) == 1
        assert publications[0]["source_uri"].endswith(f"CHAGBR{scope.ano % 100:02d}.dbc")
        count = (
            lake.connect()
            .execute("SELECT count(*) FROM lake.sinan_chagas WHERE _source_ano = ?", [scope.ano])
            .fetchone()[0]
        )
        assert count == initial.rows
