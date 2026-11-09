import json
from pathlib import Path

import pytest

from ad_spy_kit.fixtures import fixture_names
from ad_spy_kit.golden import check_golden, snapshot

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = fixture_names()


@pytest.mark.parametrize("name", FIXTURES)
def test_ranking_matches_golden(name):
    assert check_golden(name) == []


def test_golden_catches_reordered_winners(tmp_path, monkeypatch):
    golden = json.loads((ROOT / "fixtures" / "foldbrook" / "golden.json").read_text())
    golden["winner_order"] = list(reversed(golden["winner_order"]))
    assert golden["winner_order"] != snapshot("foldbrook")["winner_order"]
    fake = tmp_path / "fixtures" / "foldbrook"
    fake.mkdir(parents=True)
    (fake / "golden.json").write_text(json.dumps(golden))
    import ad_spy_kit.golden as g

    monkeypatch.setattr(g, "golden_path", lambda name: fake / "golden.json")
    assert any("winner_order" in d for d in check_golden("foldbrook"))
