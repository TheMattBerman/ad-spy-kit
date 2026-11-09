# ruff: noqa: E501  (embedded HTML/CSS/JS template)
"""Render the 'steal the whole niche' X demo from a real category run (silent 16:9 MP4).

    uv run python scripts/demo/record_bfcm_demo.py /workspace/bfcm-run/skincare \
        --out /workspace/ad-spy-kit-bfcm-demo.mp4

Reads category.json written by bfcm_category_run.py: every number on screen comes from that
run (ads, brands, bangers, wall-clock seconds, dollars from the credit-balance delta). Frames
are drawn in headless Chromium (Playwright) and piped to ffmpeg. No ad IDs, no scores.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

FPS = 30
DURATION = 29.0
W, H = 1920, 1080
ACCENT = "#2fff89"
PROMPT = "/ad-spy-kit steal black friday skincare"
INSTALL = "npx skills add TheMattBerman/ad-spy-kit"
COLS, ROWS = 8, 4
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0000fe0f\U0000200d\U00002b00-\U00002bff]+"
)


def clean(text: str, limit: int = 70) -> str:
    text = re.sub(r"\s+", " ", EMOJI.sub("", text or "")).strip(" -|·")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def pick_cards(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Up to COLS*ROWS cards with creative, spread across every brand, grouped by brand."""
    order = {"banger": 0, "solid": 1, "testing": 2}
    per_brand: dict[str, list[dict[str, Any]]] = {}
    for ad in run["events"]:
        if ad.get("image") and clean(ad["hook"]):
            per_brand.setdefault(ad["brand"], []).append(ad)
    for ads in per_brand.values():
        ads.sort(key=lambda a: (order[a["band"]], -a["versions"], -a["days_live"]))
    cards: list[dict[str, Any]] = []
    depth = 0
    while len(cards) < COLS * ROWS and any(len(v) > depth for v in per_brand.values()):
        for ads in per_brand.values():
            if len(ads) > depth and len(cards) < COLS * ROWS:
                cards.append(ads[depth])
        depth += 1
    # Show all three labels: swap testing ads in for the deepest picks if none made the cut.
    testing = [a for ads in per_brand.values() for a in ads if a["band"] == "testing"]
    for ad in testing[:2]:
        if ad in cards:
            continue
        counts = {b: sum(c["brand"] == b for c in cards) for b in per_brand}
        drop = next(c for c in reversed(cards) if counts[c["brand"]] > 1 and c["band"] != "testing")
        cards[cards.index(drop)] = ad
    brands = list(per_brand)
    cards.sort(key=lambda a: brands.index(a["brand"]))
    return cards


