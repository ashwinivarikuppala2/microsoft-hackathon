"""DealMind Intelligence Engine.

Derives objection patterns, competitor patterns, deal-risk analysis,
recommendations, Hindsight evidence, and evidence-based playbooks from
the current deal plus recalled Hindsight memories.

The key flow is:

    Current Deal
        ↓
    Hindsight Recall
        ↓
    Similar Historical Deals
        ↓
    Hindsight Memories attached to each deal
        ↓
    Evidence-Based Playbook
        ↓
    Recommendations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dealmind.deals import normalize_outcome
from dealmind.retrieval import (
    CurrentDeal,
    DealEvidence,
    RetrievalResult,
    find_similar_deals,
)


SIMILARITY_THRESHOLD = 0.55


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class ObjectionPattern:
    category: str
    description: str
    similar_deals_count: int = 0
    won_count: int = 0
    lost_count: int = 0
    stalled_count: int = 0
    win_rate: float = 0.0
    winning_approaches: list[str] = field(default_factory=list)
    pitfalls_and_traps: list[str] = field(default_factory=list)
    deal_ids: list[str] = field(default_factory=list)


@dataclass
class CompetitorPattern:
    competitor_name: str
    matchups_count: int = 0
    won_count: int = 0
    lost_count: int = 0
    stalled_count: int = 0
    win_rate: float = 0.0
    playbook: str = ""
    winning_counters: list[str] = field(default_factory=list)
    vulnerabilities: list[str] = field(default_factory=list)
    deal_ids: list[str] = field(default_factory=list)


@dataclass
class RiskFactor:
    title: str
    severity: str
    rationale: str
    evidence_citation: str = ""


@dataclass
class DealRiskAnalysis:
    level: str
    score: int
    summary: str
    risk_factors: list[RiskFactor] = field(default_factory=list)
    mitigating_factors: list[str] = field(default_factory=list)


@dataclass
class ActionRecommendation:
    action_type: str
    headline: str
    detailed_guidance: str
    historical_evidence: list[str] = field(default_factory=list)
    why_it_works: str = ""


@dataclass
class DealPlaybook:
    """Hindsight-backed playbook for one recommended historical deal."""

    deal_id: str

    # Actual memories recalled from Hindsight for this historical deal.
    hindsight_memory: list[str] = field(default_factory=list)

    # What the historical deal shows worked.
    worked: list[str] = field(default_factory=list)

    # Lessons from unsuccessful historical deals.
    avoid: list[str] = field(default_factory=list)

    # Actions relevant to the current opportunity.
    recommended_actions: list[str] = field(default_factory=list)

    # Historical outcome.
    outcome: str = ""

    # Why this historical deal is relevant.
    relevance: str = ""


@dataclass
class IntelligenceReport:
    deal: CurrentDeal
    retrieval: RetrievalResult

    objection_patterns: list[ObjectionPattern] = field(
        default_factory=list
    )

    competitor_patterns: list[CompetitorPattern] = field(
        default_factory=list
    )

    risk_analysis: DealRiskAnalysis | None = None

    recommendations: list[ActionRecommendation] = field(
        default_factory=list
    )

    # Hindsight-backed playbook for every recommended historical deal.
    deal_playbooks: list[DealPlaybook] = field(
        default_factory=list
    )


# ============================================================
# OBJECTION CATEGORIES
# ============================================================

OBJECTION_CATEGORIES = {
    "Price & Commercial Terms": [
        "price",
        "cheaper",
        "discount",
        "expensive",
        "cost",
        "budget",
        "quote",
        "rate",
        "undercut",
        "license",
        "fee",
        "per-seat",
        "capex",
        "pricing",
    ],
    "Security, Privacy & Compliance": [
        "security",
        "hipaa",
        "gdpr",
        "compliance",
        "ciso",
        "privacy",
        "soc 2",
        "audit",
        "gxp",
        "validation",
        "data transfer",
        "questionnaire",
    ],
    "Adoption & Change Fatigue": [
        "adopt",
        "adoption",
        "training",
        "fatigue",
        "complex",
        "sprawl",
        "in-house",
        "spreadsheets",
        "burden",
        "team",
        "internal",
    ],
    "Implementation & Timeline": [
        "timeline",
        "long",
        "go-live",
        "go live",
        "months",
        "deploy",
        "disrupt",
        "delay",
        "shipping",
        "peak-season",
        "peak season",
        "schedule",
        "rollout",
    ],
    "Integrations & Technical Parity": [
        "integrate",
        "integration",
        "connector",
        "tms",
        "api",
        "parity",
        "workflow",
        "feature",
    ],
    "Lock-in & Contract Terms": [
        "lock-in",
        "term",
        "contract",
        "viability",
        "unproven",
        "flexible",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def _classify_text_category(text: str) -> str:
    lowered = (text or "").lower()

    for category, keywords in OBJECTION_CATEGORIES.items():
        for keyword in keywords:
            if re.search(
                rf"\b{re.escape(keyword)}",
                lowered,
            ):
                return category

    return "Value Proposition & Fit"


def _similar_records(
    evidence: list[DealEvidence],
) -> list[dict]:
    """Return only historical records above the similarity threshold."""

    return [
        item.record
        for item in evidence
        if (
            item.record
            and item.similarity_score >= SIMILARITY_THRESHOLD
        )
    ]


def _similar_evidence(
    evidence: list[DealEvidence],
) -> list[DealEvidence]:
    """Return only strong historical evidence."""

    return [
        item
        for item in evidence
        if (
            item.record
            and item.similarity_score >= SIMILARITY_THRESHOLD
        )
    ]


def _safe_text(value) -> str:
    """Convert optional historical fields safely to text."""

    if value is None:
        return ""

    return str(value).strip()


def _normalize_label(value: str) -> str:
    """Normalize competitor/customer labels for comparisons."""

    return re.sub(
        r"[^a-z0-9]",
        "",
        (value or "").lower(),
    )


# ============================================================
# HINDSIGHT MEMORY + DEAL PLAYBOOK
# ============================================================

def build_deal_playbook(
    evidence: DealEvidence,
    current_deal: CurrentDeal,
) -> DealPlaybook:
    """Build a Hindsight-backed playbook for one historical deal.

    The hindsight_memory field comes directly from Hindsight memories
    attached to this historical deal.

    Recommendations are derived from the historical record and its
    outcome. No historical event is invented when evidence is missing.
    """

    record = evidence.record or {}

    outcome = normalize_outcome(
        _safe_text(record.get("outcome"))
    )

    # --------------------------------------------------------
    # 1. HINDSIGHT MEMORY
    # --------------------------------------------------------

    hindsight_memory: list[str] = []

    for memory in evidence.memories:
        text = _safe_text(
            getattr(memory, "text", "")
        )

        if text and text not in hindsight_memory:
            hindsight_memory.append(text)

    # --------------------------------------------------------
    # 2. HISTORICAL FIELDS
    # --------------------------------------------------------

    objection = _safe_text(
        record.get("objection")
    )

    stakeholder = _safe_text(
        record.get("stakeholder_concern")
    )

    pricing = _safe_text(
        record.get("pricing_discussion")
    )

    approach = _safe_text(
        record.get("approach")
    )

    outcome_reason = _safe_text(
        record.get("outcome_reason")
    )

    competitor = _safe_text(
        record.get("competitor")
    )

    # --------------------------------------------------------
    # 3. WHAT WORKED
    # --------------------------------------------------------

    worked: list[str] = []

    if outcome == "Won":

        if approach:
            worked.append(
                f"Historical winning approach: {approach}"
            )

        if outcome_reason:
            worked.append(
                f"Why it worked: {outcome_reason}"
            )

        if objection:
            worked.append(
                f"The deal successfully addressed this objection: "
                f"{objection}"
            )

        if stakeholder:
            worked.append(
                f"Stakeholder concern addressed: {stakeholder}"
            )

        if pricing:
            worked.append(
                f"Historical pricing approach: {pricing}"
            )

    # --------------------------------------------------------
    # 4. WHAT TO AVOID
    # --------------------------------------------------------

    avoid: list[str] = []

    if outcome in ("Lost", "Stalled"):

        if approach:
            avoid.append(
                f"Review this historical approach carefully: {approach}"
            )

        if outcome_reason:
            avoid.append(
                f"Historical {outcome.lower()} reason: "
                f"{outcome_reason}"
            )

        if pricing:
            avoid.append(
                f"Pricing lesson: {pricing}"
            )

    if outcome == "Won" and pricing:
        pricing_lower = pricing.lower()

        if any(
            word in pricing_lower
            for word in (
                "discount",
                "cut",
                "cheaper",
                "lower",
            )
        ):
            avoid.append(
                "Do not assume the historical pricing outcome "
                "can be repeated without the same commercial conditions."
            )

    # --------------------------------------------------------
    # 5. RECOMMENDED ACTIONS
    # --------------------------------------------------------

    recommended_actions: list[str] = []

    current_objection = _safe_text(
        current_deal.objection
    )

    current_stakeholder = _safe_text(
        current_deal.stakeholder_concern
    )

    current_pricing = _safe_text(
        current_deal.pricing_discussion
    )

    if current_objection and objection:

        current_words = set(
            re.findall(
                r"[a-z0-9]{4,}",
                current_objection.lower(),
            )
        )

        historical_words = set(
            re.findall(
                r"[a-z0-9]{4,}",
                objection.lower(),
            )
        )

        overlap = current_words & historical_words

        if overlap:
            recommended_actions.append(
                "Use this historical deal as a reference for "
                "handling the current objection."
            )

    if current_stakeholder and stakeholder:

        current_words = set(
            re.findall(
                r"[a-z0-9]{4,}",
                current_stakeholder.lower(),
            )
        )

        historical_words = set(
            re.findall(
                r"[a-z0-9]{4,}",
                stakeholder.lower(),
            )
        )

        if current_words & historical_words:
            recommended_actions.append(
                "Reuse the stakeholder-alignment pattern from "
                "this historical deal."
            )

    current_combined = (
        f"{current_objection} "
        f"{current_stakeholder}"
    ).lower()

    historical_combined = (
        f"{objection} "
        f"{stakeholder}"
    ).lower()

    operational_terms = (
        "go-live",
        "go live",
        "rollout",
        "implementation",
        "disrupt",
        "peak",
        "shipping",
        "training",
        "adoption",
    )

    if (
        any(
            term in current_combined
            for term in operational_terms
        )
        and any(
            term in historical_combined
            for term in operational_terms
        )
    ):
        recommended_actions.append(
            "Address implementation and operational risk before "
            "moving the conversation primarily to price."
        )

    pricing_pressure = (
        f"{current_pricing} "
        f"{current_objection}"
    ).lower()

    if any(
        term in pricing_pressure
        for term in (
            "discount",
            "cheaper",
            "lower price",
            "match",
            "undercut",
        )
    ):
        if outcome == "Won":
            recommended_actions.append(
                "Review how this historical deal defended value "
                "before offering a large concession."
            )
        elif outcome in ("Lost", "Stalled"):
            recommended_actions.append(
                "Use this historical outcome as a warning before "
                "leading with a price concession."
            )

    if not recommended_actions and approach:
        recommended_actions.append(
            f"Consider the historical approach as a reference: "
            f"{approach}"
        )

    # --------------------------------------------------------
    # 6. RELEVANCE
    # --------------------------------------------------------

    similarity_percent = round(
        evidence.similarity_score * 100
    )

    relevance_parts = [
        f"{similarity_percent}% similarity"
    ]

    if competitor:
        relevance_parts.append(
            f"same competitor: {competitor}"
        )

    if objection:
        relevance_parts.append(
            "related objection"
        )

    if stakeholder:
        relevance_parts.append(
            "related stakeholder concern"
        )

    relevance = (
        "Recommended because it matches the current opportunity "
        "on "
        + ", ".join(relevance_parts)
        + "."
    )

    return DealPlaybook(
        deal_id=evidence.deal_id,
        hindsight_memory=hindsight_memory[:5],
        worked=worked[:4],
        avoid=avoid[:4],
        recommended_actions=recommended_actions[:4],
        outcome=outcome,
        relevance=relevance,
    )


def build_deal_playbooks(
    current_deal: CurrentDeal,
    evidence: list[DealEvidence],
) -> list[DealPlaybook]:
    """Create one Hindsight/playbook object per recommended deal."""

    return [
        build_deal_playbook(
            item,
            current_deal,
        )
        for item in _similar_evidence(evidence)
    ]


def playbook_by_deal_id(
    playbooks: list[DealPlaybook],
) -> dict[str, DealPlaybook]:
    """Return playbooks indexed by historical deal ID.

    This makes it easy for the UI to display the correct Hindsight
    evidence and evidence-based playbook inside each recommended deal.
    """

    return {
        playbook.deal_id: playbook
        for playbook in playbooks
    }


# ============================================================
# OBJECTION PATTERNS
# ============================================================

def detect_objection_patterns(
    current_deal: CurrentDeal,
    evidence: list[DealEvidence],
) -> list[ObjectionPattern]:

    current_cat = (
        _classify_text_category(current_deal.objection)
        if current_deal.objection
        else "Price & Commercial Terms"
    )

    category_deals: dict[str, list[dict]] = {}

    for record in _similar_records(evidence):

        category = _classify_text_category(
            _safe_text(record.get("objection"))
        )

        category_deals.setdefault(
            category,
            [],
        ).append(record)

    if (
        current_cat not in category_deals
        and current_deal.objection
    ):
        category_deals[current_cat] = []

    patterns: list[ObjectionPattern] = []

    for category, deals in category_deals.items():

        won = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Won"
        ]

        lost = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Lost"
        ]

        stalled = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Stalled"
        ]

        total = len(deals)

        win_rate = (
            len(won) / total
            if total
            else 0.0
        )

        winning_approaches = [
            (
                f"Deal {d['id']} "
                f"({d['customer']}): "
                f"{_safe_text(d.get('approach'))}"
            )
            for d in won
            if _safe_text(d.get("approach"))
        ]

        pitfalls = [
            (
                f"Deal {d['id']} "
                f"({d['customer']}): "
                f"Approach '{_safe_text(d.get('approach'))}' "
                f"-> Lost because: "
                f"{_safe_text(d.get('outcome_reason'))}"
            )
            for d in lost
        ]

        pitfalls += [
            (
                f"Deal {d['id']} "
                f"({d['customer']}): "
                f"Approach '{_safe_text(d.get('approach'))}' "
                f"-> Stalled: "
                f"{_safe_text(d.get('outcome_reason'))}"
            )
            for d in stalled
        ]

        if category == "Price & Commercial Terms":

            description = (
                "Buyers use competitor pricing to "
                "pressure commercial terms."
            )

            if not pitfalls and not winning_approaches:
                winning_approaches.append(
                    "Defend value using quantified ROI "
                    "and a total-cost-of-ownership model."
                )

        elif category == "Security, Privacy & Compliance":

            description = (
                "Security and compliance stakeholders "
                "require early proof and governance evidence."
            )

            if not pitfalls and not winning_approaches:
                winning_approaches.append(
                    "Address compliance requirements early "
                    "with documentation and a security workshop."
                )

        elif category == "Adoption & Change Fatigue":

            description = (
                "Stakeholders are concerned about adoption "
                "burden, training, or tool sprawl."
            )

            if not pitfalls and not winning_approaches:
                winning_approaches.append(
                    "Use a smaller initial scope with "
                    "onboarding and measurable pilot milestones."
                )

        elif category == "Implementation & Timeline":

            description = (
                "Operational stakeholders are concerned "
                "about implementation and business disruption."
            )

            if not pitfalls and not winning_approaches:
                winning_approaches.append(
                    "Use a phased rollout with explicit "
                    "go-live milestones."
                )

        else:

            description = (
                f"Historical objections related to "
                f"{category.lower()}."
            )

        patterns.append(
            ObjectionPattern(
                category=category,
                description=description,
                similar_deals_count=total,
                won_count=len(won),
                lost_count=len(lost),
                stalled_count=len(stalled),
                win_rate=win_rate,
                winning_approaches=winning_approaches[:3],
                pitfalls_and_traps=pitfalls[:3],
                deal_ids=[
                    d["id"]
                    for d in deals
                ],
            )
        )

    patterns.sort(
        key=lambda pattern: (
            0
            if pattern.category == current_cat
            else 1,
            -pattern.similar_deals_count,
        )
    )

    return patterns


# ============================================================
# COMPETITOR PATTERNS
# ============================================================

def detect_competitor_patterns(
    current_deal: CurrentDeal,
    evidence: list[DealEvidence],
) -> list[CompetitorPattern]:

    target_competitor = _normalize_label(
        current_deal.competitor
    )

    competitor_groups: dict[str, list[dict]] = {}

    for record in _similar_records(evidence):

        competitor = (
            _safe_text(
                record.get(
                    "competitor",
                    "Other",
                )
            )
            or "Other"
        )

        competitor_groups.setdefault(
            competitor,
            [],
        ).append(record)

    patterns: list[CompetitorPattern] = []

    matched_exact = False

    for competitor_name, deals in competitor_groups.items():

        normalized_competitor = _normalize_label(
            competitor_name
        )

        is_target = (
            bool(target_competitor)
            and (
                target_competitor in normalized_competitor
                or normalized_competitor in target_competitor
            )
        )

        if is_target:
            matched_exact = True

        won = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Won"
        ]

        lost = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Lost"
        ]

        stalled = [
            d
            for d in deals
            if normalize_outcome(
                _safe_text(d.get("outcome"))
            ) == "Stalled"
        ]

        total = len(deals)

        win_rate = (
            len(won) / total
            if total
            else 0.0
        )

        playbook_signals = [
            _safe_text(d.get("objection"))
            for d in deals
        ]

        playbook_signals += [
            _safe_text(d.get("pricing_discussion"))
            for d in deals
        ]

        playbook_text = " · ".join(
            signal
            for signal in playbook_signals
            if signal
        )[:220]

        if not playbook_text:
            playbook_text = (
                f"Historical positioning against "
                f"{competitor_name}."
            )

        winning_counters = [
            (
                f"Deal {d['id']} "
                f"({d['customer']}): "
                f"{_safe_text(d.get('approach'))}"
            )
            for d in won
        ]

        vulnerabilities = [
            (
                f"Deal {d['id']} "
                f"({d['customer']}): "
                f"{_safe_text(d.get('outcome_reason'))}"
            )
            for d in (lost + stalled)
        ]

        patterns.append(
            CompetitorPattern(
                competitor_name=competitor_name,
                matchups_count=total,
                won_count=len(won),
                lost_count=len(lost),
                stalled_count=len(stalled),
                win_rate=win_rate,
                playbook=playbook_text,
                winning_counters=winning_counters[:3],
                vulnerabilities=vulnerabilities[:3],
                deal_ids=[
                    d["id"]
                    for d in deals
                ],
            )
        )

    if target_competitor and not matched_exact:

        patterns.insert(
            0,
            CompetitorPattern(
                competitor_name=_safe_text(
                    current_deal.competitor
                ),
                matchups_count=0,
                won_count=0,
                lost_count=0,
                stalled_count=0,
                win_rate=0.0,
                playbook=(
                    "No strong historical matchup was found "
                    "for this competitor."
                ),
                winning_counters=[
                    "Use the current buyer's stated criteria "
                    "to establish value and differentiation."
                ],
                vulnerabilities=[
                    "Do not assume competitor pricing "
                    "or capabilities without evidence."
                ],
                deal_ids=[],
            ),
        )

    patterns.sort(
        key=lambda pattern: (
            0
            if (
                target_competitor
                and (
                    target_competitor
                    in _normalize_label(
                        pattern.competitor_name
                    )
                )
            )
            else 1,
            -pattern.matchups_count,
        )
    )

    return patterns


# ============================================================
# DEAL RISK
# ============================================================

def analyze_deal_risk(
    current_deal: CurrentDeal,
    evidence: list[DealEvidence],
    objection_patterns: list[ObjectionPattern],
    competitor_patterns: list[CompetitorPattern],
) -> DealRiskAnalysis:

    risk_factors: list[RiskFactor] = []
    mitigating_factors: list[str] = []

    score = 30

    recalled_records = _similar_records(evidence)

    won_records = [
        record
        for record in recalled_records
        if normalize_outcome(
            _safe_text(record.get("outcome"))
        ) == "Won"
    ]

    lost_records = [
        record
        for record in recalled_records
        if normalize_outcome(
            _safe_text(record.get("outcome"))
        ) == "Lost"
    ]

    if recalled_records:

        win_rate = (
            len(won_records)
            / len(recalled_records)
        )

        if win_rate < 0.40:

            score += 25

            lost_ids = ", ".join(
                record["id"]
                for record in lost_records[:3]
            )

            risk_factors.append(
                RiskFactor(
                    title="Low Win Rate in Similar Deals",
                    severity="High",
                    rationale=(
                        f"{len(won_records)} of "
                        f"{len(recalled_records)} "
                        f"similar historical deals "
                        f"were Won ({win_rate:.0%})."
                    ),
                    evidence_citation=(
                        f"Historical deals: {lost_ids}"
                        if lost_ids
                        else "Historical similar-deal cohort"
                    ),
                )
            )

        elif win_rate >= 0.70:

            score -= 15

            won_ids = ", ".join(
                record["id"]
                for record in won_records[:3]
            )

            mitigating_factors.append(
                (
                    f"Similar-deal win rate is "
                    f"{win_rate:.0%} "
                    f"across {won_ids}."
                )
            )

    target_competitor = _normalize_label(
        current_deal.competitor
    )

    matched_competitor = None

    for pattern in competitor_patterns:

        if not target_competitor:
            continue

        normalized_name = _normalize_label(
            pattern.competitor_name
        )

        if (
            target_competitor in normalized_name
            or normalized_name in target_competitor
        ):
            matched_competitor = pattern
            break

    if (
        matched_competitor
        and matched_competitor.matchups_count > 0
    ):

        if matched_competitor.win_rate < 0.50:

            score += 20

            citations = ", ".join(
                matched_competitor.deal_ids[:2]
            )

            risk_factors.append(
                RiskFactor(
                    title=(
                        "Competitive Pressure in "
                        f"{matched_competitor.competitor_name} "
                        "Deals"
                    ),
                    severity="High",
                    rationale=(
                        f"Historical win rate in this "
                        f"similar competitor cohort was "
                        f"{matched_competitor.win_rate:.0%}."
                    ),
                    evidence_citation=(
                        f"Historical deals: {citations}"
                    ),
                )
            )

        elif matched_competitor.win_rate >= 0.65:

            score -= 10

            mitigating_factors.append(
                (
                    f"Similar historical deals against "
                    f"{matched_competitor.competitor_name} "
                    f"had a {matched_competitor.win_rate:.0%} "
                    "win rate."
                )
            )

    pricing_text = (
        current_deal.pricing_discussion
        or ""
    ).lower()

    objection_text = (
        current_deal.objection
        or ""
    ).lower()

    discount_requested = any(
        keyword in pricing_text
        for keyword in (
            "discount",
            "cut",
            "match",
            "concession",
            "cheaper",
        )
    )

    cheaper_objection = (
        "cheaper" in objection_text
        or "lower" in objection_text
    )

    if discount_requested or cheaper_objection:

        score += 20

        discount_losses = [
            record
            for record in recalled_records
            if normalize_outcome(
                _safe_text(record.get("outcome"))
            ) in ("Lost", "Stalled")
            and any(
                keyword
                in (
                    _safe_text(
                        record.get(
                            "pricing_discussion",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "objection",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "approach",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "outcome_reason",
                            "",
                        )
                    )
                ).lower()
                for keyword in (
                    "discount",
                    "cut",
                    "cheaper",
                    "undercut",
                    "price",
                    "commodity",
                )
            )
        ]

        target_discount_deals = (
            discount_losses
            or lost_records
        )

        citation = " and ".join(
            (
                f"Deal {record['id']} "
                f"({record['customer']}, "
                f"{normalize_outcome(record.get('outcome', ''))})"
            )
            for record in target_discount_deals[:2]
        )

        risk_factors.append(
            RiskFactor(
                title="Competitive Price Pressure",
                severity="High",
                rationale=(
                    "The buyer is comparing against a lower "
                    "competitor price or requesting a discount."
                ),
                evidence_citation=citation,
            )
        )

    if current_deal.stage in (
        "Security Review",
        "Procurement",
        "Legal Review",
    ):

        stakeholder_text = (
            current_deal.stakeholder_concern
            or ""
        ).lower()

        governance_terms = (
            "ciso",
            "security",
            "hipaa",
            "audit",
            "compliance",
            "privacy",
            "procurement",
            "legal",
        )

        if any(
            term in stakeholder_text
            or term in objection_text
            for term in governance_terms
        ):

            score += 15

            risk_factors.append(
                RiskFactor(
                    title="Late-Stage Governance Risk",
                    severity="Medium",
                    rationale=(
                        "Security, compliance, procurement, "
                        "or legal concerns are active late "
                        "in the deal."
                    ),
                    evidence_citation=(
                        "Current opportunity buyer signal"
                    ),
                )
            )

    concern_text = (
        current_deal.stakeholder_concern
        or ""
    ).lower()

    operational_terms = (
        "adoption",
        "training",
        "sprawl",
        "busy",
        "workflow",
        "disrupt",
        "staff",
        "rollout",
        "go-live",
        "go live",
        "peak",
    )

    if any(
        term in concern_text
        for term in operational_terms
    ):

        score += 10

        operational_deals = [
            record
            for record in recalled_records
            if any(
                term
                in (
                    _safe_text(
                        record.get(
                            "stakeholder_concern",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "objection",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "approach",
                            "",
                        )
                    )
                    + " "
                    + _safe_text(
                        record.get(
                            "outcome_reason",
                            "",
                        )
                    )
                ).lower()
                for term in operational_terms
            )
        ]

        citation = " and ".join(
            (
                f"Deal {record['id']} "
                f"({record['customer']})"
            )
            for record in operational_deals[:2]
        )

        risk_factors.append(
            RiskFactor(
                title=(
                    "Operational Adoption / "
                    "Implementation Concern"
                ),
                severity="Medium",
                rationale=(
                    "An operational stakeholder is concerned "
                    "about disruption, adoption, or rollout."
                ),
                evidence_citation=(
                    citation
                    or "Current buyer signal"
                ),
            )
        )

    final_score = max(
        10,
        min(95, score),
    )

    if final_score >= 60:

        level = "HIGH"

        summary = (
            "High Risk: active commercial or stakeholder "
            "pressure requires focused value-defense and "
            "buyer-alignment actions."
        )

    elif final_score >= 35:

        level = "MEDIUM"

        summary = (
            "Moderate Risk: meaningful buyer objections "
            "or commercial pressure are present but have "
            "historical precedents."
        )

    else:

        level = "LOW"

        summary = (
            "Low Risk: the similar historical cohort shows "
            "manageable buyer concerns."
        )

    return DealRiskAnalysis(
        level=level,
        score=final_score,
        summary=summary,
        risk_factors=risk_factors,
        mitigating_factors=mitigating_factors,
    )


# ============================================================
# RECOMMENDATIONS
# ============================================================

def generate_recommendations(
    current_deal: CurrentDeal,
    evidence: list[DealEvidence],
    objection_patterns: list[ObjectionPattern],
    competitor_patterns: list[CompetitorPattern],
    risk: DealRiskAnalysis,
) -> list[ActionRecommendation]:

    recommendations: list[ActionRecommendation] = []

    recalled_records = _similar_records(evidence)

    won_deals = [
        record
        for record in recalled_records
        if normalize_outcome(
            _safe_text(record.get("outcome"))
        ) == "Won"
    ]

    lost_deals = [
        record
        for record in recalled_records
        if normalize_outcome(
            _safe_text(record.get("outcome"))
        ) == "Lost"
    ]

    primary_citations: list[str] = []

    if won_deals:

        for deal in won_deals[:2]:

            primary_citations.append(
                (
                    f"Deal {deal['id']} "
                    f"({deal['customer']}, Won): "
                    f"{_safe_text(deal.get('approach'))} — "
                    f"{_safe_text(deal.get('outcome_reason'))}"
                )
            )

        headline = (
            "Lead with the proven winning approach"
        )

        guidance = (
            f"Similar {current_deal.industry} deals "
            "show that the sales approach used in the "
            "winning historical cohort should be tested "
            "before making a broad price concession."
        )

        why = (
            "The recommendation is grounded in the "
            "outcomes of the closest historical matches."
        )

    elif recalled_records:

        for record in recalled_records[:2]:

            outcome = normalize_outcome(
                _safe_text(record.get("outcome"))
            )

            primary_citations.append(
                (
                    f"Deal {record['id']} "
                    f"({record['customer']}, {outcome}): "
                    f"{_safe_text(record.get('approach'))} — "
                    f"{_safe_text(record.get('outcome_reason'))}"
                )
            )

        headline = (
            "Build the business case before final pricing"
        )

        guidance = (
            "Use the closest historical deals to establish "
            "ROI, buyer success criteria, and implementation "
            "confidence before final commercial concessions."
        )

        why = (
            "This keeps the conversation tied to the buyer's "
            "business case instead of only the competitor quote."
        )

    else:

        primary_citations.append(
            "No strong historical matches were found."
        )

        headline = (
            "Establish buyer-specific success criteria"
        )

        guidance = (
            "No strong historical precedent was found. "
            "Use the current buyer signals, product knowledge, "
            "and company policy to establish the business case."
        )

        why = (
            "This is a first-deal situation, so the system "
            "should not invent historical precedent."
        )

    recommendations.append(
        ActionRecommendation(
            action_type="Primary Strategy",
            headline=headline,
            detailed_guidance=guidance,
            historical_evidence=primary_citations,
            why_it_works=why,
        )
    )

    pitfall_citations: list[str] = []

    if lost_deals:

        for deal in lost_deals[:2]:

            pitfall_citations.append(
                (
                    f"Deal {deal['id']} "
                    f"({deal['customer']}, Lost): "
                    f"{_safe_text(deal.get('approach'))} — "
                    f"{_safe_text(deal.get('outcome_reason'))}"
                )
            )

        pitfall_headline = (
            "Avoid repeating the loss pattern"
        )

        pitfall_guidance = (
            "Review the closest lost deals before making "
            "a commercial concession. Identify what happened "
            "after the historical approach was used and "
            "avoid repeating that sequence."
        )

    elif recalled_records:

        pitfall_headline = (
            "Avoid leading with an unsupported discount"
        )

        pitfall_guidance = (
            "Do not make a unilateral discount the first "
            "response to competitor pricing. Tie any "
            "commercial movement to a specific buyer "
            "give-get or business outcome."
        )

        for record in recalled_records[:2]:

            outcome = normalize_outcome(
                _safe_text(record.get("outcome"))
            )

            pitfall_citations.append(
                (
                    f"Deal {record['id']} "
                    f"({record['customer']}, {outcome}): "
                    f"{_safe_text(record.get('approach'))}"
                )
            )

    else:

        pitfall_headline = (
            "Avoid unsupported commercial assumptions"
        )

        pitfall_guidance = (
            "Do not assume competitor pricing, discounts, "
            "or historical win patterns when there is no "
            "strong historical match."
        )

        pitfall_citations.append(
            "No strong historical match was found."
        )

    recommendations.append(
        ActionRecommendation(
            action_type="Pitfall to Avoid",
            headline=pitfall_headline,
            detailed_guidance=pitfall_guidance,
            historical_evidence=pitfall_citations,
            why_it_works=(
                "Commercial actions should be connected "
                "to evidence and explicit buyer value."
            ),
        )
    )

    concern = (
        current_deal.stakeholder_concern
        or ""
    ).strip()

    concern_citations: list[str] = []

    if concern:

        stakeholder_headline = (
            "Resolve the stakeholder concern before closing"
        )

        stakeholder_matches = []

        concern_terms = set(
            re.findall(
                r"[a-zA-Z]{4,}",
                concern.lower(),
            )
        )

        for record in recalled_records:

            historical_concern = (
                _safe_text(
                    record.get(
                        "stakeholder_concern",
                        "",
                    )
                ).lower()
            )

            overlap = sum(
                1
                for term in concern_terms
                if term in historical_concern
            )

            if overlap > 0:
                stakeholder_matches.append(
                    (
                        overlap,
                        record,
                    )
                )

        stakeholder_matches.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        chosen = [
            record
            for _, record in stakeholder_matches[:2]
        ]

        if not chosen:
            chosen = won_deals[:2]

        for record in chosen:

            outcome = normalize_outcome(
                _safe_text(record.get("outcome"))
            )

            concern_citations.append(
                (
                    f"Deal {record['id']} "
                    f"({record['customer']}, {outcome}): "
                    f"Handled "
                    f"'{_safe_text(record.get('stakeholder_concern'))}' "
                    f"via {_safe_text(record.get('approach'))}"
                )
            )

        if not concern_citations:
            concern_citations.append(
                "No strong historical stakeholder precedent found."
            )

        stakeholder_guidance = (
            f"Address the stated concern directly: "
            f"'{concern}'. "
            "Use a concrete validation plan, milestone, "
            "pilot, or rollout commitment rather than "
            "leaving the concern implicit."
        )

    else:

        stakeholder_headline = (
            "Establish stakeholder alignment"
        )

        stakeholder_guidance = (
            "Confirm operational, technical, and economic "
            "stakeholders before final commercial negotiation."
        )

        for record in won_deals[:2]:

            concern_citations.append(
                (
                    f"Deal {record['id']} "
                    f"({record['customer']}, Won): "
                    f"{_safe_text(record.get('approach'))}"
                )
            )

    recommendations.append(
        ActionRecommendation(
            action_type="Stakeholder Alignment",
            headline=stakeholder_headline,
            detailed_guidance=stakeholder_guidance,
            historical_evidence=concern_citations,
            why_it_works=(
                "The buyer concern is treated as a concrete "
                "deal signal rather than background text."
            ),
        )
    )

    pricing_citations: list[str] = []

    pricing_headline = (
        "Structure any pricing movement around a give-get"
    )

    pricing_guidance = (
        "If pricing flexibility is required, connect it "
        "to a defined commercial exchange such as term, "
        "scope, payment structure, volume, or referenceability."
    )

    pricing_matches = [
        record
        for record in won_deals
        if any(
            keyword
            in (
                _safe_text(
                    record.get(
                        "pricing_discussion",
                        "",
                    )
                )
                + " "
                + _safe_text(
                    record.get(
                        "approach",
                        "",
                    )
                )
            ).lower()
            for keyword in (
                "tier",
                "term",
                "billing",
                "bundle",
                "subscription",
                "discount",
                "price",
                "ramp",
                "pilot",
            )
        )
    ]

    chosen_pricing = (
        pricing_matches
        or won_deals
        or recalled_records
    )

    for record in chosen_pricing[:2]:

        outcome = normalize_outcome(
            _safe_text(record.get("outcome"))
        )

        pricing_citations.append(
            (
                f"Deal {record['id']} "
                f"({record['customer']}, {outcome}): "
                f"{_safe_text(record.get('pricing_discussion'))} "
                f"-> {_safe_text(record.get('approach'))}"
            )
        )

    if not pricing_citations:
        pricing_citations.append(
            "No strong historical pricing precedent found."
        )

    recommendations.append(
        ActionRecommendation(
            action_type="Pricing & Negotiation",
            headline=pricing_headline,
            detailed_guidance=pricing_guidance,
            historical_evidence=pricing_citations,
            why_it_works=(
                "It keeps pricing decisions connected to "
                "explicit commercial value and historical evidence."
            ),
        )
    )

    return recommendations


# ============================================================
# MAIN DEAL INTELLIGENCE ENGINE
# ============================================================

def run_deal_intelligence(
    client,
    bank_id: str,
    deal: CurrentDeal,
    index: dict[str, dict] | None = None,
) -> IntelligenceReport:
    """Execute the complete DealMind intelligence workflow."""

    index = index or {}

    # --------------------------------------------------------
    # STEP 1
    # Hindsight recall + similarity filtering
    # --------------------------------------------------------

    retrieval = find_similar_deals(
        client,
        bank_id,
        deal,
        index,
    )

    # --------------------------------------------------------
    # STEP 2
    # Objection patterns
    # --------------------------------------------------------

    objection_patterns = detect_objection_patterns(
        deal,
        retrieval.evidence,
    )

    # --------------------------------------------------------
    # STEP 3
    # Competitor patterns
    # --------------------------------------------------------

    competitor_patterns = detect_competitor_patterns(
        deal,
        retrieval.evidence,
    )

    # --------------------------------------------------------
    # STEP 4
    # Deal risk
    # --------------------------------------------------------

    risk_analysis = analyze_deal_risk(
        deal,
        retrieval.evidence,
        objection_patterns,
        competitor_patterns,
    )

    # --------------------------------------------------------
    # STEP 5
    # Overall recommendations
    # --------------------------------------------------------

    recommendations = generate_recommendations(
        deal,
        retrieval.evidence,
        objection_patterns,
        competitor_patterns,
        risk_analysis,
    )

    # --------------------------------------------------------
    # STEP 6
    # HINDSIGHT-BACKED PLAYBOOKS
    #
    # One playbook is generated for every recommended
    # historical deal.
    # --------------------------------------------------------

    deal_playbooks = build_deal_playbooks(
        deal,
        retrieval.evidence,
    )

    # --------------------------------------------------------
    # STEP 7
    # FINAL REPORT
    # --------------------------------------------------------

    return IntelligenceReport(
        deal=deal,
        retrieval=retrieval,
        objection_patterns=objection_patterns,
        competitor_patterns=competitor_patterns,
        risk_analysis=risk_analysis,
        recommendations=recommendations,
        deal_playbooks=deal_playbooks,
    )