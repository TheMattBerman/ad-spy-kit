# ruff: noqa: E501  (embedded HTML/CSS/JS template)
"""Render the v3 'steal your competitors' best ads' demo from bfcm_archive_run.py output.

    uv run python scripts/demo/record_v3_demo.py /workspace/bfcm-run/archive \
        --out /workspace/ad-spy-kit-v3-demo.mp4

Same beats as record_v2_demo.py. Every number and caption comes from category.json. Every
ad in the run is a tile (dense wall); ads with no local image get a plain text tile (no
fabricated media). Ads with images are placed first so the zoomed fill shows real creative.
The sort beat orders by days run and highlights ads that ran 30+ days. No ad IDs, no
scores, no hedges.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import random
import re
import subprocess
from pathlib import Path
from typing import Any

W, H, FPS, DURATION = 1920, 1080, 30, 25.0
COLS = 90
KEEP_DAYS = 30
EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]")
BAND_ORDER = {"banger": 0, "solid": 1, "testing": 2}


def clean(text: str, limit: int = 80) -> str:
    t = re.sub(r"\s+", " ", EMOJI.sub("", text or "")).strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def short(brand: str) -> str:
    return re.sub(r" (Skincare|Skin|Global|US\.official)$", "", brand)


def build_page(run: dict[str, Any]) -> str:
    s = run["summary"]
    ev = run["events"]
    top3 = run["top3"]
    ev = sorted(ev, key=lambda e: (not e.get("image"), random.Random(e["ad_id"]).random()))
    rnd = random.Random(29)
    fill_rank = list(range(len(ev)))
    rnd.shuffle(fill_rank)
    sorted_idx = sorted(
        range(len(ev)),
        key=lambda i: (
            -int(ev[i]["days_live"] or 0),
            -int(ev[i]["versions"] or 0),
            BAND_ORDER[ev[i]["band"]],
            i,
        ),
    )
    sort_pos = [0] * len(ev)
    for p, i in enumerate(sorted_idx):
        sort_pos[i] = p

    def find(t: dict[str, Any]) -> int:
        return next(i for i, e in enumerate(ev) if e["ad_id"] == t["ad_id"])

    hero = [find(t) for t in top3]
    tiles = []
    for i, e in enumerate(ev):
        img = Path(e["image"]) if e.get("image") else None
        inner = (
            f'<img src="{img.resolve().as_uri()}">'
            if img and img.exists()
            else f'<div class="txt"><b>{html.escape(short(e["brand"]))}</b>{html.escape(clean(e["hook"], 40))}</div>'
        )
        tiles.append(
            f'<div class="tile" id="t{i}">{inner}<span class="pill {e["band"]}">{e["band"]}</span></div>'
        )
    cards = []
    for k, t in enumerate(top3):
        cards.append(
            f'<div class="card" id="card{k}"><div class="cimg"><img src="{Path(t["image"]).resolve().as_uri()}"></div>'
            f'<div class="cbody"><div class="cbrand">{html.escape(t["brand"])}</div>'
            f'<span class="cpill {t["band"]}">{t["band"]}</span>'
            f'<div class="chook">“{html.escape(clean(t["hook"], 90))}”</div>'
            f'<div class="cwhy">{html.escape(t["why"])}</div></div></div>'
        )
    brands = [short(b["name"]) for b in run["brands"]]
    named = [
        b
        for b in ("Skims", "Glossier", "Charlotte Tilbury", "Alo Yoga", "Brooklinen", "Anker")
        if b in brands
    ]
    prompt = (
        "/ad-spy-kit steal the best ads from "
        + ", ".join(named)
        + f" + {len(brands) - len(named)} more brands"
    )
    keep = sum(int(e["days_live"] or 0) >= KEEP_DAYS for e in ev)
    h0 = top3[0]
    cap_hero = f"{h0['days_live']} days. " + (
        "still running." if h0.get("is_active") else f"{h0['versions']} versions."
    )
    cap_keep = f"the {keep:,} they kept running {KEEP_DAYS}+ days."
    usd = float(s["usd"])
    cents = round(usd * 100)
    data = {
        "n": len(ev),
        "brands": int(s["brands"]),
        "sec": float(s["seconds"]),
        "usd": usd,
        "fill": fill_rank,
        "sortPos": sort_pos,
        "hero": hero,
        "prompt": prompt,
        "bands": [e["band"] for e in ev],
        "keep": [int(e["days_live"] or 0) >= KEEP_DAYS for e in ev],
        "capHero": cap_hero,
        "capKeep": cap_keep,
        "capCost": "$0. data already pulled." if cents == 0 else "",
    }
    stats1 = f"{s['ads']:,} ads. {s['brands']} brands."
    secs = float(s["seconds"])
    stats2 = (
        (f"{secs:.1f}" if secs < 10 else f"{round(secs)}")
        + " seconds. "
        + ("$0." if cents == 0 else f"{cents} cents.")
    )
    tops = "".join(
        f'<div class="t3"><b>{html.escape(short(t["brand"]))}</b> {html.escape(t["why"])}</div>'
        for t in top3
    )
    foot = f"pulled {html.escape(run['pulled_date'])} · stealads.ai"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{W}px;height:{H}px;overflow:hidden;background:#000;font-family:Inter,sans-serif}}
#root{{position:absolute;inset:0;background:#e7e7e3;transform-origin:0 0}}
#bar{{position:absolute;left:0;top:0;width:{W}px;height:110px;background:#fff;border-bottom:3px solid #000;display:flex;align-items:center;padding:0 40px}}
#bar h1{{font-size:52px;font-weight:900;letter-spacing:-1.5px;color:#000}}
#ctr{{position:absolute;right:30px;top:12px;display:flex;gap:10px;transform-origin:100% 0;z-index:30}}
.c{{background:#fff;border:3px solid #000;border-radius:14px;padding:4px 16px 6px;min-width:120px;text-align:center}}
.c b{{display:block;font-size:44px;font-weight:900;line-height:1.05;font-variant-numeric:tabular-nums;color:#000}}
.c i{{font-style:normal;font-size:15px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:1px}}
.c.cost{{background:#2bff88}}
.win{{position:absolute;left:30px;top:132px;width:1860px;height:928px;border-radius:14px;overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.28)}}
.chrome{{height:50px;display:flex;align-items:center;padding:0 18px;gap:9px;font-size:18px}}
.dot{{width:15px;height:15px;border-radius:50%}}
#browser .chrome{{background:#ececec;border-bottom:1px solid #ccc;color:#333}}
.url{{margin-left:30px;background:#fff;border-radius:8px;padding:6px 16px;width:900px;font-size:17px;color:#444}}
#vp{{position:absolute;left:0;top:50px;width:1860px;height:878px;background:#fff;overflow:hidden}}
#grid{{position:absolute;left:1px;top:0;width:1860px;height:840px;transform-origin:0 0}}
.tile{{position:absolute;width:19.4px;height:22px;background:#f1f1ef;overflow:hidden;border-radius:3px}}
.tile img{{width:100%;height:100%;object-fit:cover;display:block}}
.txt{{padding:1px;font-size:2.2px;line-height:1.15;color:#333;height:100%;overflow:hidden;border:.4px solid #ddd}}
.txt b{{display:block;font-size:2.6px;color:#000}}
.pill{{position:absolute;left:.7px;bottom:.7px;font-size:3.3px;font-weight:900;padding:.3px 1.3px;border-radius:1.6px;opacity:0;transform:scale(.3);transform-origin:0 100%}}
.banger{{background:#2bff88;color:#000}} .solid{{background:#000;color:#fff}} .testing{{background:#fff;color:#666;border:.4px solid #999}}
.tile.hl{{outline:1.2px solid #00c853;outline-offset:-1.2px}}
#foot{{position:absolute;left:0;bottom:8px;width:100%;text-align:center;font-size:20px;color:#666;font-weight:600}}
#tag{{position:absolute;left:24px;top:20px;background:#000;color:#fff;font-weight:800;font-size:24px;padding:6px 14px;border-radius:8px;z-index:20;display:none}}
.card{{position:absolute;inset:0;background:#fff;display:none;padding:40px;gap:50px}}
.cimg{{width:790px;height:798px;background:#f3f3f3;border-radius:14px;overflow:hidden;flex:none}}
.cimg img{{width:100%;height:100%;object-fit:cover}}
.cbody{{display:flex;flex-direction:column;justify-content:center;gap:28px;padding-right:30px}}
.cbrand{{font-size:46px;font-weight:800;color:#000}}
.cpill{{align-self:flex-start;font-size:44px;font-weight:900;padding:6px 22px;border-radius:14px}}
.chook{{font-size:50px;font-weight:700;line-height:1.15;color:#111}}
.cwhy{{font-size:42px;font-weight:800;color:#007a3d}}
#zoom{{position:absolute;background:#fff;display:none;overflow:hidden;z-index:15}}
#zoom img{{width:100%;height:100%;object-fit:cover}}
#term{{background:#141414;display:none}}
#term .chrome{{background:#2a2a2a;color:#bbb;justify-content:flex-start}}
#term .title{{margin-left:auto;margin-right:auto;font-family:Inter;font-size:18px}}
#tbody{{padding:40px 60px;font-family:'DejaVu Sans Mono',monospace;color:#e8e8e8;font-size:30px}}
.wel{{border:2px solid #D97757;border-radius:12px;padding:18px 26px;width:860px;line-height:1.6;font-size:24px}}
.wel .o{{color:#D97757}} .dim{{color:#8a8a8a}}
#inbox{{margin-top:40px;border:2px solid #777;border-radius:12px;padding:22px 26px;width:1140px;font-size:40px;line-height:1.35;min-height:150px}}
#inbox .o{{color:#D97757}}
.caret{{display:inline-block;width:22px;height:42px;background:#e8e8e8;vertical-align:-7px}}
#hint{{margin:12px 0 0 28px;font-size:22px;color:#8a8a8a}}
#run{{margin-top:26px;font-size:30px;line-height:1.6;display:none}}
#cap{{position:absolute;left:50%;bottom:60px;transform:translateX(-50%);background:#000;color:#fff;font-size:78px;font-weight:900;letter-spacing:-2px;padding:10px 40px 16px;border-radius:22px;white-space:nowrap;display:none;z-index:40}}
#mouse{{position:absolute;z-index:45;display:none;width:34px}}
#end{{position:absolute;inset:0;background:#fff;display:none;z-index:50;flex-direction:column;align-items:center;justify-content:center;gap:24px}}
#end .big{{font-size:132px;font-weight:900;letter-spacing:-4px;line-height:1.0;color:#000;text-align:center}}
#end .cmd{{margin-top:34px;background:#000;color:#2bff88;font-family:'DejaVu Sans Mono',monospace;font-size:62px;font-weight:700;padding:22px 44px;border-radius:20px}}
#end .tops{{display:flex;gap:40px;margin-top:20px;font-size:26px;color:#333}}
#end .ft{{position:absolute;bottom:26px;font-size:22px;color:#666;font-weight:600}}
#black{{position:absolute;inset:0;background:#000;display:none;z-index:99}}
</style></head><body><div id="root">
<div id="bar"><h1>steal your competitors' best ads</h1></div>
<div id="ctr"><div class="c"><b id="cA">0</b><i>ads</i></div><div class="c"><b id="cB">0</b><i>brands</i></div><div class="c"><b id="cS">0</b><i>sec</i></div><div class="c cost" id="cost"><b id="cD">$0.00</b><i>$ spent</i></div></div>
<div class="win" id="browser"><div class="chrome"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span><span class="url">file://~/ads/board.html</span></div>
<div id="vp"><div id="tag">▶▶ sped up</div><div id="grid">{"".join(tiles)}</div><div id="foot">{foot}</div><div id="zoom"><img id="zimg"></div>{"".join(cards)}</div></div>
<div class="win" id="term"><div class="chrome"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span><span class="dot" style="background:#28c840"></span><span class="title">claude — ~/ads — 160×48</span></div>
<div id="tbody"><div class="wel"><span class="o">✻</span> Welcome to <b>Claude Code</b>!<br><br><span class="dim">&nbsp;&nbsp;/help for help, /status for your current setup<br><br>&nbsp;&nbsp;cwd: ~/ads</span></div>
<div id="inbox"><span class="o">&gt;</span> <span id="typed"></span><span class="caret" id="caret"></span></div><div id="hint">? for shortcuts</div>
<div id="run"><span style="color:#2bff88">⏺</span> Skill(<b>ad-spy-kit</b>)<br><span class="o" style="color:#D97757">✻ Stealing… <span class="dim">(esc to interrupt)</span></span></div></div></div>
<svg id="mouse" viewBox="0 0 24 34"><path d="M1 1 L1 27 L8 20 L13 32 L17 30 L12 18 L22 18 Z" fill="#000" stroke="#fff" stroke-width="2"/></svg>
<div id="end"><div class="big" id="s1">{stats1}<br>{stats2}</div><div class="cmd">npx skills add TheMattBerman/ad-spy-kit</div><div class="tops">{tops}</div><div class="ft">{foot}</div></div>
</div><div id="cap"></div><div id="black"></div>
<script>
const D={json.dumps(data)};
const $=id=>document.getElementById(id);
const tiles=[...Array(D.n).keys()].map(i=>$('t'+i));
const pills=tiles.map(t=>t.querySelector('.pill'));
const VW=1860,VH=878,TW=20.6,TH=23,W={W},H={H};
const pos=p=>[(p%{COLS})*TW,10+Math.floor(p/{COLS})*TH];
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const ease=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;
const lerp=(a,b,k)=>a+(b-a)*k;
function show(id,on,disp='block'){{$(id).style.display=on?disp:'none'}}
function view(s,x0,y0){{$('grid').style.transform=`translate(${{-x0*s}}px,${{-y0*s}}px) scale(${{s}})`}}
function counters(k,kc){{  // k: fill progress 0..1, kc: cost progress 0..1
  $('cA').textContent=Math.round(D.n*k); $('cB').textContent=Math.ceil(D.brands*k);
  $('cS').textContent=(D.sec<10?(D.sec*k).toFixed(1):Math.round(D.sec*k)); $('cA').textContent=Math.round(D.n*k).toLocaleString('en-US'); $('cD').textContent='$'+(D.usd*kc).toFixed(2);
}}
function setT(t){{
  const tj=Math.floor(t*6)/6;  // jump cuts: 5-frame holds
  show('term',t>=1.5&&t<3.5); show('browser',!(t>=1.5&&t<3.5));
  show('tag',t>=3.5&&t<8.5); show('end',t>=22.5,'flex'); show('black',t>=24.75);
  for(let k=0;k<3;k++) $('card'+k).style.display='none';
  show('zoom',false); show('mouse',false);
  $('root').style.transform=''; $('ctr').style.transform='';
  // board positions (sort beat moves tiles)
  const ks=clamp((t-19.7)/1.3);
  for(let i=0;i<D.n;i++){{
    const a=pos(i),b=pos(D.sortPos[i]),e=ease(clamp(ks*1.15-(i%{COLS})/{COLS}*0.15));
    tiles[i].style.left=lerp(a[0],b[0],e)+'px'; tiles[i].style.top=lerp(a[1],b[1],e)+'px';
    let vis=true;
    if(t>=3.5&&t<8.5) vis=D.fill[i]<D.n*clamp((tj-3.5)/5)*1.0001;
    tiles[i].style.visibility=vis?'visible':'hidden';
    // pills: on in beat 1, pop in waves from 8.5, stay on
    let pk=t<1.5?1:(t<8.5?0:clamp((t-8.5-((i%{COLS})+Math.floor(i/{COLS}))*0.016)/0.15));
    pills[i].style.opacity=pk; pills[i].style.transform=`scale(${{0.3+0.7*pk+(pk>0&&pk<1?0.4*Math.sin(pk*Math.PI):0)}})`;
    const kp=D.keep[i];
    tiles[i].classList.toggle('hl',t>=19.5&&t<22.5&&kp);
    tiles[i].style.opacity=(t>=20.2&&t<22.5&&!kp)?0.25:1;
  }}
  // camera
  if(t<1.5) view(4.2,lerp(0,40,t/1.5),0);
  else if(t<11) view(3,0,0);
  else if(t<13) {{const z=ease(clamp((t-11)/1.2)); view(lerp(3,1,z),0,0);}}
  else view(1,0,0);
  // counters
  if(t<1.5) counters(1,1);
  else if(t<3.5) counters(0,0);
  else if(t<8.5) counters(clamp((tj-3.5)/5),clamp((tj-3.5)/1.5));
  else counters(1,1);
  if(t>=3.5&&t<8.5) $('ctr').style.transform='scale(1.6)';
  if(t>=5&&t<6.5){{  // snap zoom onto the $ counter
    const z=clamp((t-5)/0.15), r=$('cost').getBoundingClientRect();
    const s=lerp(1,2.6,z), cx=r.left+r.width/2, cy=r.top+r.height/2;
    const tx=clamp(W/2-cx*s,W-W*s,0), ty=clamp(H/2-cy*s,H-H*s,0);
    $('root').style.transform=`translate(${{lerp(0,tx,z)}}px,${{lerp(0,ty,z)}}px) scale(${{s}})`;
  }}
  // terminal typing
  if(t>=1.5&&t<3.5){{
    const k=clamp((t-1.55)/1.45); $('typed').textContent=D.prompt.slice(0,Math.round(D.prompt.length*k));
    $('caret').style.visibility=(t>3.0||Math.floor(t*4)%2===0)?'visible':'hidden';
    show('run',t>=3.1);
  }}
  // mouse to the Megelin tile, click, snap zoom into its card
  const hp=pos(D.hero[0]);
  if(t>=12.3&&t<13){{const k=ease(clamp((t-12.3)/0.55)); show('mouse',true);
    $('mouse').style.left=lerp(1300,30+hp[0]+10,k)+'px'; $('mouse').style.top=lerp(900,132+50+hp[1]+11,k)+'px';}}
  if(t>=13&&t<13.2){{const k=ease((t-13)/0.2), z=$('zoom'); show('zoom',true);
    $('zimg').src=tiles[D.hero[0]].querySelector('img').src;
    z.style.left=lerp(hp[0],0,k)+'px'; z.style.top=lerp(hp[1],0,k)+'px'; z.style.width=lerp(19.4,VW,k)+'px'; z.style.height=lerp(22,VH,k)+'px';}}
  if(t>=13.2&&t<16.5) $('card0').style.display='flex';
  if(t>=16.5&&t<18) $('card1').style.display='flex';
  if(t>=18&&t<19.5) $('card2').style.display='flex';
  // captions
  let cap='';
  if(t>=8.7&&t<11) cap='banger. solid. testing.';
  if(t>=5.15&&t<6.5&&D.capCost) cap=D.capCost;
  if(t>=13.4&&t<16.5) cap=D.capHero;
  if(t>=20.4&&t<22.5) cap=D.capKeep;
  $('cap').textContent=cap; show('cap',!!cap);
  // end slam
  if(t>=22.5){{const k=clamp((t-22.5)/0.12); $('end').style.transform=`scale(${{lerp(1.25,1,k)}})`;}}
}}
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("/workspace/ad-spy-kit-v3-demo.mp4"))
    ap.add_argument("--frames", type=int, default=0, help="debug: render only this many frames")
    args = ap.parse_args()
    run = json.loads((args.run_dir / "category.json").read_text())
    s = run["summary"]
    assert (s["ads"], s["brands"], s["bangers"]) == (
        len(run["events"]),
        len(run["brands"]),
        sum(e["band"] == "banger" for e in run["events"]),
    ), "summary mismatch"
    page_html = build_page(run)
    visible = re.sub(r"<script.*?</script>|<[^>]+>", " ", page_html, flags=re.S)
    assert not re.search(r"\b\d{12,}\b", visible), "ad ID in the video"
    assert "score" not in visible.lower(), "score in the video"
    assert not re.search(r"\b(may|might|could|likely|probably|seems)\b", visible.lower()), (
        "hedge copy"
    )
    d = json.loads(re.search(r"const D=(.*?);\n", page_html).group(1))
    caps = " ".join(d[k] for k in ("capHero", "capKeep", "capCost", "prompt"))
    assert not re.search(r"that actually work|every live ad|\bwon\b|\bwinners?\b", caps.lower()), (
        "banned copy"
    )
    html_path = args.run_dir / "demo_v3.html"
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
