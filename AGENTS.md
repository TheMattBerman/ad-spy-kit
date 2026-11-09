# Agent notes

- Prove a change with `uv run ad-spy-kit replay-all` (renders + gate), `uv run pytest -q`,
  `uv run ruff check . && uv run ruff format --check .` (`vendor/` and `cie/` are ported upstream code and excluded). Re-render artifacts when output changes.
- Fixtures are generated: edit `scripts/gen_fixtures.py`, run it, then
  `ad-spy-kit golden --update --fixture <name>` only for an intended change, and commit the diff.
- Never show a numeric score; bands + facts-only `why` only (gate B1).
- StealAds MCP is the primary path (Matt, 2026-11-05; live at https://mcp.stealads.ai/mcp). Access
  links in copy use the literal `https://stealads.ai` until Matt supplies one. The
  ScrapeCreators flow stays a complete alternate path. Status in `docs/stealads-mcp.md`.
- Never commit secrets or `.env`. Design tokens live in `templates/board/war-room-tokens.css`.
- CI is disabled on purpose; don't re-enable `.github/workflows/ci.yml`.