def build_page(run: dict[str, Any], cards: list[dict[str, Any]], hero_idx: int) -> str:
    s = run["summary"]
    top3 = run["top3"]
    hero = cards[hero_idx]
    card_html = "".join(
        f'<div class="card" id="c{i}"><img src="file://{html.escape(c["image"])}">'
        f'<div class="meta"><b>{html.escape(c["brand"])}</b>'
        f'<span class="band {c["band"]}">{c["band"]}</span>'
        f"<p>{html.escape(clean(c['hook'], 48))}</p></div></div>"
        for i, c in enumerate(cards)
    )
    top_html = "".join(
        f'<div class="top"><span class="n">{i}</span><div><b>{html.escape(a["brand"])}</b>'
        f"<p>“{html.escape(clean(a['hook'], 60))}”</p><i>{html.escape(a['why'])}</i></div></div>"
        for i, a in enumerate(top3, start=1)
    )
    flashes = [p.strip() for p in hero["why"].split("·")]
    data = {
        "ads": s["ads"],
        "brands": s["brands"],
        "seconds": s["seconds"],
        "usd": s["usd"],
        "n": len(cards),
        "hero": hero_idx,
        "flashes": flashes,
        "prompt": PROMPT,
    }
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden}}
body{{background:#0b0b0c;color:#f4f4f4;font-family:Inter,sans-serif}}
#bar{{position:absolute;left:0;top:0;width:100%;height:96px;display:flex;align-items:center;
 justify-content:space-between;padding:0 48px;border-bottom:1px solid #222;background:#0b0b0c;z-index:20}}
#title{{font-size:40px;font-weight:800;letter-spacing:-.02em}} #title em{{color:{ACCENT};font-style:normal}}
#counters{{display:flex;gap:44px}} .ctr{{text-align:right}}
.ctr b{{display:block;font-size:40px;font-weight:800;font-variant-numeric:tabular-nums}}
.ctr span{{font-size:14px;letter-spacing:.14em;text-transform:uppercase;color:#8a8a8a}}
#speed{{position:absolute;right:48px;top:108px;font-size:16px;color:#8a8a8a;letter-spacing:.1em;z-index:20}}
#stage{{position:absolute;left:0;top:96px;width:100%;height:{H - 96}px;overflow:hidden}}
#grid{{position:absolute;left:40px;top:24px;width:{W - 80}px;display:grid;
 grid-template-columns:repeat({COLS},1fr);gap:14px;transform-origin:0 0}}
.card{{background:#161618;border:1px solid #262628;border-radius:10px;overflow:hidden;height:214px;opacity:0}}
.card img{{width:100%;height:150px;object-fit:cover;display:block}}
.meta{{padding:8px 10px;font-size:13px;line-height:1.25}}
.meta b{{font-size:13px;display:inline-block;max-width:62%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}}
.meta p{{margin:4px 0 0;color:#cfcfcf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.band{{float:right;font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
 color:#9a9a9a;display:inline-block}}
.band.banger{{color:#0b0b0c;background:{ACCENT};padding:1px 6px;border-radius:4px}}
#prompt{{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:1240px;
 background:#141416;border:1px solid #2a2a2c;border-radius:16px;padding:44px 52px;z-index:15}}
#prompt .who{{font-size:18px;color:#8a8a8a;letter-spacing:.12em;text-transform:uppercase;margin-bottom:18px}}
#typed{{font-family:'DejaVu Sans Mono',monospace;font-size:44px}} #caret{{color:{ACCENT}}}
#cap{{position:absolute;left:50%;bottom:54px;transform:translateX(-50%);z-index:18;font-size:54px;
 font-weight:800;letter-spacing:-.02em;background:rgba(11,11,12,.92);padding:14px 34px;border-radius:14px;
 white-space:nowrap;opacity:0}}
#dim{{position:absolute;inset:96px 0 0 0;background:#0b0b0c;opacity:0;z-index:16}}
#flash{{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);text-align:center;z-index:17;
 font-size:150px;font-weight:900;letter-spacing:-.04em;color:{ACCENT};opacity:0}}
#flashsub{{position:absolute;left:0;right:0;top:calc(50% + 120px);text-align:center;z-index:17;font-size:30px;
 color:#bdbdbd;opacity:0}}
#side{{position:absolute;left:1010px;top:300px;width:840px;z-index:17;opacity:0}}
#side .lbl{{display:inline-block;background:{ACCENT};color:#0b0b0c;font-weight:900;font-size:30px;
 letter-spacing:.1em;padding:6px 16px;border-radius:8px}}
#side h2{{font-size:62px;line-height:1.08;margin:26px 0 22px;letter-spacing:-.02em}}
#side .why{{font-size:40px;color:{ACCENT};font-weight:700}} #side .brand{{font-size:28px;color:#9a9a9a;margin-top:18px}}
#end{{position:absolute;inset:0;background:#0b0b0c;z-index:30;opacity:0;padding:170px 110px 0}}
#end h1{{font-size:84px;font-weight:900;letter-spacing:-.04em;margin:0}} #end h1 em{{color:{ACCENT};font-style:normal}}
#tops{{display:flex;gap:28px;margin-top:64px}}
.top{{flex:1;display:flex;gap:18px;background:#141416;border:1px solid #262628;border-radius:14px;padding:30px}}
.top .n{{font-size:60px;font-weight:900;color:{ACCENT};line-height:1}} .top b{{font-size:30px}}
.top p{{font-size:28px;line-height:1.25;margin:12px 0;color:#dcdcdc}} .top i{{font-style:normal;color:{ACCENT};font-size:22px}}
#install{{margin-top:80px;font-family:'DejaVu Sans Mono',monospace;font-size:46px;background:#141416;
 border:1px solid {ACCENT};border-radius:14px;padding:26px 36px;display:inline-block}}
#install span{{color:{ACCENT}}}
#foot{{position:absolute;left:110px;bottom:44px;font-size:20px;color:#6f6f6f}}
</style></head><body>
<div id="bar"><div id="title">steal the whole <em>niche</em></div><div id="counters">
<div class="ctr"><b id="k_ads">0</b><span>ads pulled</span></div>
<div class="ctr"><b id="k_brands">0</b><span>brands</span></div>
<div class="ctr"><b id="k_sec">0s</b><span>seconds</span></div>
<div class="ctr"><b id="k_usd">$0.00</b><span>cost</span></div></div></div>
<div id="speed"></div>
<div id="stage"><div id="grid">{card_html}</div></div>
<div id="prompt"><div class="who">Claude Code</div><div id="typed"><span id="tx"></span><span id="caret">▍</span></div></div>
<div id="dim"></div><div id="flash"></div><div id="flashsub"></div>
<div id="side"><span class="lbl">BANGER</span><h2>“{html.escape(clean(hero["hook"], 60))}”</h2>
<div class="why">{html.escape(hero["why"])}</div><div class="brand">{html.escape(hero["brand"])}</div></div>
<div id="cap"></div>
<div id="end"><h1>{s["ads"]} ads. {s["brands"]} brands. <em>{s["bangers"]} bangers.</em>
{round(s["seconds"])}s. ${s["usd"]:.2f}.</h1><div id="tops">{top_html}</div>
<div id="install"><span>$</span> {INSTALL}</div>
<div id="foot">pulled {html.escape(run["pulled_date"])} · stealads.ai</div></div>
<script>
const D={json.dumps(data)};
const $=id=>document.getElementById(id);
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const ease=x=>1-Math.pow(1-clamp(x),3);
const win=(t,a,b,f=.2)=>clamp((t-a)/f)*clamp((b-t)/f);
const CAPS=[[2.3,6.0,"pulling every live ad"],[6.0,9.6,"{s["brands"]} brands at once"],
 [9.6,12.8,"every ad gets labeled"],[16.9,20.0,"banger. solid. testing."],[21.6,26.0,"steal the reason why"]];
window.setT=function(t){{
  // prompt 0-2s
  const typed=Math.floor(clamp(t/1.55)*D.prompt.length);
  $('tx').textContent=D.prompt.slice(0,typed);
  $('caret').style.opacity=(Math.floor(t*4)%2||t<1.6)?1:0;
  $('prompt').style.opacity=1-clamp((t-1.75)/.25);
  // board fill 2-18.5s, counters 2-20s
  const p=clamp((t-2)/18);
  const fill=clamp((t-2)/16.5);
  for(let i=0;i<D.n;i++){{
    const at=i/D.n, local=clamp((fill-at)*D.n/1.6);
    const c=$('c'+i); c.style.opacity=ease(local*2);
    c.style.transform=`scale(${{.82+.18*ease(local*1.6)}})`;
    const b=c.querySelector('.band'); const bl=clamp(local*2.2-.9);
    b.style.opacity=bl; b.style.transform=`scale(${{bl<1?.6+.6*Math.sin(bl*Math.PI/2)-.2*bl:1}})`;
  }}
  $('k_ads').textContent=Math.round(D.ads*p);
  $('k_brands').textContent=Math.min(D.brands,Math.ceil(D.brands*p-1e-9));
  $('k_sec').textContent=Math.round(D.seconds*p)+'s';
  $('k_usd').textContent='$'+(D.usd*p).toFixed(2);
  $('speed').textContent=(t>2&&t<20)?'▶▶ '+Math.round(D.seconds/18)+'x speed':'';
  // reason line flashes big 13-16.6s
  const fl=[[13.0,14.2],[14.2,15.4],[15.4,16.6]];
  let fo=0,txt='';
  fl.forEach(([a,b],k)=>{{ if(t>=a&&t<b&&D.flashes[k]){{fo=win(t,a,b,.12);txt=D.flashes[k];}} }});
  $('flash').textContent=txt; $('flash').style.opacity=fo;
  $('flash').style.transform=`translateY(-50%) scale(${{.92+.08*fo}})`;
  const fz=win(t,12.9,16.7,.2);
  $('flashsub').textContent='why the #1 banger wins'; $('flashsub').style.opacity=fz;
  // zoom 20-26s
  const z=ease((t-20)/1.4);
  const card=$('c'+D.hero), g=$('grid');
  const cx=card.offsetLeft+card.offsetWidth/2, cy=card.offsetTop+card.offsetHeight/2;
  const S=1+2.1*z, tx=480-cx*S, ty=(984/2)-cy*S;
  g.style.transform=z>0?`translate(${{40+(tx-40)*z}}px,${{24+(ty-24)*z}}px) scale(${{S}})`:'none';
  g.style.left=z>0?'0px':'40px'; g.style.top=z>0?'0px':'24px';
  for(let i=0;i<D.n;i++){{ if(i!==D.hero&&z>0) $('c'+i).style.opacity=Math.min($('c'+i).style.opacity,1-z); }}
  $('side').style.opacity=clamp((t-21.1)/.4)*(1-clamp((t-25.8)/.2));
  $('dim').style.opacity=Math.max(.72*fz,0);
  // captions
  let co=0,ct='';
  CAPS.forEach(([a,b,s])=>{{ if(t>=a&&t<b){{co=win(t,a,b,.15);ct=s;}} }});
  $('cap').textContent=ct; $('cap').style.opacity=co;
  // end card 26-29s
  $('end').style.opacity=clamp((t-26)/.35);
}};
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("/workspace/ad-spy-kit-bfcm-demo.mp4"))
    ap.add_argument("--frames", type=int, default=0, help="debug: render only this many frames")
    args = ap.parse_args()
    run = json.loads((args.run_dir / "category.json").read_text())
    cards = pick_cards(run)
    top1 = run["top3"][0]
    hero_idx = next(
        (
            i
            for i, c in enumerate(cards)
            if c["hook"] == top1["hook"] and c["brand"] == top1["brand"]
        ),
        None,
    )
    if hero_idx is None:  # make sure the #1 banger is on the board for the zoom
        cards[-1] = top1
        hero_idx = len(cards) - 1
        cards.sort(key=lambda a: [c["brand"] for c in cards].index(a["brand"]))
        hero_idx = cards.index(top1)
    page_html = build_page(run, cards, hero_idx)
    visible = re.sub(r"<script.*?</script>|<[^>]+>", " ", page_html, flags=re.S)
    assert not re.search(r"\b\d{12,}\b", visible), "ad ID in the video"
    assert "score" not in visible.lower(), "score in the video"
    html_path = args.run_dir / "demo.html"
    html_path.write_text(page_html)

    from playwright.sync_api import sync_playwright

    total = args.frames or math.floor(DURATION * FPS)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
         "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-preset", "medium", "-movflags", "+faststart", str(args.out)],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        for f in range(total):
            page.evaluate(f"setT({f / FPS})")
            ff.stdin.write(page.screenshot(type="jpeg", quality=92))
        browser.close()
    ff.stdin.close()
    ff.wait()
    print(f"{args.out} · {total} frames · {total / FPS:.1f}s")
    return ff.returncode


if __name__ == "__main__":
    raise SystemExit(main())
