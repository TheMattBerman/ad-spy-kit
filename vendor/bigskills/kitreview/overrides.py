import json
from datetime import datetime
from pathlib import Path

def _daily_file(corpus: Path, ts: str) -> Path:
    day = ts[:10] if ts else datetime.now().strftime("%Y-%m-%d")
    return corpus / f"{day}.jsonl"

def append_override(corpus, *, profile_id, kit, criterion, model_score,
                    matt_score, why, ts=None):
    corpus = Path(corpus)
    corpus.mkdir(parents=True, exist_ok=True)
    ts = ts or datetime.now().isoformat(timespec="seconds")
    rec = {"profile_id": profile_id, "kit": kit, "criterion": criterion,
           "model_score": model_score, "matt_score": int(matt_score),
           "why": why, "ts": ts}
    with (_daily_file(corpus, ts)).open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def load_overrides(corpus, limit=12):
    corpus = Path(corpus)
    if not corpus.is_dir():
        return []
    recs = []
    for jf in sorted(corpus.glob("*.jsonl")):
        for line in jf.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    recs.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return recs[:limit]
