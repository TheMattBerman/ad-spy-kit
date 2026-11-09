from __future__ import annotations

from pathlib import Path

from ad_spy_kit.paths import visible


def slice_board(html_path: Path, out_dir: Path, *, repo_root: Path) -> list[Path]:
    """Render carousel slices from labeled sections in board HTML."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in visible(
        out_dir.glob("[0-9][0-9].png")
    ):  # a board with fewer slices than last time
        stale.unlink(missing_ok=True)
    uri = html_path.resolve().as_uri()
    paths: list[Path] = []
    with sync_playwright() as p:
        from ad_spy_kit.render import launch_chromium

        browser = launch_chromium(p)
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.goto(uri, wait_until="networkidle")
        for idx in range(1, 6):
            sel = f"#slice-{idx:02d}"
            if page.locator(sel).count() == 0:
                continue
            # Slices sit off-canvas in the board; bring each one on-screen to shoot it,
            # otherwise the crop captures the board behind it.
            page.evaluate(
                "s => { const el = document.querySelector(s);"
                " el.style.left = '0'; el.style.top = '0'; el.style.zIndex = '9999';"
                " window.scrollTo(0, 0); }",
                sel,
            )
            if not page.locator(sel).bounding_box():
                continue
            out = out_dir / f"{idx:02d}.png"
            page.locator(sel).screenshot(path=str(out))
            page.evaluate("s => { document.querySelector(s).style.left = '-9999px'; }", sel)
            paths.append(out)
        browser.close()
    return paths
