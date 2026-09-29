"""A scope rejected before it writes fails alone.

One bad file of RD SP 2023 used to roll back the whole batch: 11 good months
were reported ``rolled_back`` and nothing was committed. Staging and identity
checks run before the scope touches the lake transaction, so a rejection there
must not cost the other scopes of the batch.
"""

from __future__ import annotations

from pathlib import Path

import omnisus as sus
from omnisus.lake import Lake
from omnisus.sources._base import ScopeKey
from tests.support import fake_datasus

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "dbc" / "sia_ar_ac_2024_01_mini.dbc"


def test_a_scope_rejected_by_identity_does_not_roll_back_its_batch(monkeypatch, tmp_path):
    """ARAC2401 is served as itself and as MG; identity rejects the MG copy."""
    good, wrong = ScopeKey(uf="AC", ano=2024, mes=1), ScopeKey(uf="MG", ano=2024, mes=1)
    raw = FIXTURE.read_bytes()
    fake_datasus.serve(monkeypatch, "sia_apac_radioterapia", {good: raw, wrong: raw})
    target = f"ducklake:{tmp_path}/lake.ducklake"
    report = sus.import_dataset(
        "sia_apac_radioterapia", scopes=[good, wrong], target=target, concurrency=1
    )
    assert [(o.status, o.code) for o in report.outcomes] == [
        ("ok", None),
        ("failed", "ingest_failed"),
    ]
    assert "ap_ufmun" in (report.outcomes[1].reason or "")
    with Lake.local(target) as lake:
        published = [p["scope"] for p in lake.publications()]
    assert published == [good]
