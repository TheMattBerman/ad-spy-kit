"""Ad images are saved at read time (Meta's links expire), from the URLs the read already
returned, in parallel, size-capped, failing quietly. Network is mocked throughout."""

import contextlib
import io
import json
import time

import httpx
import pytest
from PIL import Image

from ad_spy_kit import category, cli, sc_client
from ad_spy_kit.sl_adapter import sc_media


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 75), (30, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


class _Resp:
    def __init__(self, url, body=b"", ctype="image/jpeg", status=200, length=None):
        self.url, self.body, self.status = url, body, status
        self.headers = {"content-type": ctype}
        if length is not None:
            self.headers["content-length"] = str(length)

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def iter_bytes(self):
        for i in range(0, len(self.body), 1024):
            yield self.body[i : i + 1024]


@pytest.fixture
def net(monkeypatch):
    """url → _Resp. Any unknown URL fails like a dead link. Records every URL fetched."""
    routes: dict[str, _Resp] = {}
    seen: list[str] = []

    @contextlib.contextmanager
    def fake_stream(method, url, **kw):
        seen.append(url)
        if url not in routes:
            raise httpx.ConnectError("dead link")
        yield routes[url]

    monkeypatch.setattr(httpx, "stream", fake_stream)
    return routes, seen


def test_download_saves_images_and_rejects_bad_ones(net, tmp_path):
    routes, _ = net
    routes["https://x/ok"] = _Resp("ok", _jpeg())
    routes["https://x/png"] = _Resp("png", b"\x89PNG....", ctype="image/png")
    routes["https://x/html"] = _Resp("html", b"<html>login</html>", ctype="text/html")
    routes["https://x/big"] = _Resp("big", b"0" * 5000)
    routes["https://x/says-big"] = _Resp("sb", b"0", length=10**9)
    routes["https://x/404"] = _Resp("404", status=404)
    path, digest = sc_client._download("https://x/ok", tmp_path / "a")
    assert path.name == "a.jpg" and len(digest) == 64 and Image.open(path).size == (60, 75)
    assert sc_client._download("https://x/png", tmp_path / "b")[0].name == "b.png"
    assert sc_client._download("https://x/html", tmp_path / "c") is None
    assert sc_client._download("https://x/big", tmp_path / "d", max_bytes=4096) is None
    assert sc_client._download("https://x/says-big", tmp_path / "e") is None
    assert sc_client._download("https://x/404", tmp_path / "f") is None
    assert sc_client._download("https://x/gone", tmp_path / "g") is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg", "b.png"]


def test_catalog_and_carousel_cards_keep_the_picture_on_the_card():
    dpa = {"display_format": "DPA", "images": [], "cards": [{"resized_image_url": "https://c/1"}]}
    assert sc_media(dpa) == [{"url": "https://c/1", "durable": False, "kind": "image"}]
    vid = {"cards": [{"video_preview_image_url": "https://c/v", "video_sd_url": "https://c/sd"}]}
    assert sc_media(vid)[0] == {"url": "https://c/v", "durable": False, "kind": "video_preview"}
    assert sc_media({"cards": [{"resized_image_url": "{{product.image}}"}]}) == []


def test_cache_media_runs_in_parallel_and_counts_failures(tmp_path):
    ads = [
        {"ad_id": str(i), "media": [{"url": f"https://x/{i}", "kind": "image"}]} for i in range(16)
    ]
    ads.append({"ad_id": "none", "media": []})

    def slow(url, stem):
        time.sleep(0.15)
        if url.endswith("/3"):
            return None
        if url.endswith("/4"):
            raise RuntimeError("boom")
        p = stem.with_suffix(".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p, "h"

    t = time.monotonic()
    skipped = sc_client.cache_media(ads, tmp_path / "media", downloader=slow, workers=8)
    assert time.monotonic() - t < 1.5  # 16 x 0.15s one at a time would be 2.4s
    assert skipped == [
        {"ad_id": "3", "reason": "media_download_failed"},
        {"ad_id": "4", "reason": "media_download_failed"},
        {"ad_id": "none", "reason": "no_media"},
    ]
    assert sc_client.image_counts(ads, skipped) == {"saved": 14, "failed": 2, "none": 1}
    assert ads[0]["media"] == [{"path": "media/0.jpg", "durable": False, "kind": "image"}]
    assert "https://" not in json.dumps(ads)


def _sc_row(i, card_image=True):
    snap = {
        "page_name": "Feed Co",
        "display_format": "DPA" if card_image else "IMAGE",
        "title": f"Holiday pick {i}",
        "body": {"text": "Gifts they keep."},
        "images": [] if card_image else [{"resized_image_url": f"https://cdn/{i}.jpg"}],
        "cards": [{"resized_image_url": f"https://cdn/{i}.jpg"}] if card_image else [],
    }
    return {
        "ad_archive_id": f"77{i}",
        "is_active": True,
        "start_date": 1700000000,
        "snapshot": snap,
    }


class _FakeClient:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def facebook_company_ads(self, **kw):
        self.calls.append({"credits_used": 1})
        return self.rows, {}


@pytest.fixture
def sc_reader(monkeypatch):
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "test-key")
    monkeypatch.setattr("cie.scrapecreators_client._load_dotenv_if_needed", lambda *_: None)
    rows = [_sc_row(i, card_image=i % 2 == 0) for i in range(6)]
    monkeypatch.setattr(sc_client, "_client", lambda: _FakeClient(rows))
    return rows


def _brands_file(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text("name,page_id,country\nFeed Co,123456,US\n")
    return f


def test_category_run_saves_images_and_puts_them_on_the_board(sc_reader, net, tmp_path, capsys):
    routes, seen = net
    for i in range(6):
        if i != 5:  # one dead link: skipped quietly, counted
            routes[f"https://cdn/{i}.jpg"] = _Resp(str(i), _jpeg())
    out = tmp_path / "run"
    args = ["category", "--brands-file", str(_brands_file(tmp_path)), "--out", str(out)]
    assert cli.main([*args, "--yes"]) == 0
    text = capsys.readouterr().out
    assert "Saved 5 ad images, 1 wouldn't download" in text
    media = sorted(p.name for p in (out / "brands").glob("*/media/*"))
    assert media == [f"77{i}.jpg" for i in range(5)]
    raw = json.loads(next((out / "brands").glob("*/ads.raw.json")).read_text())
    assert "cdn/" not in json.dumps(raw)  # expiring links are never stored
    assert len(seen) == 6  # one fetch per ad image, nothing else
    html = (out / "board.html").read_text()
    assert html.count('<img class="t ') == 3  # 5 pictures, the board shows 3 per brand
    # Redrawing later reads the saved images, with no network at all.
    seen.clear()
    assert cli.main(["category", "--from", str(out), "--out", str(tmp_path / "again")]) == 0
    assert seen == []
    assert (tmp_path / "again" / "board.html").read_text().count('<img class="t ') == 3


def test_no_images_skips_every_download(sc_reader, net, tmp_path, capsys):
    _, seen = net
    out = tmp_path / "run"
    args = ["category", "--brands-file", str(_brands_file(tmp_path)), "--out", str(out)]
    assert cli.main([*args, "--yes", "--no-images"]) == 0
    assert seen == [] and not list((out / "brands").glob("*/media"))
    assert "Saved" not in capsys.readouterr().out


def test_single_brand_pull_reports_images(sc_reader, net, tmp_path, capsys):
    routes, _ = net
    for i in range(6):
        routes[f"https://cdn/{i}.jpg"] = _Resp(str(i), _jpeg())
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "competitor.json").write_text(
        json.dumps({"page_id": "123456", "page_name": "Feed Co", "country": "US"})
    )
    assert cli.main(["pull", str(run_dir), "--yes"]) == 0
    assert "6 images saved" in capsys.readouterr().out
    assert len(list((run_dir / "media").iterdir())) == 6


# ---- the pattern line ------------------------------------------------------------------


def _ev(brand, text, catalog=False):
    return {"brand": brand, "catalog": catalog, "leads": category.lead_kinds(text)}


def test_pattern_line_names_the_shared_lead_and_the_gap():
    events = [
        _ev("Boll & Branch", "50K+ 5 Star Reviews"),
        _ev("Quince", "1,000,000+ 5-star reviews can't be wrong.."),
        _ev("BarkBox", "Get Toys, Treats, And A FREE Bed"),
        _ev("Fabletics", "NEW COZY DROP"),
    ]
    assert category.pattern_lines({"events": events}) == [
        "2 brands lead with a giant review count: Boll & Branch and Quince. "
        "None lead with a single real review."
    ]


def test_pattern_line_only_says_none_when_it_is_true():
    events = [
        _ev("A", "50K+ 5 Star Reviews"),
        _ev("B", "10,000 happy customers"),
        _ev("C", "“I finally slept through the night.” Sarah K."),
    ]
    assert category.pattern_lines({"events": events}) == [
        "2 brands lead with a giant review count: A and B."
    ]


def test_no_pattern_means_no_line():
    events = [_ev("A", "New drop"), _ev("B", "50K+ 5 Star Reviews"), _ev("C", "Shop now")]
    assert category.pattern_lines({"events": events}) == []
    # Catalog templates never count, even when their text would match.
    events += [_ev("D", "100K+ reviews", catalog=True), _ev("E", "1M+ reviews", catalog=True)]
    assert category.pattern_lines({"events": events}) == []


def test_board_has_no_black_friday_count(tmp_path, capsys):
    root = tmp_path / "s"
    for i, (name, head) in enumerate(
        [
            ("One", "Black Friday: up to 50% off"),
            ("Two", "50K+ 5 Star Reviews"),
            ("Three", "2M+ five-star reviews"),
        ]
    ):
        d = root / "brands" / category.slug(name)
        d.mkdir(parents=True)
        ad = {"ad_id": f"90{i}", "headline": head, "days_live": 40 + i, "is_active": True}
        raw = {"pulled_at": "2026-11-03T12:00:00Z", "ads": [ad]}
        (d / "competitor.json").write_text(json.dumps({"page_name": name, "page_id": str(i)}))
        (d / "ads.raw.json").write_text(json.dumps(raw))
    out = tmp_path / "o"
    assert cli.main(["category", "--from", str(root), "--out", str(out)]) == 0
    html = (out / "board.html").read_text()
    printed = capsys.readouterr().out + (out / "summary.md").read_text()
    for text in (html.split("<body>")[1], printed):
        assert "say Black Friday" not in text and "up to X% off" not in text
    assert "2 brands lead with a giant review count: Three and Two." in html
    assert "None lead with a single real review." in html
