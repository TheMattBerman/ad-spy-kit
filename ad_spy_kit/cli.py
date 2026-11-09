"""ad-spy-kit CLI. The agent skills call these; every step also runs by hand.

Live data inside an agent comes from the StealAds MCP (the agent calls the MCP tools and
writes the JSON contracts). From a plain shell, `resolve` and `pull` use the ScrapeCreators
fallback. Analysis is the agent's job (vision + copy); the CLI validates and renders it.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

from ad_spy_kit.errors import KitError
from ad_spy_kit.pipeline import GateFailed, gate, replay_all_fixtures, replay_fixture, repo_root
from ad_spy_kit.validate_run import COUNTERS_FIX

NEWEST_HELP = "read their newest live ads instead of the ones live 30+ days (the default)"
EXIT_GATE = 1
EXIT_USER = 2
DEFAULT_PULLED_AT = "2026-10-28T12:00:00Z"  # sc_client.build_ads_raw_from_fixture default


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "competitor"


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {path}")


def _rerun(*argv: str) -> str:
    return shlex.join(["ad-spy-kit", *argv, "--yes"])


def _resolve(query: str, country: str, out: Path | None, *, yes: bool) -> tuple[int, Path | None]:
    from ad_spy_kit.sc_client import page_id_from_query, require_key, resolve_via_scrapecreators
    from ad_spy_kit.spend import confirm

    if not page_id_from_query(query):  # a page ID or page link costs nothing to resolve
        require_key()
        quote = f"Finding the Facebook page for {query} costs 1 ScrapeCreators credit."
        country_arg = ["--country", country] if country and country != "US" else []
        if not confirm(quote, yes=yes, rerun=_rerun("resolve", query, *country_arg)):
            return 0, None
    comp = resolve_via_scrapecreators(query, country=country)
    run_dir = out or repo_root() / "runs" / _slug(comp["page_name"])
    _write(run_dir / "competitor.json", comp)
    if comp["confidence"] == "ambiguous":
        print(f"More than one Facebook page matches '{query}'. Which one is it?")
        for alt in [comp, *comp["alternates"]][:3]:
            print(f"  {alt['page_id']}  {alt['page_name']}")
        print("Run it again with the right page ID, e.g. ad-spy-kit run <page ID>")
        return EXIT_USER, run_dir
    return 0, run_dir


def cmd_resolve(args: argparse.Namespace) -> int:
    return _resolve(args.query, args.country, args.out, yes=args.yes)[0]


def cmd_pull(args: argparse.Namespace) -> int:
    from ad_spy_kit.sc_client import pull_via_scrapecreators, require_key
    from ad_spy_kit.spend import brand_quote, confirm

    comp_path = args.run_dir / "competitor.json"
    comp = json.loads(comp_path.read_text())
    require_key()
    newest = getattr(args, "newest", False)
    min_days = getattr(args, "min_days", None)
    quote = brand_quote(
        comp.get("page_name") or "this brand",
        max_ads=args.max_ads,
        find_page=False,
        newest=newest,
        min_days=min_days,
    )
    rerun = _rerun(
        "pull",
        str(args.run_dir),
        "--max-ads",
        str(args.max_ads),
        *(["--newest"] if newest else []),
        *(["--min-days", str(min_days)] if min_days else []),
        *(["--keep-originals"] if getattr(args, "keep_originals", False) else []),
    )
    if not getattr(args, "quoted", False) and not confirm(quote[0], yes=args.yes, rerun=rerun):
        return 0
    ads_raw = pull_via_scrapecreators(
        comp,
        country=comp.get("country", "US"),
        max_ads=args.max_ads,
        media_dir=None if getattr(args, "no_images", False) else args.run_dir / "media",
        newest=newest,
        min_days=min_days,
        keep_originals=getattr(args, "keep_originals", False),
    )
    _write(comp_path, comp)  # the read may fill in the page name
    _write(args.run_dir / "ads.raw.json", ads_raw)
    from ad_spy_kit.sc_client import image_counts

    if getattr(args, "no_images", False):
        pics = "images not saved (--no-images)"
    else:
        n = image_counts(ads_raw["ads"], ads_raw["skipped"])
        pics = f"{n['saved']} images saved"
        if n["failed"]:
            pics += f", {n['failed']} wouldn't download"
        if n["none"]:
            pics += f", {n['none']} came with no image"
    print(
        f"{len(ads_raw['ads'])} ads read ({ads_raw.get('credits_spent', '?')} credits), {pics}"
        + (
            f", {ads_raw['dropped_too_new']} left out for being live under 30 days"
            if ads_raw.get("dropped_too_new")
            else ""
        )
    )
    if not ads_raw["ads"] and not ads_raw.get("dropped_too_new"):
        print(_no_ads_message(args.run_dir, comp))
        return 0
    if not ads_raw["ads"] and not newest:
        print("None of their live ads has run 30+ days. To see their newest ads, add --newest.")
    return 0


def _no_ads_message(run_dir: Path, comp: dict) -> str:
    """0 ads of any age came back: say so, and name what to try, instead of reading again."""
    name = comp.get("page_name") or comp.get("query") or "this page"
    same = [
        a
        for a in comp.get("alternates") or []
        if str(a.get("page_name", "")).strip().lower() == str(name).strip().lower()
    ]
    lines = [
        f"No live ads came back for {name} (page {comp.get('page_id')}, country "
        f"{comp.get('country') or 'US'}), so there is nothing to analyze and no board.",
        "Try: --country with the market they sell in (e.g. GB), or check the page in the "
        "Meta Ad Library.",
    ]
    if same:
        ids = ", ".join(str(a.get("page_id")) for a in same)
        lines.append(f"Another page has the same name ({ids}); run with that page ID to check it.")
    return "\n".join(lines)


def cmd_transcripts(args: argparse.Namespace) -> int:
    from ad_spy_kit.transcribe import current_mode
    from ad_spy_kit.transcripts import fetch_transcripts, quote, transcript_targets

    ads_raw = json.loads((args.run_dir / "ads.raw.json").read_text())
    winners = json.loads((args.run_dir / "winners.json").read_text())
    mode = current_mode()
    if mode.requested == "openrouter" or mode.effective != mode.requested:
        print(mode.note)
    targets = transcript_targets(ads_raw, winners, mode, args.run_dir / "media")
    print(quote(targets, allow_long=args.allow_long, mode=mode))
    if not targets:
        return 0
    if not args.yes:
        print(f"Nothing spent. Rerun with --yes: ad-spy-kit transcripts {args.run_dir} --yes")
        return 0
    doc = fetch_transcripts(
        args.run_dir, cache_max_age=args.cache_max_age, allow_long=args.allow_long, mode=mode
    )
    got = sum(1 for i in doc["items"] if i.get("transcript"))
    print(f"{got}/{len(doc['items'])} transcripts saved to transcripts.json; ads.raw.json updated")
    for i in doc["items"]:
        if i.get("error"):
            print(f"  {i['ad_id']}: {i['error']}")
    return 0


def cmd_transcribe_mode(args: argparse.Namespace) -> int:
    from ad_spy_kit.transcribe import DEFAULT_MODEL, KEY_ENV, current_mode, save_mode

    if args.mode in ("openrouter", "scrapecreators"):
        path = save_mode(args.mode, args.model)
        print(f"saved AD_SPY_TRANSCRIBE={args.mode} to {path}")
    elif args.mode in ("on", "off"):
        mode = "openrouter" if args.mode == "on" else "scrapecreators"
        path = save_mode(mode, args.model)
        print(f"saved AD_SPY_TRANSCRIBE={mode} to {path}")
    m = current_mode()
    print(f"transcripts: {m.effective} (asked: {m.requested}, from {m.origin})")
    print(f"model: {m.model}{' (default)' if m.model == DEFAULT_MODEL else ''}")
    print(f"{KEY_ENV}: {'set' if m.key_present else 'not set'}")
    print(m.note)
    return 0


def cmd_onscreen(args: argparse.Namespace) -> int:
    from ad_spy_kit.onscreen import apply_file, onscreen_targets

    if args.apply:
        landed, problems = apply_file(args.run_dir)
        for p in problems:
            print(f"skipped {p}")
        print(f"{landed} on-screen hooks written to ads.raw.json")
        return 1 if problems else 0
    ads_raw = json.loads((args.run_dir / "ads.raw.json").read_text())
    winners = json.loads((args.run_dir / "winners.json").read_text())
    targets = onscreen_targets(ads_raw, winners, args.run_dir / "media")
    if not targets:
        print("No image on the board needs an on-screen read.")
        return 0
    print(
        "Look at each file and record onscreen_text + onscreen_hook in "
        f"{args.run_dir}/onscreen.json:"
    )
    for t in targets:
        print(f"  {t['ad_id']}  {t['role']}  {t['path']}")
    print(f"Then: ad-spy-kit onscreen {args.run_dir} --apply")
    return 0


def cmd_winners(args: argparse.Namespace) -> int:
    from ad_spy_kit.media import normalize_run
    from ad_spy_kit.score_winners import score_winners
    from ad_spy_kit.spend import thin_read_note
    from ad_spy_kit.validate import assert_valid

    fixed = normalize_run(args.run_dir)
    if fixed["templates"] or fixed["images"]:
        print(
            f"cleaned ads.raw.json: {fixed['templates']} ads had catalog placeholder text "
            f"emptied, {fixed['images']} images shrunk to 1200px"
        )
    ads_raw = json.loads((args.run_dir / "ads.raw.json").read_text())
    winners = score_winners(ads_raw.get("ads", []))
    assert_valid("winners", winners)
    _write(args.run_dir / "winners.json", winners)
    for w in winners["winners"]:
        label = w.get("strength_label") or "-"
        print(f"  #{w['display_rank']:02d} {w['ad_id']}  {label}  {w['why']}")
    note = thin_read_note(ads_raw, str(args.run_dir))
    if note:
        print(f"\n{note}")
    hidden = winners.get("hidden") or []
    if hidden:
        n = len(hidden)
        print(
            f"\n{n} newer ad{'' if n == 1 else 's'} not on the board (under 7 days, under 3 "
            "versions). Read them before you write the headline or any 'none of them' claim:"
        )
        for h in hidden:
            sale = "  [sale copy]" if h.get("bf_tag") in ("bf_live", "bf_teaser") else ""
            print(f"  {h['ad_id']}  {h.get('headline') or 'no headline'!r}{sale}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """StealAds MCP path: the agent saved search_ads pages and find_winning_ads JSON."""
    from ad_spy_kit.sc_client import (
        SEARCH_STEM,
        build_ads_raw_from_fixture,
        cache_media,
        saved_files,
        unfetched_pages,
    )
    from ad_spy_kit.tracked import tracked_files

    run_dir = args.run_dir
    has_list = (run_dir / "stealads_list_ads.json").exists()
    if not has_list and not saved_files(run_dir, SEARCH_STEM) and tracked_files(run_dir):
        print("tracked_rival_ads files found: reading them as a tracked-competitors board.")
        return cmd_tracked(args)
    if not has_list and not saved_files(run_dir, SEARCH_STEM):
        raise KitError(
            f"{run_dir} has no StealAds ads saved (search_ads*.json or stealads_list_ads.json).",
            fix=(
                "Save each search_ads response for the competitor's facebook_page_id as "
                "search_ads.json (format=video/static calls as search_ads.video.json / "
                "search_ads.static.json; more pages fetched with cursor as search_ads.*.page2.json "
                "and so on) and find_winning_ads as find_winning_ads.json, then rerun."
            ),
        )
    ads_raw = build_ads_raw_from_fixture(run_dir)
    if not (run_dir / "competitor.json").exists() and ads_raw["ads"]:
        from ad_spy_kit.competitor_rows import competitor_from_ads

        comp = competitor_from_ads(ads_raw["ads"])
        _write(run_dir / "competitor.json", comp)
        print(
            f"note: competitor.json written from the saved rows: {comp['page_name']!r}, "
            f"page {comp['page_id'] or 'unknown'}. Fix it by hand if that's the wrong page.",
            file=sys.stderr,
        )
        ads_raw = build_ads_raw_from_fixture(run_dir)  # again, now with the page filter
    for name in unfetched_pages(run_dir):
        print(
            f"note: {name} says more results exist (has_more). Fetch them with its "
            "next_cursor and save as another search_ads*.json if you want a bigger sample.",
            file=sys.stderr,
        )
    if not ads_raw["ads"]:
        print(
            "note: the saved StealAds replies hold 0 ads. The brand may not be in StealAds' "
            "library yet: try search_ads with just the brand name, or use the ScrapeCreators path.",
            file=sys.stderr,
        )
    remote = [a for a in ads_raw["ads"] if any("url" in m for m in a.get("media") or [])]
    no_media = [a for a in ads_raw["ads"] if not a.get("media")]
    if getattr(args, "no_images", False):
        for a in remote:
            a["media"] = []
        ads_raw["skipped"] = []
    else:
        extra = {"keep_originals": True} if getattr(args, "keep_originals", False) else {}
        ads_raw["skipped"] = cache_media(remote + no_media, run_dir / "media", **extra)
    if args.import_cap_hit:
        ads_raw["import_cap_hit"] = True
    if ads_raw.get("pulled_at") == DEFAULT_PULLED_AT:
        # Saved replies with no recorded_at: the board says "checked <date>", so it's today.
        ads_raw["pulled_at"] = (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
    _write(run_dir / "ads.raw.json", ads_raw)
    return 0


def cmd_tracked(args: argparse.Namespace) -> int:
    """Tracked competitors: saved tracked_rival_ads* replies → brands/ → the category board."""
    from ad_spy_kit import tracked

    return tracked.run(
        args.run_dir,
        title=getattr(args, "title", None),
        images=not getattr(args, "no_images", False),
        board_brands=getattr(args, "board_brands", None),
    )


def cmd_advertiser(args: argparse.Namespace) -> int:
    """A saved StealAds search_advertisers reply → competitor.json, a question, or the fallback."""
    from ad_spy_kit import stealads_lookup as lookup
    from ad_spy_kit.exclusions import check_not_excluded

    doc = lookup.read_reply(args.reply)
    check_not_excluded(args.query)
    kind = lookup.classify(doc)
    if kind == "not_indexed":
        print(lookup.not_indexed_message(args.query, doc))
        return EXIT_USER
    choices = lookup.advertiser_choices(doc)
    if kind == "choose":
        print(f"More than one Facebook page matches '{args.query}'. Which one is it?")
        for c in choices[:3]:
            print(f"  {c['page_id']}  {c['page_name']}")
        print("Ask the user, then run this again with a reply that names the one page.")
        return EXIT_USER
    for c in choices:
        check_not_excluded(c["page_id"], c["page_name"])
    comp = lookup.competitor_doc(args.query, choices[0])
    out = args.out or args.reply.parent
    _write(out / "competitor.json", comp)
    print(f"StealAds has {comp['page_name']} (page {comp['page_id']}).")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    from ad_spy_kit.errors import explain_stealads_error

    print(explain_stealads_error(args.code, args.message))
    return 0


def is_multi_brand_folder(run_dir: Path) -> bool:
    """`tracked` and `category` write category.json and no single-brand competitor.json."""
    return (run_dir / "category.json").exists() and not (run_dir / "competitor.json").exists()


def cmd_render(args: argparse.Namespace) -> int:
    from ad_spy_kit.render import render_board_bundle

    if is_multi_brand_folder(args.run_dir):
        raise KitError(
            f"{args.run_dir} is a multi-brand folder, and its board is already drawn: "
            f"{args.run_dir}/board.png.",
            fix="To redraw it, run the command that made it again (`tracked` or `category`).",
        )
    for need in ("competitor", "ads.raw", "winners", "analysis", "counters"):
        if not (args.run_dir / f"{need}.json").exists():
            fix = "Run the earlier step (see SKILL.md routing table), then render again."
            if need == "counters":
                fix = COUNTERS_FIX
            raise KitError(
                f"{args.run_dir}/{need}.json is missing, so there is nothing to render.",
                fix=fix,
            )
    render_board_bundle(args.run_dir, repo_root=repo_root())
    gate(args.run_dir)
    print(f"final: {args.run_dir}/board.png (validation.json all checks passed)")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from ad_spy_kit.validate_run import validate_run

    if is_multi_brand_folder(args.run_dir):
        saved = args.run_dir / "validation.json"
        if not saved.exists():
            raise KitError(
                f"{saved} is missing, so this multi-brand folder has no check results.",
                fix="Run the command that made it again (`tracked` or `category`).",
            )
        result = json.loads(saved.read_text())
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else EXIT_GATE
    report = validate_run(args.run_dir, rendered=(args.run_dir / "board.html").exists())
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ok else EXIT_GATE


def cmd_correct(args: argparse.Namespace) -> int:
    path = repo_root() / "evals" / "corrections.jsonl"
    existing = path.read_text().splitlines() if path.exists() else []
    re.compile(args.pattern)
    entry = {
        "id": f"{len([line for line in existing if line.strip()]) + 1:03d}",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "rule": args.rule,
        "pattern": args.pattern,
        "reason": args.reason,
    }
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    print(f"captured correction {entry['id']} → {path} (enforced by validate on every run)")
    return 0


def cmd_golden(args: argparse.Namespace) -> int:
    from ad_spy_kit.fixtures import fixture_names
    from ad_spy_kit.golden import check_golden, write_golden

    names = [args.fixture] if args.fixture else fixture_names(repo_root())
    bad = 0
    for name in names:
        if args.update:
            print(f"updated {write_golden(name)}")
            continue
        diffs = check_golden(name)
        bad += bool(diffs)
        print(f"{name}: {'OK' if not diffs else 'DRIFT'}")
        for d in diffs:
            print(f"  {d}")
    return EXIT_GATE if bad else 0


def cmd_run(args: argparse.Namespace) -> int:
    from ad_spy_kit.sc_client import page_id_from_query, require_key
    from ad_spy_kit.spend import CREDITS_PER_SEARCH, brand_quote, confirm, pull_pages

    fixtures = repo_root() / "fixtures"
    if (fixtures / _slug(args.query)).is_dir():
        print(f"'{args.query}' is a made-up sample brand, so this runs offline for free.")
        print(replay_fixture(_slug(args.query)))
        return 0
    require_key()
    find_page = not page_id_from_query(args.query)
    quote, _, worst = brand_quote(
        args.query,
        max_ads=args.max_ads,
        find_page=find_page,
        newest=args.newest,
        fallback=True,
        min_days=getattr(args, "min_days", None),
    )
    first_worst = (CREDITS_PER_SEARCH if find_page else 0) + pull_pages(args.max_ads)[1]
    cap = args.max_credits
    if cap is not None:
        if first_worst > cap:
            raise KitError(
                f"The first read can cost up to {first_worst} ScrapeCreators credits, "
                f"which is over --max-credits {cap}. Nothing spent.",
                fix=f"Raise --max-credits to {first_worst} or lower --max-ads.",
                code="run_over_cap",
            )
        quote += f" Hard cap: --max-credits {cap}, so it never spends more than {cap}" + (
            " and skips the second read if that wouldn't fit." if worst > cap else "."
        )
    rerun = _rerun(
        "run",
        args.query,
        *(["--country", args.country] if args.country and args.country != "US" else []),
        "--max-ads",
        str(args.max_ads),
        *(["--newest"] if args.newest else []),
        *(["--min-days", str(args.min_days)] if getattr(args, "min_days", None) else []),
        *(["--keep-originals"] if getattr(args, "keep_originals", False) else []),
        *(["--max-credits", str(cap)] if cap is not None else []),
        *(["--out", str(args.out)] if args.out else []),
    )
    if not confirm(quote, yes=args.yes, rerun=rerun):
        return 0
    code, run_dir = _resolve(args.query, args.country, args.out, yes=True)
    if code or run_dir is None:
        return code
    comp = json.loads((run_dir / "competitor.json").read_text())
    spent = CREDITS_PER_SEARCH if find_page else 0

    def read(newest: bool) -> dict:
        cmd_pull(
            argparse.Namespace(
                run_dir=run_dir,
                max_ads=args.max_ads,
                yes=True,
                newest=newest,
                quoted=True,
                no_images=args.no_images,
                min_days=None if newest else getattr(args, "min_days", None),
                keep_originals=getattr(args, "keep_originals", False),
            )
        )
        return json.loads((run_dir / "ads.raw.json").read_text())

    ads_raw = read(args.newest)
    spent += int(ads_raw.get("credits_spent") or 0)
    if not ads_raw["ads"] and not ads_raw.get("dropped_too_new"):
        print(_no_ads_message(run_dir, comp))
        print(f"Total this run: {spent} ScrapeCreators credits.")
        return EXIT_GATE
    if not ads_raw["ads"] and not args.newest:
        retry = _rerun(
            "run",
            str(comp["page_id"]),
            *(["--country", args.country] if args.country and args.country != "US" else []),
            "--newest",
            "--max-ads",
            str(args.max_ads),
            *(["--max-credits", str(cap)] if cap is not None else []),
            "--out",
            str(run_dir),
        )
        need = pull_pages(args.max_ads)[1]
        if cap is not None and spent + need > cap:
            print(
                f"None of their live ads has run 30+ days. Reading their newest ads would "
                f"cost up to {need} more credits, past --max-credits {cap} ({spent} spent), "
                f"so it stopped. To read their newest ads: {retry}"
            )
            return 0
        print("None of their live ads has run 30+ days, so reading their newest ads instead.")
        first_credits = int(ads_raw.get("credits_spent") or 0)
        ads_raw = read(True)
        ads_raw["fallback_from"] = "longest"
        ads_raw["credits_spent"] = first_credits + int(ads_raw.get("credits_spent") or 0)
        (run_dir / "ads.raw.json").write_text(json.dumps(ads_raw, indent=2) + "\n")
        spent = (CREDITS_PER_SEARCH if find_page else 0) + int(ads_raw["credits_spent"])
        print(f"Total this run: {spent} ScrapeCreators credits.")
    cmd_winners(argparse.Namespace(run_dir=run_dir))
    # Spoken hooks cost credits: quote only, fetch on a yes.
    cmd_transcripts(
        argparse.Namespace(run_dir=run_dir, yes=False, allow_long=False, cache_max_age="7d")
    )
    cmd_onscreen(argparse.Namespace(run_dir=run_dir, apply=False))
    print(
        f"\nNext: the agent writes {run_dir}/analysis.json (skills/ad-spy-kit-analyze) and "
        f"counters.json (skills/ad-spy-kit-counter), then `ad-spy-kit render {run_dir}`."
    )
    return 0


def cmd_category(args: argparse.Namespace) -> int:
    from ad_spy_kit import category

    if not args.target and not args.from_dir and not args.brands_file:
        raise KitError(
            "Tell me a keyword or a list of brands.",
            fix='e.g. ad-spy-kit category "black friday skincare"',
            code="category_no_target",
        )
    name = args.target or (args.brands_file.stem if args.brands_file else "category")
    out = args.out or args.from_dir or repo_root() / "runs" / "category" / _slug(name)
    read = "newest" if args.newest else args.read
    rerun_args = ["category", *([args.target] if args.target else [])]
    rerun_args += ["--max-ads", str(args.max_ads), "--read", read]
    if args.brands_file:
        rerun_args += ["--brands-file", str(args.brands_file)]
    if args.max_credits is not None:
        rerun_args += ["--max-credits", str(args.max_credits)]
    if args.workers != 1:
        rerun_args += ["--workers", str(args.workers)]
    if args.out:
        rerun_args += ["--out", str(args.out)]
    if args.no_images:
        rerun_args += ["--no-images"]
    return category.run(
        args.target,
        out=out,
        yes=args.yes,
        from_dir=args.from_dir,
        title=args.title,
        max_ads=args.max_ads,
        max_brands=args.max_brands,
        country=args.country,
        read=read,
        brands_file=args.brands_file,
        max_credits=args.max_credits,
        workers=args.workers,
        board_brands=args.board_brands,
        images=not args.no_images,
        rerun=_rerun(*rerun_args),
    )


MIN_DAYS_HELP = (
    "only read ads that have already run this many days (default 30). ScrapeCreators has no "
    "longest-running sort, so this moves the date cutoff instead; same cost per page"
)
KEEP_ORIGINALS_HELP = (
    "also keep each image's full-size original in media/originals/ (by default images are "
    "saved at most 1200px on the long edge)"
)
NO_IMAGES_HELP = (
    "don't download the ads' images (by default each image is saved next to the run, "
    "because Meta's links expire)"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ad-spy-kit", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("replay", help="Rebuild a sample brand's board offline (no key, no credits)")
    s.add_argument(
        "--sample",
        "--fixture",
        dest="fixture",
        default="foldbrook",
        help="foldbrook, dewbar, fizzwell (made up) or live/spacegoods (a real recording)",
    )
    s.add_argument("--output", type=Path, default=None)
    sub.add_parser("replay-all", help="Rebuild every sample brand's board offline")

    s = sub.add_parser(
        "run",
        help="Name a brand (or paste its page ID / Ad Library page link): quote, then read "
        "the ads they've kept running 30+ days, most-shown first. A sample brand runs offline.",
    )
    s.add_argument("query")
    s.add_argument("--country", default="US")
    s.add_argument("--out", type=Path, default=None)
    s.add_argument("--max-ads", type=int, default=30, help="read up to N ads (default 30)")
    s.add_argument("--newest", action="store_true", help=NEWEST_HELP)
    s.add_argument("--min-days", type=int, default=None, help=MIN_DAYS_HELP)
    s.add_argument("--no-images", action="store_true", help=NO_IMAGES_HELP)
    s.add_argument("--keep-originals", action="store_true", help=KEEP_ORIGINALS_HELP)
    s.add_argument(
        "--max-credits",
        type=int,
        default=None,
        help="hard cap on ScrapeCreators credits for the whole run (page lookup, the read, "
        "and the newest-ads fallback)",
    )
    s.add_argument("--yes", action="store_true", help="Spend the quoted credits")

    s = sub.add_parser(
        "category",
        help='Several brands on one sorted board: a keyword ("black friday skincare") or a '
        'list ("Brand A, Brand B"). Quotes credits first; --from redraws saved data for free.',
    )
    s.add_argument("target", nargs="?", default=None, help="keyword, or brands split by commas")
    s.add_argument(
        "--max-ads", type=int, default=30, help="read up to N ads per brand (default 30)"
    )
    s.add_argument("--newest", action="store_true", help=NEWEST_HELP)
    s.add_argument(
        "--max-brands", type=int, default=10, help="keyword search: up to N brands (max 10)"
    )
    s.add_argument("--country", default="US")
    s.add_argument("--out", type=Path, default=None)
    s.add_argument("--title", default=None, help="board title (default: the keyword)")
    s.add_argument(
        "--from", dest="from_dir", type=Path, default=None, help="redraw a saved run, no credits"
    )
    s.add_argument(
        "--read",
        choices=("longest", "most-shown", "newest"),
        default="longest",
        help="longest (default): ads live 30+ days; most-shown: the most-shown live ads of "
        "any age, labeled by age here; newest: the newest live ads",
    )
    s.add_argument(
        "--brands-file", type=Path, default=None, help="CSV of brands: name, page_id, country"
    )
    s.add_argument(
        "--max-credits", type=int, default=None, help="hard cap: never start a brand past this"
    )
    s.add_argument("--workers", type=int, default=1, help="brands read at once (default 1)")
    s.add_argument(
        "--board-brands", type=int, default=10, help="brands on the board image (max 10)"
    )
    s.add_argument("--no-images", action="store_true", help=NO_IMAGES_HELP)
    s.add_argument("--yes", action="store_true", help="Spend the quoted credits")

    s = sub.add_parser(
        "resolve", help="Brand name, page ID or page link → competitor.json (ScrapeCreators)"
    )
    s.add_argument("query")
    s.add_argument("--country", default="US")
    s.add_argument("--out", type=Path, default=None)
    s.add_argument("--yes", action="store_true", help="Spend the quoted credit")

    for name, helptext in (
        ("pull", "competitor.json → ads.raw.json + saved images (ScrapeCreators, quoted first)"),
        ("winners", "ads.raw.json → winners.json: sort by run length, add labels"),
        ("render", "Run folder → board, X slices, newsletter and preview images, then the checks"),
        ("validate", "Run the board checks on a run folder and print the report"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("run_dir", type=Path)
        if name == "pull":
            s.add_argument("--max-ads", type=int, default=30, help="read up to N ads (default 30)")
            s.add_argument("--newest", action="store_true", help=NEWEST_HELP)
            s.add_argument("--min-days", type=int, default=None, help=MIN_DAYS_HELP)
            s.add_argument("--no-images", action="store_true", help=NO_IMAGES_HELP)
            s.add_argument("--keep-originals", action="store_true", help=KEEP_ORIGINALS_HELP)
            s.add_argument("--yes", action="store_true", help="Spend the quoted credits")

    s = sub.add_parser(
        "transcripts",
        help="Quote, then fetch what the board's video ads say (ScrapeCreators; OpenRouter opt-in)",
    )
    s.add_argument("run_dir", type=Path)
    s.add_argument("--yes", action="store_true", help="Spend the quoted credits")
    s.add_argument("--cache-max-age", default="7d", choices=("1d", "3d", "7d", "14d", "30d"))
    s.add_argument(
        "--allow-long", action="store_true", help="Transcribe >2 min videos (10 credits/min)"
    )

    s = sub.add_parser(
        "transcribe-mode",
        help="Show or set the transcript source: scrapecreators (default) or openrouter (opt-in)",
    )
    s.add_argument(
        "mode",
        nargs="?",
        default="status",
        choices=("status", "openrouter", "scrapecreators", "on", "off"),
    )
    s.add_argument(
        "--model", default=None, help="OpenRouter model id (default google/gemini-3.8-flash)"
    )

    s = sub.add_parser(
        "onscreen", help="List board images for the agent to read; --apply saves onscreen.json"
    )
    s.add_argument("run_dir", type=Path)
    s.add_argument("--apply", action="store_true", help="onscreen.json → ads.raw.json")

    s = sub.add_parser(
        "tracked",
        help="Tracked competitors: saved tracked_rival_ads*.json (StealAds list_tracked_rival_ads) "
        "→ one board of up to 10 brands, 3 ads each. Free: nothing is spent.",
    )
    s.add_argument("run_dir", type=Path, help="folder holding the saved tracked_rival_ads* files")
    s.add_argument("--title", default=None, help="board title (default: the folder name)")
    s.add_argument(
        "--board-brands", type=int, default=10, help="brands on the board image (max 10)"
    )
    s.add_argument("--no-images", action="store_true", help=NO_IMAGES_HELP)

    s = sub.add_parser("ingest", help="StealAds MCP: saved StealAds JSON → ads.raw.json + images")
    s.add_argument("run_dir", type=Path)
    s.add_argument("--import-cap-hit", action="store_true", help="StealAds said the cap cut it")
    s.add_argument("--no-images", action="store_true", help=NO_IMAGES_HELP)
    s.add_argument("--keep-originals", action="store_true", help=KEEP_ORIGINALS_HELP)

    s = sub.add_parser(
        "advertiser",
        help="Read a saved StealAds search_advertisers reply: write competitor.json, ask which "
        "page, or say plainly that StealAds doesn't have the brand (exit 2) and name the "
        "ScrapeCreators fallback",
    )
    s.add_argument("reply", type=Path, help="the saved search_advertisers JSON reply")
    s.add_argument("--query", default="", help="what the user typed (name, domain, id or link)")
    s.add_argument("--out", type=Path, default=None, help="run folder (default: the reply's)")

    s = sub.add_parser("explain", help="StealAds: an error code → what it means + what to do")
    s.add_argument("code")
    s.add_argument("message", nargs="?", default=None)

    s = sub.add_parser("correct", help="Capture a correction; validate enforces it forever")
    s.add_argument("--rule", choices=("must_not_contain", "must_contain"), required=True)
    s.add_argument("--pattern", required=True, help="Regex matched against visible board text")
    s.add_argument("--reason", required=True)

    s = sub.add_parser("golden", help="Check the sample boards haven't drifted")
    s.add_argument("--sample", "--fixture", dest="fixture", default=None)
    s.add_argument("--update", action="store_true", help="Accept current output as golden")
    return p


HANDLERS = {
    "run": cmd_run,
    "category": cmd_category,
    "resolve": cmd_resolve,
    "pull": cmd_pull,
    "winners": cmd_winners,
    "transcripts": cmd_transcripts,
    "onscreen": cmd_onscreen,
    "transcribe-mode": cmd_transcribe_mode,
    "ingest": cmd_ingest,
    "tracked": cmd_tracked,
    "advertiser": cmd_advertiser,
    "explain": cmd_explain,
    "render": cmd_render,
    "validate": cmd_validate,
    "correct": cmd_correct,
    "golden": cmd_golden,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "replay":
            print(replay_fixture(args.fixture, output_dir=args.output))
            return 0
        if args.cmd == "replay-all":
            for path in replay_all_fixtures():
                print(path)
            return 0
        return HANDLERS[args.cmd](args)
    except KitError as e:
        print(e.render(), file=sys.stderr)
        return EXIT_USER
    except GateFailed as e:
        print(str(e), file=sys.stderr)
        return EXIT_GATE


if __name__ == "__main__":
    raise SystemExit(main())
