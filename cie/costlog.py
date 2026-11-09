class CostLog:
    def __init__(self):
        self.rows = []
        self.skips = []

    def add(self, vector: str, tools: str, pulls: str, cost: float) -> None:
        self.rows.append({"vector": vector, "tools": tools, "pulls": pulls, "cost": float(cost)})

    def note_skip(self, reason: str) -> None:
        self.skips.append(reason)

    def total(self) -> float:
        return round(sum(round(r["cost"], 2) for r in self.rows), 2)

    def render_md(self) -> str:
        lines = ["# Sources & Cost Log", "", "| Vector | Tools | Pulls | Cost |", "|---|---|---|---|"]
        for r in self.rows:
            lines.append(f"| {r['vector']} | {r['tools']} | {r['pulls']} | ${r['cost']:.2f} |")
        lines.append("")
        lines.append(f"**Total: ${self.total():.2f}**")
        if self.skips:
            lines.append("")
            lines.append("## Skipped (no silent caps)")
            for s in self.skips:
                lines.append(f"- {s}")
        return "\n".join(lines) + "\n"
