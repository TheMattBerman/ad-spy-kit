"""ad-spy-kit category: quote first, newest N per brand, shared labels, embedded images,
shared board checks. Offline: saved brand folders and a mocked ScrapeCreators client."""

import json
import re

import pytest
from PIL import Image

from ad_spy_kit import category, cli
from cie import scrapecreators_client as cie_sc


def _brand(root, name, ads):
    d = root / "brands" / category.slug(name)
    (d / "media").mkdir(parents=True)
    for a in ads:
        Image.new("RGB", (80, 80), (200, 40, 40)).save(d / "media" / f"{a['ad_id']}.jpg")
        a["media"] = [{"path": f"media/{a['ad_id']}.jpg", "durable": True, "kind": "image"}]
    (d / "competitor.json").write_text(json.dumps({"page_name": name, "page_id": "1"}))
    raw = {"source": "scrapecreators", "pulled_at": "2026-11-03T12:00:00Z", "ads": ads}
    (d / "ads.raw.json").write_text(json.dumps(raw))


def _ad(i, days, versions=1, active=True, start="2026-10-01", **kw):
    return {
        "ad_id": f"{900000000000 + i}",
        "headline": f"Holiday offer {i}",
        "body": "",
        "days_live": days,
        "variation_count": versions,
        "is_active": active,
        "start_date": start,
        "label_source": "run_length",
        **kw,
    }


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "saved"
    _brand(root, "Brand One", [_ad(1, 40, 3), _ad(2, 35), _ad(3, 5), _ad(4, 20)])
    many = [_ad(100 + i, 50, start=f"2026-09-{i + 1:02d}") for i in range(28)]
    _brand(root, "Brand Two", many)
    return root


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setattr("cie.scrapecreators_client._load_dotenv_if_needed", lambda *_: None)


