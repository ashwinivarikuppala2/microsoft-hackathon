"""Deterministic reasoning over recalled experiences.

No LLM is involved: every number shown in the UI can be traced to a recalled memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field

OUTCOMES = ["WON", "LOST", "STALLED"]
OUTCOME_VALUE = {"WON": 1.0, "STALLED": 0.35, "LOST": 0.0}
K_PRIOR = 1.5            # strength of the playbook prior (in "pseudo-deals")
SIMILAR_THRESHOLD = 0.5  # min attribute similarity for a memory to count as a similar deal

TACTICS: dict[str, dict] = {
    "roi": {
        "label": "Quantify ROI / value-based selling",
        "prior": 0.55,
        "track": [
            "Ask what the current process costs them per month (late deliveries, manual work).",
            "Put the price next to a payback period: 'this pays for itself in ~N months'.",
            "Only discuss price after the buyer has agreed to the value number.",
        ],
    },
    "phased": {
        "label": "Phased rollout / flexible terms",
        "prior": 0.50,
        "track": [
            "Split the deal: smaller starting scope, expand after a success milestone.",
            "Offer annual-with-quarterly billing instead of cutting the price.",
            "Tie expansion pricing to results so the CFO sees limited downside.",
        ],
    },
    "exec": {
        "label": "Executive sponsor call",
        "prior": 0.50,
        "track": [
            "Bring your VP to a 20-minute call with the economic buyer.",
            "Let the exec reframe price as a strategic decision, not a line item.",
            "Agree a decision date on the call.",
        ],
    },
    "proof": {
        "label": "Hold price, add proof (case study / pilot)",
        "prior": 0.50,
        "track": [
            "Share a case study from a same-industry customer with hard numbers.",
            "Offer a short paid pilot instead of a discount.",
            "Hold the list price and trade any concession for something (term, reference).",
        ],
    },
    "discount": {
        "label": "Discount up front",
        "prior": 0.40,
        "track": [
            "Offer a percentage discount immediately to match the competitor.",
            "Ask for a signature this week in exchange.",
        ],
    },
}

_PROFILE_WEIGHTS = {"objection": 0.35, "industry": 0.20, "size": 0.15, "role": 0.15, "competitor": 0.15}


@dataclass
class Deal:
    deal_id: str
    company: str
    industry: str
    size: str
    value: int
    stage: str
    objection: str
    competitor: str
    role: str
    customer_said: str

    def profile(self) -> dict[str, str]:
        return {k: getattr(self, k) for k in _PROFILE_WEIGHTS}

    def profile_text(self) -> str:
        return (f"{self.industry} {self.size} deal, {self.objection} objection, "
                f"competitor {self.competitor}, buyer role {self.role}")


def similarity(a: dict[str, str], b: dict[str, str]) -> tuple[float, list[str]]:
    """Weighted attribute match between two deal profiles, plus the matching fields."""
    score, matched = 0.0, []
    for key, w in _PROFILE_WEIGHTS.items():
        va, vb = (a.get(key) or "").strip().lower(), (b.get(key) or "").strip().lower()
        if va and va == vb:
            score += w
            matched.append(key)
    return round(score, 3), matched


@dataclass
class Experience:
    memory_id: str
    deal_id: str
    company: str
    profile: dict[str, str]
    tactic: str
    outcome: str
    lesson: str
    value: str
    relevance: float = 0.0


def experiences_from(memories) -> list[Experience]:
    """Turn recalled memories into structured experiences (deduped by deal_id)."""
    best: dict[str, Experience] = {}
    for m in memories:
        md = m.metadata or {}
        if md.get("tactic") not in TACTICS or md.get("outcome") not in OUTCOMES or not md.get("deal_id"):
            continue  # free-text context memory: shown in the UI, not used for statistics
        exp = Experience(
            memory_id=m.id, deal_id=md["deal_id"], company=md.get("company", "?"),
            profile={k: md.get(k, "") for k in _PROFILE_WEIGHTS},
            tactic=md["tactic"], outcome=md["outcome"], lesson=md.get("lesson", ""),
            value=md.get("value", ""), relevance=m.relevance,
        )
        if exp.deal_id not in best or exp.relevance > best[exp.deal_id].relevance:
            best[exp.deal_id] = exp
    return list(best.values())


@dataclass
class Analysis:
    deal: Deal
    mode: str                                   # "playbook" (no evidence) | "evidence"
    similar: list[dict] = field(default_factory=list)
    tactic_stats: list[dict] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    recommendation: dict = field(default_factory=dict)
    avoid: list[dict] = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    eff_weight: float = 0.0


def _confidence(eff_weight: float) -> tuple[float, str]:
    c = eff_weight / (eff_weight + 2.0)
    label = "Very low" if c < 0.2 else "Low" if c < 0.4 else "Medium" if c < 0.6 else "High"
    return round(c, 2), label


def tactic_scores(deal: Deal, exps: list[Experience]) -> list[dict]:
    rows = []
    for key, t in TACTICS.items():
        rel = []
        for e in exps:
            s, matched = similarity(deal.profile(), e.profile)
            if e.tactic == key and s >= SIMILAR_THRESHOLD:
                rel.append((e, s))
        w = sum(s for _, s in rel)
        num = t["prior"] * K_PRIOR + sum(s * OUTCOME_VALUE[e.outcome] for e, s in rel)
        rows.append({
            "key": key, "label": t["label"], "prior": t["prior"],
            "score": round(num / (K_PRIOR + w), 3), "n": len(rel), "weight": round(w, 2),
            "won": sum(e.outcome == "WON" for e, _ in rel),
            "lost": sum(e.outcome == "LOST" for e, _ in rel),
            "stalled": sum(e.outcome == "STALLED" for e, _ in rel),
        })
    return rows


def analyze(deal: Deal, memories, exclude_deal_ids: set[str] | None = None) -> Analysis:
    exclude = exclude_deal_ids or set()
    exps = [e for e in experiences_from(memories) if e.deal_id not in exclude]

    similar = []
    for e in exps:
        s, matched = similarity(deal.profile(), e.profile)
        if s >= SIMILAR_THRESHOLD:
            similar.append({"exp": e, "sim": s, "matched": matched})
    similar.sort(key=lambda r: -r["sim"])
    eff = sum(r["sim"] for r in similar)

    stats = tactic_scores(deal, [r["exp"] for r in similar])
    a = Analysis(deal=deal, mode="evidence" if similar else "playbook", similar=similar,
                 tactic_stats=stats, eff_weight=eff)
    conf, conf_label = _confidence(eff)

    ranked = sorted(stats, key=lambda r: (-r["score"], -r["prior"]))
    best = ranked[0]

    # Patterns
    for r in sorted(stats, key=lambda r: -r["score"]):
        if r["n"]:
            thin = " (thin evidence)" if r["n"] < 2 else ""
            a.patterns.append(
                f"{r['label']}: {r['won']}W / {r['lost']}L / {r['stalled']}S in {r['n']} similar deal(s), "
                f"score {r['score']:.2f} vs playbook {r['prior']:.2f}{thin}")
    if not a.patterns:
        a.patterns.append("No patterns yet: no recalled deal is similar enough to learn from.")

    # Avoid list
    a.avoid = [r for r in stats if r["n"] and r["score"] < r["prior"] - 0.05]

    # Recommendation
    if a.mode == "playbook":
        a.recommendation = {
            "key": None, "label": "Diagnose before you respond (playbook default)",
            "confidence": conf, "confidence_label": conf_label,
            "why": "No similar past deals were recalled, so this is generic guidance, not a learned recommendation.",
            "track": [
                "Ask what they are comparing against and what the price gap actually covers.",
                "Quantify the cost of their status quo before you touch price.",
                "Do not concede a discount until the value case is agreed.",
            ],
        }
    else:
        t = TACTICS[best["key"]]
        moved = best["score"] - best["prior"]
        if best["n"]:
            why = (f"Ranked #1 from {best['n']} similar deal(s): {best['won']}W/{best['lost']}L/{best['stalled']}S, "
                   f"score {best['score']:.2f} (playbook prior {best['prior']:.2f}).")
        else:
            why = (f"No similar deal has tried this yet, but every tactic that was tried scored worse, so the "
                   f"playbook's best untried option ranks first (score {best['score']:.2f}).")
        if a.avoid:
            why += " Deprioritised: " + ", ".join(r["label"] for r in a.avoid) + "."
        a.recommendation = {"key": best["key"], "label": t["label"], "confidence": conf,
                            "confidence_label": conf_label, "why": why, "track": t["track"],
                            "delta_vs_prior": round(moved, 3)}

    # Risk
    rec_score = best["score"]
    risk_score = 1.0 - rec_score
    reasons = []
    if a.deal.competitor and a.deal.competitor.lower() != "none":
        risk_score += 0.10
        reasons.append(f"Active competitor ({a.deal.competitor}) is anchoring on price.")
    if a.deal.stage.lower() in ("negotiation", "contracting"):
        risk_score += 0.05
        reasons.append(f"Late stage ({a.deal.stage}): little room for a slow reframe.")
    if a.mode == "playbook":
        reasons.append("No history: risk is unvalidated, not measured.")
    else:
        losses = [r for r in similar if r["exp"].outcome != "WON"]
        wins = [r for r in similar if r["exp"].outcome == "WON"]
        if losses:
            reasons.append(f"{len(losses)} similar deal(s) were lost or stalled.")
        if wins:
            reasons.append(f"{len(wins)} similar deal(s) were won.")
    risk_score = max(0.0, min(1.0, risk_score))
    a.risk = {"score": round(risk_score, 2),
              "level": "Low" if risk_score < 0.35 else "Medium" if risk_score < 0.6 else "High",
              "reasons": reasons}

    # Evidence
    rec_key = a.recommendation.get("key")
    for r in similar:
        e = r["exp"]
        if rec_key is None:
            signal = "context"
        elif e.tactic == rec_key:
            signal = "supports" if e.outcome == "WON" else "cautions"
        else:
            signal = "supports" if e.outcome in ("LOST", "STALLED") else "context"
        a.evidence.append({"memory_id": e.memory_id, "company": e.company, "tactic": TACTICS[e.tactic]["label"],
                           "outcome": e.outcome, "similarity": r["sim"], "matched": r["matched"],
                           "lesson": e.lesson, "signal": signal})
    return a


def make_lesson(deal: Deal, tactic: str, outcome: str, note: str = "") -> str:
    t = TACTICS[tactic]["label"]
    ctx = f"{deal.industry} {deal.size} deal with {deal.competitor} pushing on price, buyer role {deal.role}"
    if outcome == "WON":
        base = f"'{t}' won a {ctx}. Repeat it for similar deals."
    elif outcome == "LOST":
        base = f"'{t}' lost a {ctx}. Do not lead with it next time."
    else:
        base = f"'{t}' stalled a {ctx}. It needs a forcing event (exec sponsor, deadline) alongside it."
    return base + (f" Rep note: {note.strip()}" if note.strip() else "")


def experience_text(deal: Deal, tactic: str, outcome: str, lesson: str) -> str:
    return (f"Deal {deal.company} ({deal.industry}, {deal.size}, ${deal.value:,}) hit a {deal.objection} objection. "
            f"Competitor: {deal.competitor}. Buyer role: {deal.role}. Tactic used: {TACTICS[tactic]['label']}. "
            f"Outcome: {outcome}. Lesson: {lesson}")


def experience_metadata(deal: Deal, tactic: str, outcome: str, lesson: str) -> dict[str, str]:
    return {**deal.profile(), "deal_id": deal.deal_id, "company": deal.company, "tactic": tactic,
            "outcome": outcome, "lesson": lesson, "value": str(deal.value)}
