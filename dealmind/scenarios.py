"""Demo script: the two deals, the question, and one unrelated seed memory."""
from __future__ import annotations

from .engine import Deal, experience_metadata, experience_text

QUESTION = "How should I handle this pricing objection?"

DEAL_A = Deal(
    deal_id="d-1001", company="Northwind Logistics", industry="Logistics", size="Mid-market",
    value=48_000, stage="Negotiation", objection="Pricing", competitor="RouteIQ", role="CFO",
    customer_said="RouteIQ quoted about 20% less. I need a better number before I can sign.",
)

DEAL_B = Deal(
    deal_id="d-1002", company="Contoso Freight", industry="Logistics", size="Mid-market",
    value=52_000, stage="Negotiation", objection="Pricing", competitor="RouteIQ", role="VP Finance",
    customer_said="We like the product, but RouteIQ is cheaper. Can you match their price?",
)

# Deliberately unrelated (security objection, healthcare) so the demo starts with
# "little/no relevant memory": it is recalled at low relevance and ignored by the engine.
_SEED_DEAL = Deal(
    deal_id="d-0901", company="Fabrikam Health", industry="Healthcare", size="Enterprise",
    value=120_000, stage="Security review", objection="Security", competitor="None", role="CISO",
    customer_said="We need your SOC 2 report before legal will proceed.",
)
_SEED_LESSON = "Sharing the SOC 2 report early cleared a security objection. Unrelated to price negotiations."

SEED_MEMORIES = [
    (experience_text(_SEED_DEAL, "proof", "WON", _SEED_LESSON),
     experience_metadata(_SEED_DEAL, "proof", "WON", _SEED_LESSON), _SEED_DEAL.deal_id),
]
