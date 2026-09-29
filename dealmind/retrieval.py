"""DealMind similar-deal retrieval.

Hindsight is the memory layer.

Flow:

    Current Deal
        ↓
    Hindsight Recall
        ↓
    Resolve memories to historical deals
        ↓
    Exclude current customer
        ↓
    Structured similarity scoring
        ↓
    Strong historical matches
        ↓
    Deal-specific Hindsight evidence
        ↓
    Intelligence + Evidence-Based Playbook

The retrieval layer deliberately does NOT return every historical deal.
Only historical deals that Hindsight recalled and that pass the similarity
threshold are exposed as recommended deals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from dealmind.memory import RecalledMemory, recall_memories


# ============================================================
# CONSTANTS
# ============================================================

DEAL_ID_RE = re.compile(r"\bD-\d{3}\b")

STAGES = [
    "Discovery",
    "Demo",
    "Proposal",
    "Security Review",
    "Negotiation",
    "Procurement",
    "Legal Review",
]

# Buyer and opportunity signals are weighted more heavily than
# deal value because behavioral similarity matters more than
# simply finding deals with similar dollar amounts.
SIMILARITY_WEIGHTS = {
    "industry": 0.15,
    "product": 0.20,
    "competitor": 0.15,
    "objection": 0.15,
    "stakeholder_concern": 0.15,
    "pricing_discussion": 0.10,
    "stage": 0.05,
    "value": 0.05,
}

SIMILARITY_THRESHOLD = 0.55
MAX_SIMILAR_DEALS = 5


# ============================================================
# CURRENT DEAL
# ============================================================

@dataclass
class CurrentDeal:
    customer: str = ""
    industry: str = ""
    product: str = ""
    value: float = 0
    stage: str = ""
    competitor: str = ""
    objection: str = ""
    stakeholder_concern: str = ""
    pricing_discussion: str = ""

    def validate(self):
        if not self.customer.strip():
            raise ValueError("Customer is required.")

        if not self.industry.strip():
            raise ValueError("Industry is required.")

        if not self.product.strip():
            raise ValueError("Product is required.")

        if self.value < 0:
            raise ValueError("Deal value cannot be negative.")

        if self.stage and self.stage not in STAGES:
            raise ValueError(
                f"Stage must be one of: {', '.join(STAGES)}"
            )

    def to_query(self) -> str:
        """Build the natural-language query sent to Hindsight."""

        parts = [
            (
                f"Find similar past sales deals involving a "
                f"{self.industry} customer considering {self.product}"
            )
        ]

        if self.value:
            parts[0] += f" worth about ${self.value:,.0f}"

        if self.stage:
            parts[0] += (
                f", currently at the {self.stage} stage"
            )

        parts[0] += "."

        if self.competitor.strip():
            parts.append(
                f"The competitor is {self.competitor.strip()}."
            )

        if self.objection.strip():
            parts.append(
                f"Customer objection: {self.objection.strip()}"
            )

        if self.stakeholder_concern.strip():
            parts.append(
                "Stakeholder concern: "
                f"{self.stakeholder_concern.strip()}"
            )

        if self.pricing_discussion.strip():
            parts.append(
                "Pricing discussion: "
                f"{self.pricing_discussion.strip()}"
            )

        parts.append(
            "Find historical deals with similar buyer signals, "
            "objections, competitors, pricing situations, "
            "stakeholder concerns, and sales approaches. "
            "Return evidence that can support a recommendation."
        )

        return " ".join(parts)


# ============================================================
# DEAL EVIDENCE
# ============================================================

@dataclass
class DealEvidence:
    """One recommended historical deal surfaced by Hindsight."""

    deal_id: str

    record: dict | None

    # Hindsight memories belonging specifically to this deal.
    memories: list[RecalledMemory] = field(
        default_factory=list
    )

    # Overall structured similarity score.
    similarity_score: float = 0.0

    # Individual similarity dimensions.
    similarity_breakdown: dict[str, float] = field(
        default_factory=dict
    )

    # Human-readable explanation of why this deal matched.
    match_reasons: list[str] = field(
        default_factory=list
    )

    @property
    def memory_count(self) -> int:
        """Number of Hindsight memories attached to this deal."""

        return len(self.memories)

    @property
    def hindsight_memory_texts(self) -> list[str]:
        """Clean Hindsight memory text for API/UI consumption."""

        results: list[str] = []

        for memory in self.memories:
            text = (memory.text or "").strip()

            if text and text not in results:
                results.append(text)

        return results


# ============================================================
# RETRIEVAL RESULT
# ============================================================

@dataclass
class RetrievalResult:
    query: str

    # All memories returned by Hindsight for transparency/debugging.
    memories: list[RecalledMemory]

    # ONLY recommended historical deals.
    evidence: list[DealEvidence]

    # Memories that could not be attributed to a historical deal.
    unattributed: list[RecalledMemory]


# ============================================================
# NORMALIZATION
# ============================================================

def _normalize_text(
    value: str | None,
) -> str:
    """Normalize text before comparison."""

    if not value:
        return ""

    value = str(value).lower().strip()

    replacements = {
        "20%": "20 percent",
        "15%": "15 percent",
        "10%": "10 percent",
        "5%": "5 percent",
        "tco": "total cost ownership",
        "go-live": "go live",
        "go_live": "go live",
        "peak-season": "peak season",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# TEXT SIMILARITY
# ============================================================

def _token_similarity(
    a: str,
    b: str,
) -> float:
    """Token/Jaccard similarity."""

    if not a or not b:
        return 0.0

    a_tokens = set(a.split())
    b_tokens = set(b.split())

    if not a_tokens or not b_tokens:
        return 0.0

    intersection = len(
        a_tokens & b_tokens
    )

    union = len(
        a_tokens | b_tokens
    )

    if union == 0:
        return 0.0

    return intersection / union


def _sequence_similarity(
    a: str,
    b: str,
) -> float:
    """Character sequence similarity."""

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


def _text_similarity(
    current_value: str | None,
    historical_value: str | None,
) -> float:
    """Combine token and sequence similarity."""

    current = _normalize_text(
        current_value
    )

    historical = _normalize_text(
        historical_value
    )

    if not current or not historical:
        return 0.0

    if current == historical:
        return 1.0

    token_score = _token_similarity(
        current,
        historical,
    )

    sequence_score = _sequence_similarity(
        current,
        historical,
    )

    return round(
        token_score * 0.60
        + sequence_score * 0.40,
        4,
    )


# ============================================================
# CATEGORICAL SIMILARITY
# ============================================================

def _categorical_similarity(
    current_value: str | None,
    historical_value: str | None,
) -> float:
    """Similarity for industry/product/stage/competitor."""

    current = _normalize_text(
        current_value
    )

    historical = _normalize_text(
        historical_value
    )

    if not current or not historical:
        return 0.0

    if current == historical:
        return 1.0

    return _text_similarity(
        current,
        historical,
    )


# ============================================================
# DEAL VALUE SIMILARITY
# ============================================================

def _value_similarity(
    current_value: float,
    historical_value: float,
) -> float:
    """Soft similarity for deal value."""

    try:
        current = float(
            current_value or 0
        )

        historical = float(
            historical_value or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0.0

    if current <= 0 or historical <= 0:
        return 0.0

    difference = abs(
        current - historical
    )

    denominator = max(
        current,
        historical,
    )

    if denominator == 0:
        return 1.0

    difference_ratio = (
        difference / denominator
    )

    return max(
        0.0,
        1.0 - difference_ratio,
    )


# ============================================================
# SIMILARITY BREAKDOWN
# ============================================================

def calculate_similarity_breakdown(
    current: CurrentDeal,
    historical: dict,
) -> dict[str, float]:
    """Calculate similarity for every deal dimension."""

    return {
        "industry": _categorical_similarity(
            current.industry,
            historical.get("industry"),
        ),

        "product": _categorical_similarity(
            current.product,
            historical.get("product"),
        ),

        "competitor": _categorical_similarity(
            current.competitor,
            historical.get("competitor"),
        ),

        "objection": _text_similarity(
            current.objection,
            historical.get("objection"),
        ),

        "stakeholder_concern": _text_similarity(
            current.stakeholder_concern,
            historical.get(
                "stakeholder_concern"
            ),
        ),

        "pricing_discussion": _text_similarity(
            current.pricing_discussion,
            historical.get(
                "pricing_discussion"
            ),
        ),

        "stage": _categorical_similarity(
            current.stage,
            historical.get("stage"),
        ),

        "value": _value_similarity(
            current.value,
            historical.get("value"),
        ),
    }


def calculate_deal_similarity(
    current: CurrentDeal,
    historical: dict,
) -> float:
    """Calculate weighted similarity between opportunities."""

    scores = calculate_similarity_breakdown(
        current,
        historical,
    )

    total = sum(
        scores[field] * weight
        for field, weight in SIMILARITY_WEIGHTS.items()
    )

    return round(
        total,
        4,
    )


# ============================================================
# MATCH EXPLANATION
# ============================================================

def build_match_reasons(
    current: CurrentDeal,
    historical: dict,
    breakdown: dict[str, float],
) -> list[str]:
    """Create concise reasons explaining why a deal matched."""

    reasons: list[str] = []

    labels = {
        "industry": "same industry",
        "product": "same product",
        "competitor": "same competitor",
        "objection": "similar objection",
        "stakeholder_concern": (
            "similar stakeholder concern"
        ),
        "pricing_discussion": (
            "similar pricing discussion"
        ),
        "stage": "same sales stage",
        "value": "similar deal value",
    }

    # High-confidence matching dimensions first.
    ranked = sorted(
        breakdown.items(),
        key=lambda item: (
            item[1]
            * SIMILARITY_WEIGHTS.get(
                item[0],
                0,
            )
        ),
        reverse=True,
    )

    for field, score in ranked:

        if score < 0.45:
            continue

        label = labels.get(
            field,
            field,
        )

        reasons.append(label)

        if len(reasons) >= 4:
            break

    # Make sure the explanation is useful even when
    # individual fields are weak but the combined score passed.
    if not reasons:

        if (
            _normalize_text(
                current.industry
            )
            == _normalize_text(
                historical.get("industry")
            )
        ):
            reasons.append(
                "same industry"
            )

        if (
            _normalize_text(
                current.product
            )
            == _normalize_text(
                historical.get("product")
            )
        ):
            reasons.append(
                "same product"
            )

    return reasons


# ============================================================
# MEMORY → DEAL RESOLUTION
# ============================================================

def resolve_deal_id(
    memory: RecalledMemory,
    index: dict[str, dict],
) -> str | None:
    """Resolve a Hindsight memory to a historical deal."""

    metadata = memory.metadata or {}

    # --------------------------------------------------------
    # 1. Explicit deal_id metadata
    # --------------------------------------------------------

    candidate = metadata.get(
        "deal_id"
    )

    if candidate in index:
        return candidate

    # --------------------------------------------------------
    # 2. Document ID
    # --------------------------------------------------------

    if memory.document_id in index:
        return memory.document_id

    # --------------------------------------------------------
    # 3. Deal ID in memory text
    # --------------------------------------------------------

    for found in DEAL_ID_RE.findall(
        memory.text or ""
    ):

        if found in index:
            return found

    # --------------------------------------------------------
    # 4. Customer name fallback
    # --------------------------------------------------------

    lowered = (
        memory.text or ""
    ).lower()

    for deal_id, record in index.items():

        customer = str(
            record.get(
                "customer",
                "",
            )
        ).lower().strip()

        if (
            customer
            and customer in lowered
        ):
            return deal_id

    return None


# ============================================================
# MEMORY DEDUPLICATION
# ============================================================

def _memory_key(
    memory: RecalledMemory,
) -> str:
    """Create a stable key for duplicate detection."""

    return "|".join(
        [
            str(
                getattr(
                    memory,
                    "document_id",
                    "",
                )
                or ""
            ),
            str(
                getattr(
                    memory,
                    "text",
                    "",
                )
                or ""
            ).strip(),
        ]
    )


def _append_unique_memory(
    target: list[RecalledMemory],
    memory: RecalledMemory,
) -> None:
    """Attach a memory only once."""

    new_key = _memory_key(
        memory
    )

    for existing in target:

        if _memory_key(existing) == new_key:
            return

    target.append(
        memory
    )


# ============================================================
# MAIN RETRIEVAL
# ============================================================

def find_similar_deals(
    client,
    bank_id: str,
    deal: CurrentDeal,
    index: dict[str, dict] | None = None,
) -> RetrievalResult:
    """Find only strong historical matches.

    Important behavior:

    - Hindsight is always queried first.
    - Historical deals are created only from recalled memories.
    - The current customer is excluded.
    - Similarity is calculated from the actual historical record.
    - Deals below SIMILARITY_THRESHOLD are discarded.
    - Results are sorted by similarity.
    - Only MAX_SIMILAR_DEALS are returned.
    - Every returned deal carries its own Hindsight memories.
    - Every returned deal carries a similarity breakdown and
      human-readable match reasons.

    The function therefore does NOT expose the complete historical
    dataset to the UI.
    """

    index = index or {}

    # --------------------------------------------------------
    # 1. BUILD HINDSIGHT QUERY
    # --------------------------------------------------------

    query = deal.to_query()

    # --------------------------------------------------------
    # 2. HINDSIGHT RECALL
    # --------------------------------------------------------

    memories = recall_memories(
        client,
        bank_id,
        query,
    )

    grouped: dict[
        str,
        DealEvidence,
    ] = {}

    unattributed: list[
        RecalledMemory
    ] = []

    current_customer = (
        deal.customer
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # 3. RESOLVE MEMORIES TO HISTORICAL DEALS
    # --------------------------------------------------------

    for memory in memories:

        deal_id = resolve_deal_id(
            memory,
            index,
        )

        # Hindsight memory could not be connected to
        # a known historical deal.
        if deal_id is None:

            unattributed.append(
                memory
            )

            continue

        historical_record = index.get(
            deal_id
        )

        if not historical_record:
            continue

        historical_customer = str(
            historical_record.get(
                "customer",
                "",
            )
        ).strip().lower()

        # ----------------------------------------------------
        # NEVER RECOMMEND CURRENT CUSTOMER
        # ----------------------------------------------------

        if (
            current_customer
            and historical_customer
            and current_customer
            == historical_customer
        ):
            continue

        # ----------------------------------------------------
        # CREATE DEAL EVIDENCE
        # ----------------------------------------------------

        if deal_id not in grouped:

            grouped[deal_id] = DealEvidence(
                deal_id=deal_id,
                record=historical_record,
                memories=[],
                similarity_score=0.0,
                similarity_breakdown={},
                match_reasons=[],
            )

        # ----------------------------------------------------
        # ATTACH DEAL-SPECIFIC HINDSIGHT MEMORY
        # ----------------------------------------------------

        _append_unique_memory(
            grouped[deal_id].memories,
            memory,
        )

    # --------------------------------------------------------
    # 4. SCORE DEALS
    # --------------------------------------------------------

    scored: list[
        DealEvidence
    ] = []

    for evidence in grouped.values():

        if not evidence.record:
            continue

        breakdown = (
            calculate_similarity_breakdown(
                deal,
                evidence.record,
            )
        )

        similarity = (
            sum(
                breakdown[field] * weight
                for field, weight
                in SIMILARITY_WEIGHTS.items()
            )
        )

        similarity = round(
            similarity,
            4,
        )

        evidence.similarity_score = (
            similarity
        )

        evidence.similarity_breakdown = (
            breakdown
        )

        evidence.match_reasons = (
            build_match_reasons(
                deal,
                evidence.record,
                breakdown,
            )
        )

        # ----------------------------------------------------
        # ONLY STRONG MATCHES
        # ----------------------------------------------------

        if (
            similarity
            >= SIMILARITY_THRESHOLD
        ):
            scored.append(
                evidence
            )

    # --------------------------------------------------------
    # 5. SORT BY RELEVANCE
    # --------------------------------------------------------

    scored.sort(
        key=lambda item: (
            item.similarity_score,
            item.memory_count,
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # 6. RETURN ONLY TOP RECOMMENDED DEALS
    # --------------------------------------------------------

    top_matches = scored[
        :MAX_SIMILAR_DEALS
    ]

    return RetrievalResult(
        query=query,

        # Keep all recalled Hindsight memories available
        # for the technical/debugging view.
        memories=memories,

        # IMPORTANT:
        # This contains ONLY recommended historical deals.
        evidence=top_matches,

        unattributed=unattributed,
    )