"""UI-only helpers for app.py. No Streamlit import, no Hindsight calls, no retrieval changes.

Everything here is derived from data the app already holds (recall results, the
analysis of those results, saved outcomes, retrieved historical records). Nothing
is invented: if the data is not there, the helper returns "not done" / "no reasons".
"""
from __future__ import annotations

import re

from .engine import analyze
from .intelligence import OBJECTION_CATEGORIES, _classify_text_category
from .scenarios import DEAL_A, DEAL_B

# The visual flow shown at the top of the page and used to number the guided-demo sections.
FLOW_STAGES = [
    "Current Deal",
    "Customer Objection",
    "Hindsight Memories",
    "Historical Evidence",
    "Recommendation",
    "Record Outcome",
    "Learning Loop",
]
FLOW_NUMBERS = "①②③④⑤⑥⑦"


def flow_markdown() -> str:
    return " → ".join(f"`{n} {s}`" for n, s in zip(FLOW_NUMBERS, FLOW_STAGES))


def stage_title(index: int) -> str:
    """Numbered section title, e.g. stage_title(3) -> '④ Historical Evidence'."""
    return f"{FLOW_NUMBERS[index]} {FLOW_STAGES[index]}"


# --- Guided 9-step progress -------------------------------------------------

STEP_LABELS = [
    "Start with little/no relevant memory",
    "Ask the pricing-objection question",
    "Recalled Hindsight experiences",
    "Historical evidence",
    "Evidence-based recommendation",
    "Record WON / LOST / STALLED",
    "Save outcome to Hindsight",
    "Create a future similar deal",
    "New experience recalled & used",
]


def guided_steps(results: dict, saved: dict, scene: int) -> list[tuple[str, bool]]:
    """(label, done) for each of the 9 guided-demo steps.

    A step is done only when the action it describes has actually happened:
      1 cold start        - scene-1 recall ran and found no similar past deal
      2 ask               - the scene-1 question was submitted
      3 recalled          - that recall returned at least one memory
      4 evidence          - real similar-deal evidence exists (scene 1 or 2)
      5 recommendation    - an evidence-based (not playbook-default) recommendation exists
      6 record outcome    - an outcome was submitted for scene 1
      7 save to Hindsight - that outcome was retained (same button as 6, so they land together)
      8 future deal       - the user moved to scene 2
      9 new exp. used     - scene-2 recall used the deal saved in step 7
    """
    r1, r2 = results.get(1), results.get(2)
    a1 = analyze(DEAL_A, r1["memories"]) if r1 else None
    a2 = analyze(DEAL_B, r2["memories"]) if r2 else None

    analyses = [a for a in (a1, a2) if a is not None]
    used_in_scene2 = bool(a2 and any(r["exp"].deal_id == DEAL_A.deal_id for r in a2.similar))
    flags = [
        a1 is not None and not a1.similar,
        r1 is not None,
        bool(r1 and r1["memories"]),
        any(a.evidence for a in analyses),
        any(a.mode == "evidence" for a in analyses),
        1 in saved,
        1 in saved,
        scene == 2,
        1 in saved and used_in_scene2,
    ]
    return list(zip(STEP_LABELS, flags))


def cold_start_note(results: dict) -> str:
    """Explain why steps 4-5 are still open after a scene-1 recall that found no history."""
    r1 = results.get(1)
    if r1 and not analyze(DEAL_A, r1["memories"]).similar:
        return ("Cold start: no similar past deals were recalled, so there is no historical "
                "evidence or evidence-based recommendation yet.")
    return ""


# --- Evidence relevance -----------------------------------------------------

_CITED_DEAL = re.compile(r"^Deal (D-\d+)\b")

MATCH_LABELS = {
    "objection": "same objection type",
    "industry": "same industry",
    "size": "same company size",
    "role": "same buyer role",
    "competitor": "same competitor",
}


def split_citations(citations: list[str], records_by_id: dict[str, dict]) -> tuple[list[tuple[str, dict]], list[str]]:
    """Separate real citations from generic playbook text.

    A citation is real only if it names a deal id that was actually retrieved
    (present in records_by_id). Anything else (e.g. 'General Playbook ...') is
    returned in the second list and must not be presented as historical evidence.
    """
    real, generic = [], []
    for text in citations:
        m = _CITED_DEAL.match(text)
        if m and m.group(1) in records_by_id:
            real.append((text, records_by_id[m.group(1)]))
        else:
            generic.append(text)
    return real, generic


def _category(text: str) -> str | None:
    if not (text or "").strip():
        return None
    cat = _classify_text_category(text)
    return cat if cat in OBJECTION_CATEGORIES else None  # skip the catch-all fallback


def record_relevance(current, record: dict) -> list[str]:
    """Why a retrieved historical record relates to the current deal.

    Only attributes that genuinely match are listed. If none match, the caller
    is told the deal was recalled by Hindsight semantic search, nothing more.
    """
    reasons = []
    for field, label in (("competitor", "competitor"), ("industry", "industry"),
                         ("product", "product"), ("stage", "deal stage")):
        cur, old = (getattr(current, field, "") or "").strip(), (record.get(field) or "").strip()
        if cur and old and cur.lower() == old.lower():
            reasons.append(f"Same {label}: {old}")
    cur_cat, old_cat = _category(current.objection), _category(record.get("objection", ""))
    if cur_cat and cur_cat == old_cat:
        reasons.append(f"Same kind of objection: {old_cat}")
    cur_cat, old_cat = _category(current.stakeholder_concern), _category(record.get("stakeholder_concern", ""))
    if cur_cat and cur_cat == old_cat:
        reasons.append(f"Similar stakeholder concern theme: {old_cat}")
    if not reasons:
        reasons.append("Recalled by Hindsight as related to this deal's description; no exact match on "
                       "competitor, industry, product, stage or objection theme.")
    return reasons


def evidence_relevance(ev: dict, recommended_label: str | None) -> list[str]:
    """Why one guided-demo evidence row matters, from the engine's own match data."""
    reasons = []
    matched = [MATCH_LABELS[k] for k in ev.get("matched", []) if k in MATCH_LABELS]
    if matched:
        reasons.append(f"Matched on: {', '.join(matched)} (similarity {ev['similarity']:.2f})")
    outcome, tactic = ev["outcome"].title(), ev["tactic"]
    signal = ev["signal"]
    if signal == "supports" and tactic == recommended_label:
        reasons.append(f"{outcome} using the recommended approach, which supports recommending it.")
    elif signal == "supports":
        reasons.append(f"{outcome} when '{tactic}' was used, which argues against leading with it.")
    elif signal == "cautions":
        reasons.append(f"The recommended approach was used here and the deal was {outcome.lower()}: treat with caution.")
    else:
        reasons.append(f"{outcome} using '{tactic}'; noted as context, not a driver of this recommendation.")
    return reasons
