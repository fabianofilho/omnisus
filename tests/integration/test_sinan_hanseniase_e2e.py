"""Live: one final and one preliminary year through the same row, then outdated() is empty."""

import pytest

import omnisus as sus

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def test_final_and_preliminary_years_share_one_table(tmp_path):
    releases = sus.available_releases("sinan_hanseniase", refresh=True)

    def latest(release):
        """ScopeKey is not orderable, so the newest year is picked explicitly."""
        return max((s for s, r in releases.items() if r == release), key=lambda s: s.ano)

    final, prelim = latest("final"), latest("prelim")
    target = f"ducklake:{tmp_path}/hans.ducklake"
    report = sus.import_dataset(
        "sinan_hanseniase",
        scopes=[final, prelim],
        target=target,
        policy="skip_same",
        run_id="pilot",
        batch_size=1,
        concurrency=1,
    )
    assert not report.failed and len(report.ok) == 2
    with sus.Lake.local(target) as lake:
        rows = {r["scope"].ano: r["release"] for r in lake.publications()}
        assert rows == {final.ano: "final", prelim.ano: "prelim"}
        by_release = dict(
            lake.connect()
            .execute("SELECT _source_release, count(*) FROM lake.sinan_hanseniase GROUP BY 1")
            .fetchall()
        )
        assert set(by_release) == {"final", "prelim"}
        assert sus.outdated("sinan_hanseniase", lake=lake) == []
