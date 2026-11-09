import re
import subprocess
from pathlib import Path
from .models import Finding

# (filename, rule-id, severity, fix)  -- README + install are errors; the rest warn.
FLOOR = [
    ("README.md", "missing-readme", "error", "Add a README that sells the magic + a quick start."),
    ("install.sh", "missing-install", "error", "Add an idempotent install.sh."),
    ("LICENSE", "missing-license", "warn", "Add a LICENSE (MIT for public)."),
    ("VERSION", "missing-version", "warn", "Add a semver VERSION."),
    ("CHANGELOG.md", "missing-changelog", "warn", "Add CHANGELOG.md, one entry per release."),
    ("AGENTS.md", "missing-agents", "warn", "Add AGENTS.md (how an agent operates the kit)."),
    (".env.example", "missing-env-example", "warn", "Add .env.example with var names only."),
    ("doctor.sh", "missing-doctor", "warn", "Add doctor.sh that checks env/deps/auth."),
]
_SEMVER = re.compile(r"^\d+\.\d+\.\d+")
_SECRET = re.compile(
    r"sk-or-v1-[A-Za-z0-9]{20,}"
    r"|sk-ant-[A-Za-z0-9\-]{20,}"
    r"|sk-[A-Za-z0-9]{24,}"
    r"|OPENROUTER" "_API_KEY=sk-"
    r"|OPENAI" "_API_KEY=sk-"
)
_MACHINE = re.compile(
    r"/Users/[A-Za-z0-9._-]+/"
    r"|/home/[A-Za-z0-9._-]+/"
    r"|~/" "clawd"
)

def _has_skill(d: Path):
    return (d / "SKILL.md").is_file() or any(d.glob("skills/*/SKILL.md"))

# Directories whose contents are never shipped (fixtures, build artefacts, dev-only).
_DEV_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "tests", "evals"}

# Directories that hold generated run-output / artifacts (manifests, reports, guard-reports).
# Machine-paths in these are legitimate run-time records, not source leaks.
_RUN_OUTPUT_DIRS = {
    "runs", "run", "output", "outputs", "_runs", ".runs", "backtest", "sample-runs",
    # kit-specific run-output patterns (frontrun uses frontrun-runs/ and prototypes/)
    "frontrun-runs", "prototypes",
    # archive / backup dirs: preserved older material, not shipped runtime source
    "backups", "backup", "archive", ".backups",
}

# Path-prefix segments that mark brainstorm/plan PROCESS docs inside docs/.
# These may legitimately contain absolute example paths (same as tests fixtures).
_PROCESS_PREFIXES = ("docs/specs/", "docs/plans/", "docs\\specs\\", "docs\\plans\\")

def _shipped_text_files(d: Path):
    for p in d.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".md", ".sh", ".py", ".json", ".txt", ".yml", ".yaml", ".js", ".ts"):
            rel = str(p.relative_to(d))
            # Skip entire dev/tool directories
            if any(rel.startswith(dev + "/") or rel.startswith(dev + "\\") or ("/" + dev + "/") in rel
                   for dev in _DEV_DIRS):
                continue
            # Skip run-output / generated-artifact directories (manifests, guard-reports, etc.)
            # Machine-paths in these are legitimate run-time records, not source leaks.
            if any(rel.startswith(ro + "/") or rel.startswith(ro + "\\") or ("/" + ro + "/") in rel
                   for ro in _RUN_OUTPUT_DIRS):
                continue
            # Skip process-only docs (brainstorm plans/specs) — not shipped runtime
            if any(rel.startswith(pfx) for pfx in _PROCESS_PREFIXES):
                continue
            yield p

def check_compliance(kit_dir: str):
    d = Path(kit_dir)
    out = []
    for fname, rule, sev, fix in FLOOR:
        if not (d / fname).is_file():
            out.append(Finding(rule=rule, severity=sev, message=f"missing {fname}", fix=fix))
    if not _has_skill(d):
        out.append(Finding(rule="no-skill", severity="error",
                           message="no SKILL.md or skills/*/SKILL.md", fix="Add the skill(s)."))
    if not ((d / "tests").is_dir() or (d / "evals").is_dir()):
        out.append(Finding(rule="missing-tests-and-evals", severity="warn",
                           message="no tests/ or evals/ — quality is unverified",
                           fix="Add evals/ (a blocking rubric like frontrun) or tests/."))
    v = (d / "VERSION")
    if v.is_file() and not _SEMVER.match(v.read_text().strip()):
        out.append(Finding(rule="version-not-semver", severity="warn",
                           message="VERSION is not semver", fix="Use MAJOR.MINOR.PATCH."))
    # secret / machine-path scan over shipped text files
    for p in _shipped_text_files(d):
        try:
            txt = p.read_text(errors="ignore")
        except Exception:
            continue
        if _SECRET.search(txt):
            out.append(Finding(rule="secret", severity="error",
                               message=f"possible secret in {p.name}", fix="Remove it; read from env."))
        if _MACHINE.search(txt):
            out.append(Finding(rule="machine-path", severity="error",
                               message=f"machine path in {p.name}", fix="Use env vars / relative paths."))
    # tracked .env in git
    try:
        tracked = subprocess.run(["git", "-C", str(d), "ls-files"], capture_output=True, text=True).stdout
        if re.search(r"(^|/)\.env$", tracked, re.M):
            out.append(Finding(rule="tracked-env", severity="error",
                               message="a .env is tracked in git", fix="git rm --cached .env; gitignore it."))
    except Exception:
        pass
    return out
