from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ad_spy_kit.fixtures import fixture_names, is_live
from ad_spy_kit.paths import visible
from ad_spy_kit.render import render_board_bundle
from ad_spy_kit.sc_client import build_ads_raw_from_fixture
from ad_spy_kit.score_winners import score_winners
from ad_spy_kit.validate import assert_valid
from ad_spy_kit.validate_run import validate_run


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def replay_fixture(name: str, *, output_dir: Path | None = None) -> Path:
    """Rebuild a sample brand's board offline. Renders into a scratch folder next to the
    target and swaps it in only when the render and the gate both pass, so a failed first
    run (no Chromium, a gate error) never deletes the board that shipped with the kit."""
    root = repo_root()
    fixture_dir = root / "fixtures" / name
    if not fixture_dir.is_dir():
        from ad_spy_kit.errors import KitError
        from ad_spy_kit.fixtures import fixture_names

        raise KitError(
            f"There's no sample brand called '{name}'.",
            fix="Sample brands: " + ", ".join(fixture_names(root)),
            code="unknown_sample",
        )

    target = output_dir or (root / "artifacts" / "screenshots" / name)
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        _replay_into(name, fixture_dir, scratch, root)
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    if target.exists():
        shutil.rmtree(target)
    scratch.rename(target)
    return target


def _replay_into(name: str, fixture_dir: Path, run_dir: Path, root: Path) -> None:

    for src in ("competitor.json", "analysis.json", "counters.json"):
        shutil.copy2(fixture_dir / src, run_dir / src)

    ads_raw = build_ads_raw_from_fixture(fixture_dir)
    if is_live(name):
        _use_recorded_media(ads_raw, fixture_dir / "media")
    else:
        ads_raw["synthetic"] = True  # bundled fixtures are made up; the board must say so
    # Samples carry labels from before StealAds #3343 (or made-up ones). Relabel them with
    # the shared rule so every sample board matches its own legend.
    from ad_spy_kit.labels import strength_label

    for ad in ads_raw.get("ads", []):
        ad["label_source"] = "run_length"
        ad["strength_label"] = strength_label(ad)
    (run_dir / "ads.raw.json").write_text(json.dumps(ads_raw, indent=2))
    assert_valid("ads.raw", ads_raw, root=root)

    winners = score_winners(ads_raw.get("ads", []))
    (run_dir / "winners.json").write_text(json.dumps(winners, indent=2))
    assert_valid("winners", winners, root=root)

    media_src = fixture_dir / "media"
    media_dst = run_dir / "media"
    if media_src.is_dir():
        shutil.copytree(media_src, media_dst)

    render = render_board_bundle(run_dir, repo_root=root)

    run_manifest = {
        "fixture": name,
        "source": ads_raw.get("source"),
        "rank_source": winners.get("rank_source"),
        "winners": [w["ad_id"] for w in winners.get("winners", [])],
        "dropped_no_media": render.get("dropped_no_media", []),
    }
    digest = hashlib.sha256(json.dumps(run_manifest, sort_keys=True).encode()).hexdigest()[:12]
    run_manifest["hash"] = digest  # stable across replays: excludes the timestamp
    run_manifest["replayed_at"] = datetime.now(UTC).isoformat()
    (run_dir / "run.json").write_text(json.dumps(run_manifest, indent=2))
    gate(run_dir, label=name)


def _use_recorded_media(ads_raw: dict, media_dir: Path) -> None:
    """Live recordings ship the creatives cached at record time; point each ad at its file."""
    for ad in ads_raw.get("ads", []):
        found = visible(sorted(media_dir.glob(f"{ad['ad_id']}.*"))) if media_dir.is_dir() else []
        kind = (ad.get("media") or [{}])[0].get("kind", "image")
        if found:
            ad["media"] = [{"path": f"media/{found[0].name}", "durable": True, "kind": kind}]
        else:
            ad["media"] = []
            ads_raw.setdefault("skipped", []).append(
                {"ad_id": ad["ad_id"], "reason": "media_not_recorded"}
            )


class GateFailed(Exception):
    pass


FINAL_IMAGES = ("board.png", "newsletter.png", "og.png")


def _fail_name(name: str) -> str:
    stem, dot, ext = name.partition(".")
    return f"{stem}.failed{dot}{ext}"


def _park_failed_images(run_dir: Path) -> list[str]:
    """A board that failed its checks must not sit there looking final. Rename the images
    (board.png → board.failed.png, x-slices → x-slices.failed) and return the new names."""
    parked = []
    for name in FINAL_IMAGES:
        src = run_dir / name
        if src.is_file():
            dst = run_dir / _fail_name(name)
            dst.unlink(missing_ok=True)
            src.rename(dst)
            parked.append(dst.name)
    slices = run_dir / "x-slices"
    if slices.is_dir():
        dst = run_dir / "x-slices.failed"
        shutil.rmtree(dst, ignore_errors=True)
        slices.rename(dst)
        parked.append(dst.name)
    return parked


def _clear_failed_images(run_dir: Path) -> None:
    for name in FINAL_IMAGES:
        (run_dir / _fail_name(name)).unlink(missing_ok=True)
    shutil.rmtree(run_dir / "x-slices.failed", ignore_errors=True)


def gate(run_dir: Path, *, label: str | None = None) -> None:
    """Spec §12 runtime gate: write validation.json; raise if any blocking check fails.

    A failed gate renames board.png (and the other images) to *.failed.png, so nothing in
    the folder looks final until the checks pass."""
    report = validate_run(run_dir)
    (run_dir / "validation.json").write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    if not report.ok:
        parked = _park_failed_images(run_dir)
        where = (
            f"The drawn images were renamed {', '.join(parked)} so none looks final. "
            if parked
            else ""
        )
        raise GateFailed(
            f"{label or run_dir.name}: {len(report.errors)} check(s) failed, so the board "
            f"isn't final. {where}Fix the problems, then render again:\n  "
            + "\n  ".join(report.errors)
        )
    _clear_failed_images(run_dir)


def replay_all_fixtures() -> list[Path]:
    root = repo_root()
    return [replay_fixture(n) for n in fixture_names(root)]
