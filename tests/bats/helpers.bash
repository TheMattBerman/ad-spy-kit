# Shared setup: a throwaway HOME so install/uninstall never touch the real skill dirs.
REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
setup_home() {
  export REAL_HOME="$HOME"
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME"
  # uv and Playwright keep caches, Pythons and Chromium under the real HOME.
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$REAL_HOME/.cache/uv}"
  export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$REAL_HOME/.local/share/uv/python}"
  # Playwright's default cache: ~/Library/Caches on macOS, ~/.cache on Linux.
  local pw_cache="$REAL_HOME/.cache/ms-playwright"
  [ "$(uname -s)" = "Darwin" ] && pw_cache="$REAL_HOME/Library/Caches/ms-playwright"
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$pw_cache}"
}