def test_quote_without_yes_spends_nothing(key, monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise AssertionError("spent a credit without a yes")

    monkeypatch.setattr(cie_sc.ScrapeCreatorsClient, "request", boom)
    out = tmp_path / "out"
    assert cli.main(["category", "black friday skincare", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "up to 10 brands" in text and "30 most-shown ads that have been live 30+ days" in text
    assert "ScrapeCreators credits" in text and "Nothing spent" in text and "--yes" in text
    assert not out.exists()


def test_brand_list_quote_counts_page_lookups():
    mode, names = category.parse_target("Spacegoods, 104422345678901, Magic Mind")
    assert mode == "brands" and len(names) == 3
    text, low, high = category.quote(mode, names, max_ads=30, max_brands=14, search_pages=2)
    assert (low, high) == (2 + 3, 2 + 3)  # 2 page lookups (the ID is free) + 1 page of 30 each
    _, _, high60 = category.quote(mode, names, max_ads=60, max_brands=14, search_pages=2)
    assert high60 == 2 + 3 * 4  # 60 ads = a page of 30 + three pages of 10
    assert "3 brands" in text


def test_saved_run_renders_labels_and_passes_checks(saved, tmp_path, capsys):
    out = tmp_path / "board"
    code = cli.main(
        ["category", "--from", str(saved), "--out", str(out), "--max-ads", "25", "--title", "Test"]
    )
    assert code == 0, capsys.readouterr()
    report = json.loads((out / "validation.json").read_text())
    assert report == {"ok": True, "errors": []}
    doc = json.loads((out / "category.json").read_text())
    s = doc["summary"]
    # Default: only ads live 30+ days (2 from Brand One), up to 25 per brand.
    assert s["ads"] == 2 + 25
    assert (s["winner"], s["solid"], s["testing"], s["no_label"]) == (0, 27, 0, 0)
    html = (out / "board.html").read_text()
    assert "What 2 brands keep running" in html
    assert "live 30+ days (up to 25), longest first" in (out / "summary.md").read_text()
    assert "data:image/jpeg;base64," in html and "file://" not in html
    assert "900000000001" not in html  # no raw ad IDs on the board
    assert "pull" not in html.lower()
    # Pictures carry the board: one wall, grouped by brand under big names, count honest.
    # No small print: no per-ad quotes, label legend or date on the board itself.
    assert len(re.findall(r'<div class="grp[ "]', html)) == 2 and "Brand One" in html
    assert '<ul class="quotes">' not in html and "checked " not in html
    assert "live 120+ days" not in html
    shown = int(re.search(r"(\d+) of 27 shown", html).group(1))
    assert 0 < shown == html.count('<img class="t ')
    assert (out / "board.png").stat().st_size > 10_000
    assert "winner" in (out / "summary.md").read_text()


def test_newest_mode_never_promises_keep_running(saved, tmp_path, capsys):
    out = tmp_path / "newest"
    args = ["category", "--from", str(saved), "--out", str(out), "--max-ads", "25", "--newest"]
    assert cli.main(args) == 0, capsys.readouterr()
    s = json.loads((out / "category.json").read_text())["summary"]
    assert s["ads"] == 4 + 25
    assert (s["winner"], s["solid"], s["testing"], s["no_label"]) == (0, 27, 2, 0)
    html = (out / "board.html").read_text()
    assert "keep running</h1>" not in html and "The newest ads from 2 brands" in html


def test_no_long_running_ads_says_so(tmp_path, capsys):
    root = tmp_path / "young"
    _brand(root, "New Brand", [_ad(1, 3), _ad(2, 9)])
    assert cli.main(["category", "--from", str(root), "--out", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert "live 30+ days" in err and "--newest" in err


def test_keyword_run_with_yes_pulls_and_renders(key, monkeypatch, tmp_path, saved, capsys):
    rows = [
        {"page_id": "1", "page_name": "Brand One"},
        {"page_id": "2", "page_name": "Reviews Hub"},
    ]
    monkeypatch.setattr(category, "discover", lambda *a, **k: rows)
    monkeypatch.setattr("ad_spy_kit.sc_client._client", lambda: object())

    def fake_pull(brands, out, *, max_ads, country, **kw):
        assert [b["page_name"] for b in brands] == ["Brand One"]  # review pages skipped
        import shutil

        shutil.copytree(saved / "brands" / "brand-one", out / "brands" / "brand-one")
        return []

    monkeypatch.setattr(category, "pull_brands", fake_pull)
    out = tmp_path / "kw"
    assert cli.main(["category", "black friday wallets", "--out", str(out), "--yes"]) == 0
    assert json.loads((out / "validation.json").read_text())["ok"]


def test_shared_checks_catch_claims_and_em_dashes_outside_quotes():
    from ad_spy_kit.validate_run import board_html_errors

    base = '<footer><a href="https://stealads.ai">x</a></footer>'
    assert board_html_errors(base + '<span class="q">"Proven — best ever"</span>') == []
    errs = board_html_errors(base + "<p>They are scaling this — hard</p>")
    assert any(e.startswith("E3") for e in errs) and any(e.startswith("E4") for e in errs)


def test_catalog_ads_stay_off_the_cards_and_are_counted(tmp_path, capsys):
    root = tmp_path / "cat"
    _brand(
        root,
        "Shop Co",
        [
            _ad(1, 200, headline="{{product.name}}", body="{{product.brand}}"),
            _ad(2, 45, headline="Our softest sheets"),
            _ad(3, 90, format="DPA", headline="Fall picks"),
        ],
    )
    _brand(root, "Feed Only", [_ad(4, 300, headline="{{product.name}}")])
    out = tmp_path / "o"
    assert cli.main(["category", "--from", str(root), "--out", str(out)]) == 0, capsys.readouterr()
    s = json.loads((out / "category.json").read_text())["summary"]
    assert (s["written"], s["catalog"]) == (1, 3)
    assert s["written_labels"] == {"winner": 0, "solid": 1, "testing": 0}
    html = (out / "board.html").read_text()
    assert "{{" not in html and "Our softest sheets" not in html  # quotes live in summary.md
    assert "Our softest sheets" in (out / "summary.md").read_text()
    assert "3 catalog ads (Meta fills in the" in (out / "summary.md").read_text()


def test_brands_with_nothing_live_30_days_are_named(tmp_path, capsys):
    root = tmp_path / "mix"
    _brand(root, "Long Runner", [_ad(1, 45)])
    _brand(root, "Quiet Brand", [])
    out = tmp_path / "o"
    assert cli.main(["category", "--from", str(root), "--out", str(out)]) == 0, capsys.readouterr()
    assert "No ads live 30+ days: Quiet Brand" in (out / "summary.md").read_text()


def test_named_page_ids_cost_nothing_and_keep_the_name():
    from ad_spy_kit import sc_client

    assert sc_client.page_id_from_query("Boll & Branch (354593521329931)") == "354593521329931"
    comp = sc_client.resolve_via_scrapecreators("Boll & Branch (354593521329931)")
    assert comp["page_name"] == "Boll & Branch" and not comp["page_name_from_ads"]
    mode, names = category.parse_target("Burrow (612471195588500), BarkBox (264418603594198)")
    text, low, high = category.quote(mode, names, max_ads=30, max_brands=14, search_pages=2)
    assert (low, high) == (2, 2) and "finds" not in text


def test_a_bare_web_address_is_not_a_hook():
    ad = {"headline": "www.fabletics.com", "body": "New cozy drop. Shop now."}
    assert category.hook_line(ad) == "New cozy drop."


def _brands_csv(path, n):
    rows = ["name,page_id,country,sources"]
    rows += [f"Brand {i},{1000000 + i},US,test" for i in range(n)]
    path.write_text("\n".join(rows) + "\n")
    return path


def _fake_reader(monkeypatch, calls, ads_per_brand=3):
    from ad_spy_kit import sc_client

    def fake(brand, *, country, max_ads, media_dir, read, **kw):
        calls.append((brand["page_id"], country, read))
        ads = [
            _ad(int(brand["page_id"]) * 10 + j, days, versions=v, headline=h)
            for j, (days, v, h) in enumerate(
                [
                    (200, 1, "Up to 50% off everything"),
                    (40, 1, "Black Friday starts now"),
                    (5, 1, "Black Friday: up to 70% off"),
                ][:ads_per_brand]
            )
        ]
        return {"ads": ads, "skipped": [], "credits_spent": 1, "pulled_at": "2026-11-05"}

    monkeypatch.setattr(sc_client, "pull_via_scrapecreators", fake)


def test_brands_file_quote_spends_nothing(key, monkeypatch, tmp_path, capsys):
    calls = []
    _fake_reader(monkeypatch, calls)
    f = _brands_csv(tmp_path / "b.csv", 428)
    out = tmp_path / "big"
    args = ["category", "--brands-file", str(f), "--read", "most-shown", "--out", str(out)]
    assert cli.main([*args, "--workers", "4"]) == 0
    text = capsys.readouterr().out
    assert "This reads 428 brands' 30 most-shown live ads (any age): about 428" in text
    assert "Estimated time" in text and "Nothing spent" in text
    assert calls == [] and not out.exists()


def test_big_run_resumes_caps_credits_and_writes_full_data(key, monkeypatch, tmp_path, capsys):
    calls = []
    _fake_reader(monkeypatch, calls)
    f = _brands_csv(tmp_path / "b.csv", 30)
    out = tmp_path / "big"
    base = ["category", "--brands-file", str(f), "--read", "most-shown", "--out", str(out)]
    # The cap stops new brands at 12 credits; nothing past it starts.
    assert cli.main([*base, "--max-credits", "12", "--yes", "--board-brands", "5"]) == 0
    assert len(calls) == 12
    first = capsys.readouterr().out
    assert "[12/30]" in first and "left for later, credit cap 12" in first
    # Rerun with the same --out: the 12 saved brands cost nothing, the other 18 are read.
    assert cli.main([*base, "--yes", "--board-brands", "5", "--workers", "3"]) == 0
    assert len(calls) == 30 and len({c[0] for c in calls}) == 30
    assert "12 brands already saved" in capsys.readouterr().out
    doc = json.loads((out / "category.json").read_text())
    st = doc["stats"]
    assert st["live_30_plus"] == {"ads": 60, "black_friday": 30, "up_to_off": 30}
    assert st["live_under_30"] == {"ads": 30, "black_friday": 30, "up_to_off": 30}
    assert len(doc["brands"]) == 30
    html = (out / "board.html").read_text()
    assert (
        len(re.findall(r'<div class="grp[ "]', html)) <= 5
    )  # the board shows the top 5 brands only
    assert "showing most right now" in html
    rows = (out / "ads.csv").read_text().splitlines()
    assert len(rows) == 1 + 90 and rows[0].startswith("brand,page_id,ad_library_id,label")
    summary = (out / "summary.md").read_text()
    assert summary.count("## Brand ") == 30


def test_most_shown_keeps_every_age_in_api_order():
    ads = [_ad(1, 5), _ad(2, 300), _ad(3, 40, active=False), _ad(4, 12)]
    picked = category.select(ads, 30, read="most-shown")
    assert [a["days_live"] for a in picked] == [5, 300, 12]


def test_read_retries_rate_limits(key, monkeypatch):
    from ad_spy_kit import sc_client

    monkeypatch.setattr(sc_client, "RETRY_WAIT_SECONDS", (0,))
    tries = []

    def flaky(self, company_name=None, *, page_id=None, extra_params=None, **kw):
        tries.append(1)
        if len(tries) < 3:
            raise cie_sc.ScrapeCreatorsClientError("ScrapeCreators API error 429", status=429)
        return [{"ad_archive_id": "1", "start_date": "2020-01-01", "is_active": True}], {}

    monkeypatch.setattr(cie_sc.ScrapeCreatorsClient, "facebook_company_ads", flaky)
    raw = sc_client.pull_via_scrapecreators({"page_id": "1", "page_name": "X"}, read="most-shown")
    assert len(tries) == 3 and len(raw["ads"]) == 1
