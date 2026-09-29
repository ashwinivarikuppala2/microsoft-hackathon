"""DealMind Natural-Language Chat.

Answers questions about live deals and sales history grounded strictly
in recalled Hindsight memories.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from dealmind.deals import normalize_outcome
from dealmind.memory import RecalledMemory, recall_memories
from dealmind.retrieval import CurrentDeal, resolve_deal_id


@dataclass
class ChatResponse:
    answer: str
    recalled_memories: list[RecalledMemory] = field(default_factory=list)
    query_sent: str = ""
    cited_deal_ids: list[str] = field(default_factory=list)


def format_deal_context(deal: CurrentDeal | None) -> str:
    if not deal or not deal.industry:
        return "No specific current deal active."
    return (
        f"Active Deal: {deal.customer or 'Unnamed'} ({deal.industry}, {deal.product}, "
        f"Stage: {deal.stage}, Value: ${deal.value:,.0f}). "
        f"Competitor: {deal.competitor or 'None'}. "
        f"Objection: {deal.objection or 'None'}. "
        f"Stakeholder Concern: {deal.stakeholder_concern or 'None'}."
    )


def synthesize_local_answer(
    question: str,
    memories: list[RecalledMemory],
    current_deal: CurrentDeal | None,
    index: dict[str, dict] | None = None,
) -> str:
    """Intelligent grounded synthesizer that answers strictly from recalled Hindsight facts."""
    if not memories:
        return (
            "I searched Hindsight memory for: *\"" + question + "\"*, but found no matching "
            "deal memories. Please verify that historical deals are loaded into your Hindsight bank."
        )

    index = index or {}
    q_low = question.lower()

    # Identify matching recalled deals
    matched_deals: dict[str, list[str]] = {}
    for m in memories:
        deal_id = resolve_deal_id(m, index) or m.metadata.get("deal_id") or m.document_id or "General"
        matched_deals.setdefault(deal_id, []).append(m.text)

    # Build response sections
    lines = []
    lines.append(f"Based on **{len(memories)} recalled facts** from Hindsight memory:\n")

    # If the user asked about a specific competitor or customer
    specific_mentions = []
    for d_id, facts in matched_deals.items():
        rec = index.get(d_id)
        if rec:
            outcome = rec.get("outcome", "")
            norm = normalize_outcome(outcome)
            badge = f"**{norm}**"
            line = (
                f"- **{rec['customer']}** ({d_id}, {badge}): "
                f"Competitor: {rec.get('competitor')}, Objection: \"{rec.get('objection')}\". "
                f"**Approach used:** {rec.get('approach')}. "
                f"**Outcome reason:** {rec.get('outcome_reason')}"
            )
            specific_mentions.append(line)

    if specific_mentions:
        lines.append("### Relevant Historical Precedents:")
        lines.extend(specific_mentions[:4])
        lines.append("")

    # Strategic takeaway grounded in memories
    won_examples = [
        index[d_id] for d_id in matched_deals
        if d_id in index and normalize_outcome(index[d_id].get("outcome", "")) == "Won"
    ]
    lost_examples = [
        index[d_id] for d_id in matched_deals
        if d_id in index and normalize_outcome(index[d_id].get("outcome", "")) == "Lost"
    ]

    lines.append("### Key Takeaways from Memory:")
    if won_examples:
        w = won_examples[0]
        lines.append(
            f"✅ **Winning Playbook:** In Deal {w['id']} ({w['customer']}), the winning strategy was: "
            f"*{w['approach']}*, which succeeded because *{w['outcome_reason']}*."
        )
    if lost_examples:
        l = lost_examples[0]
        lines.append(
            f"⚠️ **Pitfall to Avoid:** In Deal {l['id']} ({l['customer']}), the deal was lost because: "
            f"*{l['outcome_reason']}* after attempting *{l['approach']}*."
        )

    if not won_examples and not lost_examples:
        lines.append("Relevant memory statements:")
        for m in memories[:4]:
            lines.append(f"- {m.text}")

    return "\n".join(lines)


def chat_with_memory(
    client,
    bank_id: str,
    user_message: str,
    current_deal: CurrentDeal | None = None,
    index: dict[str, dict] | None = None,
    llm_api_key: str | None = None,
) -> ChatResponse:
    """Recall relevant Hindsight memories and generate a grounded conversational response."""
    index = index or {}
    
    # Formulate memory recall query
    query_parts = [user_message.strip()]
    if current_deal:
        if current_deal.competitor:
            query_parts.append(f"competitor {current_deal.competitor}")
        if current_deal.industry:
            query_parts.append(f"industry {current_deal.industry}")
        if current_deal.objection:
            query_parts.append(f"objection {current_deal.objection}")
    recall_query = " ".join(query_parts)

    memories = recall_memories(client, bank_id, recall_query)

    # Find cited deal IDs
    cited_ids = set()
    for m in memories:
        d_id = resolve_deal_id(m, index)
        if d_id:
            cited_ids.add(d_id)

    # Generate answer
    # First check if an LLM is configured (e.g. OpenAI / Gemini)
    api_key = (llm_api_key or os.getenv("LLM_API_KEY", "")).strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if api_key or gemini_key:
        try:
            # If google-genai is available and key is set
            if gemini_key:
                from google import genai
                g_client = genai.Client(api_key=gemini_key)
                prompt = (
                    "You are DealMind Assistant, an evidence-based B2B sales advisor.\n"
                    "Answer the user's question STRICTLY using the recalled Hindsight memories below.\n"
                    "Cite deal IDs (e.g. D-001) and customer names for every claim.\n\n"
                    f"{format_deal_context(current_deal)}\n\n"
                    "RECALLED HINDSIGHT MEMORIES:\n"
                    + "\n".join(f"- {m.text}" for m in memories)
                    + f"\n\nUSER QUESTION: {user_message}"
                )
                res = g_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                answer = res.text
                return ChatResponse(
                    answer=answer,
                    recalled_memories=memories,
                    query_sent=recall_query,
                    cited_deal_ids=sorted(cited_ids),
                )
        except Exception:
            # Fallback to local grounded synthesis if API call fails
            pass

    # Grounded synthesis fallback
    answer = synthesize_local_answer(user_message, memories, current_deal, index)
    return ChatResponse(
        answer=answer,
        recalled_memories=memories,
        query_sent=recall_query,
        cited_deal_ids=sorted(cited_ids),
    )
