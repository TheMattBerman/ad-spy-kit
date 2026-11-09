import subprocess
from pathlib import Path

FLOOR_FILES = ["README.md", "install.sh", "LICENSE", "VERSION", "CHANGELOG.md",
               "AGENTS.md", ".env.example", "doctor.sh"]

def _tree(d: Path, limit=80):
    rows = []
    for p in sorted(d.rglob("*")):
        s = str(p.relative_to(d))
        if s.startswith(".git/") or "/node_modules/" in s or "__pycache__" in s:
            continue
        rows.append(s + ("/" if p.is_dir() else ""))
        if len(rows) >= limit:
            rows.append("... (truncated)")
            break
    return "\n".join(rows)

def _count(d: Path, sub):
    p = d / sub
    return sum(1 for _ in p.rglob("*.py")) + sum(1 for _ in p.rglob("*.bats")) if p.is_dir() else 0

def build_profile(kit_dir: str, readme_chars=6000):
    d = Path(kit_dir)
    readme = (d / "README.md").read_text(errors="ignore")[:readme_chars] if (d / "README.md").is_file() else ""
    try:
        commits = int(subprocess.run(["git", "-C", str(d), "rev-list", "--count", "HEAD"],
                                     capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        commits = 0
    return {
        "name": d.resolve().name,
        "readme": readme,
        "structure": _tree(d),
        "floor_present": {f: (d / f).is_file() for f in FLOOR_FILES},
        "has_tests": (d / "tests").is_dir(),
        "has_evals": (d / "evals").is_dir(),
        "test_file_count": _count(d, "tests") + _count(d, "evals"),
        "commit_count": commits,
        "magic_moment_claim": next((ln.strip() for ln in readme.splitlines()
                                    if ln.strip() and not ln.startswith("#")), ""),
    }
