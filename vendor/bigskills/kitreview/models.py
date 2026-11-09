from dataclasses import dataclass, asdict, field
from typing import List

@dataclass
class Finding:
    rule: str
    severity: str          # "error" | "warn"
    message: str
    fix: str = ""
    def to_dict(self): return asdict(self)

@dataclass
class CriterionScore:
    id: str
    score: int             # 1-5
    reason: str = ""
    def to_dict(self): return asdict(self)

@dataclass
class KitScorecard:
    kit: str
    compliance_verdict: str        # "PASS" | "FLAG"
    findings: List[dict] = field(default_factory=list)
    quality: List[dict] = field(default_factory=list)
    grade: str = "Thin"            # Gold | Strong | Concept | Thin
    quality_avg: float = 0.0
    optimization_plan: List[dict] = field(default_factory=list)
    def to_dict(self): return asdict(self)
