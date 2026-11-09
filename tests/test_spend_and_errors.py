"""Quote before spend on every ScrapeCreators path; errors say what actually broke."""

import json

import pytest

from ad_spy_kit import cli, sc_client
from ad_spy_kit.errors import KitError
from cie import scrapecreators_client as cie_sc


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setattr("cie.scrapecreators_client._load_dotenv_if_needed", lambda *_: None)


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("spent a credit without a yes")

    monkeypatch.setattr(cie_sc.ScrapeCreatorsClient, "request", boom)


def test_run_quotes_and_spends_nothing_without_yes(key, no_network, capsys):
    assert cli.main(["run", "Some Brand"]) == 0
    out = capsys.readouterr().out
    assert "30 most-shown ads that have been live 30+ days" in out
    assert "ScrapeCreators credit" in out
    assert "Nothing spent" in out and "--yes" in out


def test_pull_and_resolve_quote_first(key, no_network, tmp_path, capsys):
    (tmp_path / "competitor.json").write_text(json.dumps({"page_id": "1", "page_name": "X"}))
    assert cli.main(["pull", str(tmp_path)]) == 0
    assert cli.main(["resolve", "Some Brand"]) == 0
    out = capsys.readouterr().out
    assert out.count("Nothing spent") == 2
    assert not (tmp_path / "ads.raw.json").exists()


@pytest.mark.parametrize(
    ("query", "page_id"),
    [
        ("123456789012", "123456789012"),
        (
            "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US"
            "&view_all_page_id=104422345678901",
            "104422345678901",
        ),
        ("facebook.com/profile.php?id=100064123456789", "100064123456789"),
        ("Spacegoods", None),
    ],
)
def test_page_id_and_page_links_resolve_without_a_search(query, page_id):
    assert sc_client.page_id_from_query(query) == page_id


def test_page_id_resolve_spends_nothing(no_network, monkeypatch):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    comp = sc_client.resolve_via_scrapecreators("104422345678901")
    assert comp["page_id"] == "104422345678901" and comp["confidence"] == "exact"


def test_single_ad_link_says_how_to_get_the_page_link():
    with pytest.raises(KitError) as e:
        sc_client.page_id_from_query("https://www.facebook.com/ads/library/?id=833977852400418")
    assert "one ad" in e.value.message and "view_all_page_id" in e.value.fix


def _http_error(monkeypatch, status):
    def fail(self, path, params=None):
        raise cie_sc.ScrapeCreatorsClientError(f"ScrapeCreators API error {status}", status=status)

    monkeypatch.setattr(cie_sc.ScrapeCreatorsClient, "request", fail)


@pytest.mark.parametrize(
    ("status", "words"),
    [(401, "turned down your API key"), (403, "turned down your API key"), (402, "out of credits")],
)
def test_bad_key_or_empty_balance_is_not_no_page_found(key, monkeypatch, status, words):
    _http_error(monkeypatch, status)
    with pytest.raises(KitError) as e:
        sc_client.resolve_via_scrapecreators("Spacegoods")
    assert words in e.value.message
    assert "no Facebook page" not in e.value.render()


def test_real_not_found_still_says_no_page(key, monkeypatch):
    _http_error(monkeypatch, 404)
    with pytest.raises(KitError) as e:
        sc_client.resolve_via_scrapecreators("Nobody Brand")
    assert "no Facebook page" in e.value.message
    assert "view_all_page_id" in e.value.fix


def test_default_read_asks_for_ads_live_30_days_most_shown_first():
    from datetime import date

    p = sc_client.read_params(newest=False, today=date(2026, 11, 4))
    assert p == {
        "status": "ACTIVE",
        "sort_by": "total_impressions",
        "start_date": "2010-01-01",
        "end_date": "2026-10-05",  # overlap filter: still live and already running 30 days ago
    }
    assert sc_client.read_params(newest=True) == {
        "status": "ACTIVE",
        "sort_by": "relevancy_monthly_grouped",
    }


def test_pull_drops_ads_under_30_days_unless_newest(key, monkeypatch, tmp_path):
    rows = [
        {"ad_archive_id": "1", "start_date": "2020-01-01", "is_active": True},
        {"ad_archive_id": "2", "start_date": "2099-01-01", "is_active": True},
    ]
    seen = {}

    def fake_ads(self, company_name=None, *, page_id=None, extra_params=None, **kw):
        seen.update(extra_params or {})
        return rows, {}

    monkeypatch.setattr(cie_sc.ScrapeCreatorsClient, "facebook_company_ads", fake_ads)
    comp = {"page_id": "1", "page_name": "X"}
    raw = sc_client.pull_via_scrapecreators(comp)
    assert [a["ad_id"] for a in raw["ads"]] == ["1"] and raw["dropped_too_new"] == 1
    assert raw["read_mode"] == "longest" and seen["sort_by"] == "total_impressions"
    raw = sc_client.pull_via_scrapecreators(comp, newest=True)
    assert len(raw["ads"]) == 2 and raw["read_mode"] == "newest"


def test_quote_page_math_matches_observed_page_sizes():
    from ad_spy_kit.spend import pull_pages

    assert pull_pages(30) == (1, 1)  # first page holds about 30
    assert pull_pages(60) == (1, 4)  # then 10 per page
    assert pull_pages(90) == (1, 7)


def test_every_format_has_plain_words():
    from ad_spy_kit.plain import FORMAT_NAMES
    from cie.taxonomy import ALL_FORMATS

    assert set(ALL_FORMATS) <= set(FORMAT_NAMES)
