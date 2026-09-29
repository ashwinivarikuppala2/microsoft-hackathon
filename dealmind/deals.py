"""Synthetic historical deals: loading, validation, and memory formatting.

The JSON file is only the *seed source* that gets written into Hindsight with
retain. It is never searched locally. Retrieval always goes through Hindsight
(see retrieval.py). Records are also used to render evidence cards for deals
that Hindsight surfaced.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEALS_PATH = Path(__file__).parent / "data" / "historical_deals.json"

REQUIRED_FIELDS = (
    "id", "customer", "industry", "product", "value", "stage", "competitor",
    "objection", "stakeholder_concern", "pricing_discussion", "approach",
    "outcome", "outcome_reason", "date",
)
OUTCOMES = ("Won", "Lost", "Stalled", "No Decision")


def load_deals(path: Path | str | None = None) -> list[dict]:
    """Load and validate the synthetic historical deals."""
    with open(path or DEALS_PATH, encoding="utf-8") as f:
        deals = json.load(f)
    validate_deals(deals)
    return deals


def validate_deals(deals: list[dict]) -> None:
    seen: set[str] = set()
    for d in deals:
        missing = [k for k in REQUIRED_FIELDS if d.get(k) in (None, "")]
        if missing:
            raise ValueError(f"Deal {d.get('id', '?')} missing fields: {missing}")
        if d["id"] in seen:
            raise ValueError(f"Duplicate deal id: {d['id']}")
        seen.add(d["id"])
        if d["outcome"] not in OUTCOMES:
            raise ValueError(f"Deal {d['id']} has invalid outcome: {d['outcome']}")
        if not isinstance(d["value"], (int, float)) or d["value"] <= 0:
            raise ValueError(f"Deal {d['id']} has invalid value: {d['value']}")
        datetime.strptime(d["date"], "%Y-%m-%d")  # raises on bad format


def deal_index(deals: list[dict]) -> dict[str, dict]:
    return {d["id"]: d for d in deals}


def option_values(deals: list[dict], field: str) -> list[str]:
    """Sorted distinct values of a field (used to populate form dropdowns)."""
    return sorted({d[field] for d in deals})


def deal_to_memory_text(d: dict) -> str:
    """Render a deal as prose for Hindsight to extract facts from.

    Hindsight stores extracted facts, not whole documents, so every sentence
    names the customer and the deal id. That keeps each recalled fact
    attributable to its deal.
    """
    c, i = d["customer"], d["id"]
    return " ".join([
        f"Deal {i}: {c} is a {d['industry']} customer that evaluated {d['product']} "
        f"in a deal worth ${d['value']:,} (stage: {d['stage']}, date: {d['date']}).",
        f"In deal {i} ({c}), the competitor was {d['competitor']}.",
        f"In deal {i} ({c}), the main objection was: {d['objection']}",
        f"In deal {i} ({c}), the stakeholder concern was: {d['stakeholder_concern']}",
        f"In deal {i} ({c}), the pricing discussion was: {d['pricing_discussion']}",
        f"In deal {i} ({c}), the sales approach used was: {d['approach']}",
        f"Outcome of deal {i} ({c}): {d['outcome']}.",
        f"Reason for the {d['outcome']} outcome in deal {i} ({c}): {d['outcome_reason']}",
    ])


def deal_metadata(d: dict) -> dict[str, str]:
    """String-only metadata stored alongside the memory in Hindsight."""
    return {
        "deal_id": d["id"],
        "customer": d["customer"],
        "industry": d["industry"],
        "product": d["product"],
        "competitor": d["competitor"],
        "outcome": d["outcome"],
        "date": d["date"],
    }


def deal_timestamp(d: dict) -> datetime:
    """When the deal happened (so Hindsight can place it in time)."""
    return datetime.strptime(d["date"], "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)


def normalize_outcome(outcome: str) -> str:
    """Normalize outcome strings, mapping 'No Decision' to 'Stalled'."""
    val = (outcome or "").strip()
    if val.lower() in ("no decision", "stalled", "stall"):
        return "Stalled"
    if val.lower() == "won":
        return "Won"
    if val.lower() == "lost":
        return "Lost"
    return val

