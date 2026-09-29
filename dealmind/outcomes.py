"""DealMind Outcome Recording and Learning Loop.

Enables recording WON / LOST / STALLED outcomes for current or closed deals,
saving them into Hindsight memory, and closing the learning loop so future
deals immediately benefit from the newly recorded experience.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from dealmind.deals import (
    deal_metadata,
    deal_timestamp,
    deal_to_memory_text,
    normalize_outcome,
)
from dealmind.memory import retain_deal_memory
from dealmind.retrieval import CurrentDeal


@dataclass
class DealOutcome:
    id: str
    customer: str
    industry: str
    product: str
    value: float
    stage: str
    competitor: str
    objection: str
    stakeholder_concern: str
    pricing_discussion: str
    approach: str
    outcome: str  # "Won", "Lost", "Stalled"
    outcome_reason: str
    date: str = ""

    def __post_init__(self):
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.outcome = normalize_outcome(self.outcome)
        if self.outcome not in ("Won", "Lost", "Stalled"):
            raise ValueError(f"Invalid outcome '{self.outcome}'. Must be 'Won', 'Lost', or 'Stalled'.")

    def to_deal_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "customer": self.customer,
            "industry": self.industry,
            "product": self.product,
            "value": float(self.value),
            "stage": self.stage,
            "competitor": self.competitor,
            "objection": self.objection,
            "stakeholder_concern": self.stakeholder_concern,
            "pricing_discussion": self.pricing_discussion,
            "approach": self.approach,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "date": self.date,
        }


def save_deal_outcome(
    client,
    bank_id: str,
    outcome: DealOutcome,
    index: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Save a completed deal outcome into Hindsight memory.
    
    The memory is retained with document_id = outcome.id, so updates are idempotent.
    The in-memory deal index is also updated so subsequent retrievals immediately
    recognize the new record.
    """
    deal_dict = outcome.to_deal_dict()
    memory_text = deal_to_memory_text(deal_dict)
    
    retain_deal_memory(
        client,
        bank_id=bank_id,
        content=memory_text,
        context=f"completed deal outcome ({outcome.outcome})",
        document_id=outcome.id,
        timestamp=deal_timestamp(deal_dict),
        metadata=deal_metadata(deal_dict),
    )

    if index is not None:
        index[outcome.id] = deal_dict

    return {
        "success": True,
        "deal_id": outcome.id,
        "document_id": outcome.id,
        "customer": outcome.customer,
        "outcome": outcome.outcome,
        "memory_text": memory_text,
        "record": deal_dict,
    }


def verify_learning_loop(
    client,
    bank_id: str,
    recorded_outcome: DealOutcome,
    future_deal: CurrentDeal,
    index: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Demonstrate and verify the complete learning loop:
    1. Record & save outcome for a deal.
    2. Query Hindsight for a future deal facing similar context.
    3. Verify that Hindsight recalls the newly recorded deal.
    4. Confirm that the new memory is incorporated into the future deal's intelligence report.
    """
    from dealmind.intelligence import run_deal_intelligence

    # Step 1: Save the outcome to Hindsight memory
    save_result = save_deal_outcome(client, bank_id, recorded_outcome, index=index)

    # Step 2: Run intelligence on the future deal
    report = run_deal_intelligence(client, bank_id, future_deal, index=index)

    # Step 3: Check if the saved deal was recalled
    recalled_ids = [ev.deal_id for ev in report.retrieval.evidence]
    memory_texts = [m.text for m in report.retrieval.memories]
    recalled = (
        recorded_outcome.id in recalled_ids
        or any(recorded_outcome.id in t for t in memory_texts)
        or any(recorded_outcome.customer.lower() in t.lower() for t in memory_texts)
    )

    # Check citation in recommendations or patterns
    cited_in_recs = any(
        recorded_outcome.id in c or recorded_outcome.customer.lower() in c.lower()
        for rec in report.recommendations
        for c in rec.historical_evidence
    )

    return {
        "saved_deal_id": recorded_outcome.id,
        "saved_customer": recorded_outcome.customer,
        "saved_outcome": recorded_outcome.outcome,
        "future_customer": future_deal.customer,
        "recalled_in_future_deal": recalled,
        "recalled_evidence_ids": recalled_ids,
        "cited_in_recommendations": cited_in_recs,
        "total_recalled_memories": len(report.retrieval.memories),
        "intelligence_report": report,
    }
