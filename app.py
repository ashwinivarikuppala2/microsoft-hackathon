"""DealMind - Hindsight-powered deal intelligence & learning loop.

Current Deal
→ Customer Objection
→ Hindsight Memories
→ Historical Evidence
→ Recommendation
→ Record Outcome
→ Learning Loop
"""

from __future__ import annotations

import streamlit as st

from dealmind.chat import chat_with_memory
from dealmind.deals import deal_index, load_deals, normalize_outcome, option_values
from dealmind.engine import (
    OUTCOMES as ENGINE_OUTCOMES,
    TACTICS,
    analyze,
    experience_metadata,
    experience_text,
    make_lesson,
)
from dealmind.intelligence import run_deal_intelligence
from dealmind.memory import (
    ConfigError,
    MemoryFacade,
    get_client,
    load_settings,
    run_connection_test,
)
from dealmind.outcomes import DealOutcome, save_deal_outcome, verify_learning_loop
from dealmind.retrieval import STAGES, CurrentDeal
from dealmind.scenarios import DEAL_A, DEAL_B, QUESTION, SEED_MEMORIES
from dealmind.seed import seed_historical_deals
from dealmind.ui_helpers import (
    cold_start_note,
    evidence_relevance,
    flow_markdown,
    guided_steps,
    record_relevance,
    split_citations,
    stage_title,
)

st.set_page_config(page_title="DealMind", page_icon="🧠", layout="wide")

OUTCOME_COLOR = {"Won": "green", "Lost": "red", "Stalled": "orange", "No Decision": "orange"}
RISK_COLOR = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}
OUTCOME_ICON = {"WON": "🟢", "LOST": "🔴", "STALLED": "🟡"}
SIGNAL_ICON = {"supports": "✅ supports", "cautions": "⚠️ cautions", "context": "ℹ️ context"}
DEALS_SCENARIOS = {1: DEAL_A, 2: DEAL_B}

# Initialize session state stores
if "deals" not in st.session_state:
    st.session_state["deals"] = load_deals()
if "index" not in st.session_state:
    st.session_state["index"] = deal_index(st.session_state["deals"])
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "current_deal" not in st.session_state:
    st.session_state["current_deal"] = CurrentDeal(
        customer="Acme Freight Systems",
        industry="Logistics",
        product="Enterprise Platform",
        value=150000,
        stage="Negotiation",
        competitor="FreightIQ",
        objection="FreightIQ is quoting 20% lower for their cloud license.",
        stakeholder_concern="VP of Operations is concerned about go-live disruption during peak shipping.",
        pricing_discussion="Procurement requested an immediate 15% discount to match FreightIQ.",
    )

# Stage 4 Guided Demo state initialization
if "stage4_mem" not in st.session_state:
    facade = MemoryFacade()
    facade.reset(SEED_MEMORIES)
    st.session_state["stage4_mem"] = facade
    st.session_state["stage4_scene"] = 1
    st.session_state["stage4_results"] = {}
    st.session_state["stage4_saved"] = {}

deals = st.session_state["deals"]
index = st.session_state["index"]
mem_facade: MemoryFacade = st.session_state["stage4_mem"]


@st.cache_resource
def _client():
    settings = load_settings()
    return get_client(settings), settings


# --- Configuration ---------------------------------------------------------
try:
    client, settings = _client()
    config_ok = True
except ConfigError as e:
    st.error(str(e))
    config_ok = False

# --- Top Header ------------------------------------------------------------
st.title("🧠 DealMind")
st.markdown("**Hindsight-Powered Deal Intelligence**")
st.markdown(flow_markdown())

# --- Sidebar: memory setup, diagnostics, presets --------------------------
with st.sidebar:
    st.header("Hindsight Memory")
    st.write(f"**Active Backend:** `{mem_facade.backend}`")
    if config_ok:
        st.write(f"**Memory Bank:** `{settings.bank_id}`")
        st.write(f"**Endpoint:** `{settings.base_url}`")
        st.write(f"**API Key:** {'✅ Configured' if settings.api_key else '⚠️ Local Fallback'}")
    if mem_facade.notice:
        st.caption(f"ℹ️ {mem_facade.notice}")

    st.markdown("---")
    st.markdown("### 🎬 Guided Demo Progress")
    demo_steps = guided_steps(
        st.session_state["stage4_results"],
        st.session_state["stage4_saved"],
        st.session_state["stage4_scene"],
    )
    for i, (label, done) in enumerate(demo_steps, 1):
        st.markdown(f"{'✅' if done else '⬜'} **{i}.** {label}")
    _cold_note = cold_start_note(st.session_state["stage4_results"])
    if _cold_note and not (demo_steps[3][1] and demo_steps[4][1]):
        st.caption(f"ℹ️ {_cold_note}")

    if st.button("↺ Restart Demo (Clear Memory)", use_container_width=True):
        mem_facade.reset(SEED_MEMORIES)
        st.session_state["stage4_scene"] = 1
        st.session_state["stage4_results"] = {}
        st.session_state["stage4_saved"] = {}
        st.rerun()

    st.markdown("---")
    st.markdown("### 📚 16 Historical Deals Bank")
    st.write(f"**Indexed Deals:** {len(index)} historical records")
    if st.button("Load historical deals into Hindsight", disabled=not config_ok, use_container_width=True):
        bar = st.progress(0.0, text="Retaining deals...")
        report = seed_historical_deals(
            client,
            settings.bank_id,
            deals,
            on_progress=lambda n, total, name: bar.progress(n / total, text=f"Retained {name}"),
        )
        bar.empty()
        if report.ok:
            st.success(
                f"Retained {len(report.retained)} deals in Hindsight. Memories are now searchable."
            )
        else:
            st.error(f"Retained {len(report.retained)}, failed {len(report.failed)}.")
            for deal_id, err in report.failed.items():
                st.write(f"- {deal_id}: {err}")

    with st.expander("Connection Test"):
        st.caption("Retains and recalls a synthetic test memory to verify bank connectivity.")
        if st.button("Run retain → recall test", disabled=not config_ok):
            with st.spinner("Testing..."):
                try:
                    report = run_connection_test()
                    st.write("\n".join(f"- {s}" for s in report["steps"]))
                    if report.get("success"):
                        st.success("Test passed!")
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")

    st.markdown("---")
    st.subheader("Quick Deal Presets")
    if st.button("🚚 FreightIQ Price Battle", use_container_width=True):
        st.session_state["current_deal"] = CurrentDeal(
            customer="Acme Freight Systems",
            industry="Logistics",
            product="Enterprise Platform",
            value=150000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="FreightIQ is quoting 20% lower for their cloud license.",
            stakeholder_concern="VP of Operations is concerned about go-live disruption during peak shipping.",
            pricing_discussion="Procurement requested an immediate 15% discount to match FreightIQ.",
        )
        st.session_state.pop("report", None)
        st.rerun()

    if st.button("🏥 Healthcare HIPAA Security", use_container_width=True):
        st.session_state["current_deal"] = CurrentDeal(
            customer="Ascension Health Alliance",
            industry="Healthcare",
            product="Enterprise Platform",
            value=230000,
            stage="Security Review",
            competitor="Corvex",
            objection="No evidence of HIPAA compliance and audit readiness available.",
            stakeholder_concern="CISO is worried about patient record exposure during the migration.",
            pricing_discussion="Fixed quote presented; no discount requested yet pending CISO approval.",
        )
        st.session_state.pop("report", None)
        st.rerun()

    if st.button("🏢 Financial Optima Adoption Fear", use_container_width=True):
        st.session_state["current_deal"] = CurrentDeal(
            customer="Heritage Credit Union",
            industry="Financial Services",
            product="Analytics Add-on",
            value=85000,
            stage="Proposal",
            competitor="Optima Cloud",
            objection="Implementation looks too complex and Optima claims a 30-day go-live.",
            stakeholder_concern="Branch operations manager fears staff change fatigue with no internal data team.",
            pricing_discussion="Buyer asked for 15% discount to offset expected onboarding difficulty.",
        )
        st.session_state.pop("report", None)
        st.rerun()


# --- Main Tabs -------------------------------------------------------------
tab_demo, tab_intel, tab_outcome, tab_loop, tab_chat = st.tabs([
    "🎬 Guided 9-Step Demo (Northwind → Contoso)",
    "🎯 Deep Deal Intelligence & Playbook",
    "📝 Record Outcome (Won / Lost / Stalled)",
    "🔄 Verify Learning Loop",
    "💬 DealMind Chat",
])


# ===========================================================================
# TAB 1: GUIDED 9-STEP DEMO (STAGE 4 HACKATHON PITCH)
# ===========================================================================
with tab_demo:
    scene = st.session_state["stage4_scene"]
    stage4_deal = DEALS_SCENARIOS[scene]

    if scene == 1:
        st.info("💡 **Scene 1: Cold Start.** DealMind has almost no relevant memory. Ask it about the pricing objection.")
    else:
        st.info("💡 **Scene 2: Future Similar Deal.** DealMind now has the outcome from Scene 1 in Hindsight memory.")

    # ① Current Deal
    with st.container(border=True):
        st.subheader(f"{stage_title(0)}: {stage4_deal.company}")
        dc = st.columns(4)
        dc[0].metric("Value", f"${stage4_deal.value:,}")
        dc[1].metric("Stage", stage4_deal.stage)
        dc[2].metric("Buyer", stage4_deal.role)
        dc[3].metric("Competitor", stage4_deal.competitor)
        st.caption(f"{stage4_deal.industry} · {stage4_deal.size}")

    # ② Customer Objection
    with st.container(border=True):
        st.subheader(stage_title(1))
        st.markdown(f"**Objection type:** {stage4_deal.objection}")
        st.markdown(f"> 💬 *“{stage4_deal.customer_said}”*  \n> — the customer ({stage4_deal.role}, {stage4_deal.company})")

    query_val = st.text_input("Ask DealMind", value=QUESTION, key=f"s4_query_{scene}")
    if st.button("Ask DealMind", type="primary", key=f"s4_ask_{scene}", disabled=scene in st.session_state["stage4_saved"]):
        mems = mem_facade.recall(query_val, stage4_deal)
        st.session_state["stage4_results"][scene] = {"query": query_val, "memories": mems}
        st.rerun()

    res = st.session_state["stage4_results"].get(scene)
    if res:
        analysis = analyze(stage4_deal, res["memories"])
        rec = analysis.recommendation

        # ③ Hindsight Memories
        st.subheader(stage_title(2))
        st.caption("Hindsight memories recalled for this question.")
        used_ids = {r["exp"].memory_id for r in analysis.similar}
        if not res["memories"]:
            st.info("Nothing recalled. The memory bank is empty.")
        else:
            if not used_ids:
                st.info("Little/no relevant memory: the recalled item(s) below are unrelated to this deal and are ignored.")
            mem_rows = []
            new_ids = {DEAL_A.deal_id} if scene == 2 else set()
            for m in res["memories"]:
                md = m.metadata
                mem_rows.append({
                    "Memory": m.id,
                    "Deal": md.get("company", "(context)"),
                    "Objection": md.get("objection", ""),
                    "Tactic": TACTICS.get(md.get("tactic", ""), {}).get("label", ""),
                    "Outcome": f"{OUTCOME_ICON.get(md.get('outcome', ''), '')} {md.get('outcome', '')}".strip(),
                    "Relevance": m.relevance,
                    "Used?": "✅ used" if m.id in used_ids else "— ignored (not similar)",
                    "New": "🆕" if m.id in new_ids or md.get("deal_id") in new_ids else "",
                })
            st.dataframe(
                mem_rows,
                hide_index=True,
                use_container_width=True,
                column_config={"Relevance": st.column_config.ProgressColumn("Relevance", min_value=0.0, max_value=1.0, format="%.2f")},
            )
            with st.expander("Raw Memory Text"):
                for m in res["memories"]:
                    st.markdown(f"**{m.id}** · `{m.source}`")
                    st.write(m.text)

        # (derived from the recalled memories above)
        # 2. Similar Deals and Patterns
        col_sim, col_pat = st.columns(2)
        with col_sim:
            st.subheader("🔍 Similar deals")
            if not analysis.similar:
                st.info("No similar deals in memory yet.")
            for r in analysis.similar:
                e = r["exp"]
                with st.container(border=True):
                    st.markdown(f"**{e.company}** · {OUTCOME_ICON[e.outcome]} {e.outcome} · similarity **{r['sim']:.2f}**")
                    st.caption(f"Tactic: {TACTICS[e.tactic]['label']} · matched on: {', '.join(r['matched'])}")

        with col_pat:
            st.subheader("📈 Patterns")
            for p in analysis.patterns:
                st.markdown(f"- {p}")
            if analysis.avoid:
                st.markdown("**Deprioritised by history:** " + ", ".join(f"~~{r['label']}~~" for r in analysis.avoid))

        # ④ Historical Evidence, then why it is relevant (real recalled deals only)
        st.subheader(stage_title(3))
        if not analysis.evidence:
            st.info("No historical evidence supports a specific tactic yet. This is why confidence is very low.")
        else:
            ev_df = [{
                "Memory": e["memory_id"],
                "Deal": e["company"],
                "Tactic": e["tactic"],
                "Outcome": f"{OUTCOME_ICON[e['outcome']]} {e['outcome']}",
                "Similarity": e["similarity"],
                "Effect on recommendation": SIGNAL_ICON[e["signal"]],
                "Lesson": e["lesson"],
            } for e in analysis.evidence]
            st.dataframe(
                ev_df,
                hide_index=True,
                use_container_width=True,
                column_config={"Similarity": st.column_config.ProgressColumn("Similarity", min_value=0.0, max_value=1.0, format="%.2f")},
            )
        st.markdown("#### Why This Evidence Is Relevant")
        if not analysis.evidence:
            st.caption("Nothing to explain: no recalled deal was similar enough to this one.")
        for e in analysis.evidence:
            with st.container(border=True):
                st.markdown(f"**{e['company']}** · {OUTCOME_ICON[e['outcome']]} {e['outcome']} · {e['tactic']}")
                for reason in evidence_relevance(e, rec["label"] if rec.get("key") else None):
                    st.markdown(f"- {reason}")

        # ⑤ Recommendation (+ risk)
        st.subheader(stage_title(4))
        col_rec, col_risk = st.columns([3, 2])
        with col_rec:
            with st.container(border=True):
                st.markdown("#### 🎯 Recommendation")
                st.caption(
                    f"Based on the {len(analysis.evidence)} piece(s) of historical evidence above."
                    if analysis.evidence
                    else "No historical evidence behind this yet: generic playbook guidance."
                )
                tag = ":orange[Playbook default]" if analysis.mode == "playbook" else ":green[Evidence-based]"
                st.markdown(f"### {rec['label']}  \n{tag} · confidence **{rec['confidence_label']}** ({rec['confidence']:.0%})")
                st.write(rec["why"])
                for step in rec["track"]:
                    st.markdown(f"1. {step}")

        with col_risk:
            with st.container(border=True):
                st.subheader("⚠️ Risk")
                r_color = {"Low": "green", "Medium": "orange", "High": "red"}[analysis.risk["level"]]
                st.markdown(f"### :{r_color}[{analysis.risk['level']}] ({analysis.risk['score']:.0%})")
                for reason in analysis.risk["reasons"]:
                    st.markdown(f"- {reason}")

        st.divider()

        # ⑥ Record Outcome
        st.subheader(stage_title(5))
        if scene in st.session_state["stage4_saved"]:
            sv = st.session_state["stage4_saved"][scene]
            st.success(
                f"Recorded {OUTCOME_ICON[sv['outcome']]} **{sv['outcome']}** for {stage4_deal.company} "
                f"using *{TACTICS[sv['tactic']]['label']}* and saved to memory ({mem_facade.backend})."
            )
        else:
            tactics_keys = list(TACTICS)
            default_tactic = analysis.recommendation.get("key") or "discount"
            with st.form(f"stage4_outcome_{scene}"):
                st.caption("What did the rep actually do, and how did the deal end?")
                form_tactic = st.selectbox(
                    "Tactic used",
                    tactics_keys,
                    index=tactics_keys.index(default_tactic),
                    format_func=lambda k: TACTICS[k]["label"],
                )
                form_outcome = st.radio(
                    "Outcome",
                    ENGINE_OUTCOMES,
                    horizontal=True,
                    index=ENGINE_OUTCOMES.index("LOST" if scene == 1 else "WON"),
                    format_func=lambda o: f"{OUTCOME_ICON[o]} {o}",
                )
                form_note = st.text_input("Optional note", placeholder="e.g. CFO went quiet after the discount")
                saved_btn = st.form_submit_button("💾 Save outcome to Hindsight", type="primary")

            if saved_btn:
                lesson_text = make_lesson(stage4_deal, form_tactic, form_outcome, form_note)
                before_stat = {r["key"]: r for r in analysis.tactic_stats}[form_tactic]
                rec_before = analysis.recommendation

                mem_facade.retain(
                    experience_text(stage4_deal, form_tactic, form_outcome, lesson_text),
                    experience_metadata(stage4_deal, form_tactic, form_outcome, lesson_text),
                    stage4_deal.deal_id,
                )
                refreshed_mems = mem_facade.recall(st.session_state["stage4_results"][scene]["query"], stage4_deal)
                after_analysis = analyze(stage4_deal, refreshed_mems)
                after_stat = {r["key"]: r for r in after_analysis.tactic_stats}[form_tactic]

                st.session_state["stage4_saved"][scene] = {
                    "tactic": form_tactic,
                    "outcome": form_outcome,
                    "lesson": lesson_text,
                    "score_before": before_stat["score"],
                    "score_after": after_stat["score"],
                    "rec_before": rec_before,
                    "rec_after": after_analysis.recommendation,
                }
                st.rerun()

        # ⑦ Learning Loop
        st.subheader(stage_title(6))
        if scene in st.session_state["stage4_saved"]:
            sv = st.session_state["stage4_saved"][scene]
            # Display Learning Metrics
            st.subheader("📚 Learning from the new outcome")
            with st.container(border=True):
                st.markdown(f"**Stored lesson:** {sv['lesson']}")
                lc = st.columns(3)
                lc[0].metric(
                    f"Score: {TACTICS[sv['tactic']]['label'][:26]}",
                    f"{sv['score_after']:.2f}",
                    f"{sv['score_after'] - sv['score_before']:+.2f}",
                )
                lc[1].metric(
                    "Confidence",
                    f"{sv['rec_after']['confidence']:.0%}",
                    f"{sv['rec_after']['confidence'] - sv['rec_before']['confidence']:+.0%}",
                )
                lc[2].metric("Recommendation now", sv["rec_after"]["label"][:30])

            if scene == 1:
                if st.button("➡️ Create a future similar deal", type="primary"):
                    st.session_state["stage4_scene"] = 2
                    st.rerun()

        # 5. Counterfactual Comparison in Scene 2
        if scene == 2 and 1 in st.session_state["stage4_saved"]:
            st.subheader("🔁 What the new experience changed")
            prev_deal_id = DEAL_A.deal_id
            without_exp = analyze(stage4_deal, res["memories"], exclude_deal_ids={prev_deal_id})
            s1 = st.session_state["stage4_saved"][1]
            with st.container(border=True):
                st.markdown(
                    f"Memory from **{DEAL_A.company}** ({OUTCOME_ICON[s1['outcome']]} {s1['outcome']} with "
                    f"*{TACTICS[s1['tactic']]['label']}*) was recalled for **{stage4_deal.company}**."
                )
                cf1, cf2 = st.columns(2)
                with cf1:
                    st.markdown("**Without that memory**")
                    st.markdown(
                        f"{without_exp.recommendation['label']}  \nconfidence {without_exp.recommendation['confidence']:.0%} · "
                        f"risk {without_exp.risk['level']}  \n*{without_exp.recommendation['why']}*"
                    )
                with cf2:
                    st.markdown("**With that memory**")
                    st.markdown(
                        f"{analysis.recommendation['label']}  \nconfidence {analysis.recommendation['confidence']:.0%} · "
                        f"risk {analysis.risk['level']}  \n*{analysis.recommendation['why']}*"
                    )
                changed = (
                    without_exp.recommendation["label"] != analysis.recommendation["label"]
                    or without_exp.recommendation["confidence"] != analysis.recommendation["confidence"]
                )
                if changed:
                    st.success("The recommendation changed because of the saved experience.")
                else:
                    st.warning("The saved experience did not change the recommendation.")
        if scene not in st.session_state["stage4_saved"] and not (scene == 2 and 1 in st.session_state["stage4_saved"]):
            st.caption("Save an outcome above and DealMind will show here what it learned from it.")

# ===========================================================================
# TAB 2: DEEP DEAL INTELLIGENCE & PLAYBOOK (16 HISTORICAL DEALS & PATTERNS)
# ===========================================================================
with tab_intel:
    st.subheader("Current deal")
    curr = st.session_state["current_deal"]

    with st.form("current_deal_form"):
        c1, c2, c3 = st.columns(3)
        customer = c1.text_input("Customer", value=curr.customer, placeholder="e.g. Acme Freight Systems")
        ind_options = option_values(deals, "industry")
        ind_idx = ind_options.index(curr.industry) if curr.industry in ind_options else 0
        industry = c2.selectbox("Industry", ind_options, index=ind_idx)
        prod_options = option_values(deals, "product")
        prod_idx = prod_options.index(curr.product) if curr.product in prod_options else 0
        product = c3.selectbox("Product", prod_options, index=prod_idx)

        c4, c5, c6 = st.columns(3)
        value = c4.number_input("Deal value (USD)", min_value=0, value=int(curr.value), step=5000)
        stg_idx = STAGES.index(curr.stage) if curr.stage in STAGES else STAGES.index("Negotiation")
        stage = c5.selectbox("Stage", STAGES, index=stg_idx)
        competitor = c6.text_input("Competitor", value=curr.competitor, placeholder="e.g. FreightIQ")

        objection = st.text_area(
            "Objection",
            value=curr.objection,
            placeholder="What is the buyer or procurement pushing back on?",
            height=70,
        )
        concern = st.text_area(
            "Stakeholder concern",
            value=curr.stakeholder_concern,
            placeholder="Who is worried (CISO, VP Ops, IT lead), and about what?",
            height=70,
        )
        pricing = st.text_area(
            "Pricing discussion",
            value=curr.pricing_discussion,
            placeholder="Discount requests, terms, quotes, concessions...",
            height=70,
        )

        submitted = st.form_submit_button(
            "Find similar deals",
            type="primary",
            disabled=not config_ok,
            use_container_width=True,
        )

    if submitted:
        deal_obj = CurrentDeal(
            customer=customer,
            industry=industry,
            product=product,
            value=value,
            stage=stage,
            competitor=competitor,
            objection=objection,
            stakeholder_concern=concern,
            pricing_discussion=pricing,
        )
        errors = deal_obj.validate()
        if errors:
            for e in errors:
                st.warning(e)
            st.session_state.pop("report", None)
            st.session_state.pop("result", None)
        else:
            st.session_state["current_deal"] = deal_obj
            with st.spinner("Querying Hindsight memory bank & analyzing patterns..."):
                try:
                    report = run_deal_intelligence(client, settings.bank_id, deal_obj, index)
                    st.session_state["report"] = report
                    st.session_state["result"] = report.retrieval
                except Exception as exc:
                    st.session_state.pop("report", None)
                    st.session_state.pop("result", None)
                    st.error(f"Hindsight recall failed: {type(exc).__name__}: {exc}")

    # Display Report
    report = st.session_state.get("report")
    if report:
        st.markdown("---")
        with st.expander("🔍 Query Dispatched to Hindsight"):
            st.code(report.retrieval.query, language="markdown")
            st.caption(f"Retrieved {len(report.retrieval.memories)} memories across {len(report.retrieval.evidence)} historical deals.")

        if not report.retrieval.memories:
            st.info(
                "Hindsight returned no memories. Load the historical deals from the sidebar "
                "(if you haven't), wait a moment for processing, then try again."
            )
        else:
            # 1. Deal Risk Analysis Card
            risk = report.risk_analysis
            if risk:
                st.subheader("2. Deal-Risk Analysis")
                r_color = RISK_COLOR.get(risk.level, "gray")
                with st.container(border=True):
                    rc1, rc2 = st.columns([1, 3])
                    with rc1:
                        st.markdown(f"### :{r_color}[{risk.level} RISK]")
                        st.metric("Risk Score", f"{risk.score}/100")
                    with rc2:
                        st.markdown(f"**Risk Summary:** {risk.summary}")
                        if risk.risk_factors:
                            st.markdown("**Identified Risk Factors:**")
                            for rf in risk.risk_factors:
                                st.markdown(f"- 🔴 **{rf.title}** ({rf.severity}): {rf.rationale}  \n  *{rf.evidence_citation}*")
                        if risk.mitigating_factors:
                            st.markdown("**Protective Factors:**")
                            for mf in risk.mitigating_factors:
                                st.markdown(f"- 🟢 {mf}")

            # 2. Identified Patterns (Objection & Competitor)
            st.subheader("3. Identified Patterns from Recalled Evidence")
            pat_col1, pat_col2 = st.columns(2)

            with pat_col1:
                st.markdown("#### 🛡️ Objection Patterns")
                for obj_pat in report.objection_patterns:
                    with st.container(border=True):
                        st.markdown(f"**{obj_pat.category}** ({obj_pat.similar_deals_count} past deals)")
                        st.caption(f"Win Rate: {obj_pat.win_rate:.0%} ({obj_pat.won_count} Won, {obj_pat.lost_count} Lost, {obj_pat.stalled_count} Stalled)")
                        st.write(obj_pat.description)
                        if obj_pat.winning_approaches:
                            st.markdown("✅ **What Succeeded in Past Deals:**")
                            for wa in obj_pat.winning_approaches:
                                st.markdown(f"- {wa}")
                        if obj_pat.pitfalls_and_traps:
                            st.markdown("⚠️ **Fatal Pitfalls in Past Deals:**")
                            for pt in obj_pat.pitfalls_and_traps:
                                st.markdown(f"- {pt}")

            with pat_col2:
                st.markdown("#### ⚔️ Competitor Patterns")
                for comp_pat in report.competitor_patterns:
                    with st.container(border=True):
                        st.markdown(f"**{comp_pat.competitor_name}** ({comp_pat.matchups_count} recalled deals)")
                        st.caption(f"Head-to-Head Win Rate: {comp_pat.win_rate:.0%} ({comp_pat.won_count} Won, {comp_pat.lost_count} Lost, {comp_pat.stalled_count} Stalled)")
                        st.markdown(f"**Competitor Playbook:** {comp_pat.playbook}")
                        if comp_pat.winning_counters:
                            st.markdown("✅ **Proven Counter-Strategies:**")
                            for wc in comp_pat.winning_counters:
                                st.markdown(f"- {wc}")
                        if comp_pat.vulnerabilities:
                            st.markdown("⚠️ **Past Loss Reasons Against Them:**")
                            for v in comp_pat.vulnerabilities:
                                st.markdown(f"- {v}")

            # 3. Evidence-Based Recommendations
            st.subheader("4. Evidence-Based Recommendations")
            st.caption("Tactical actions derived strictly from the current deal signals and recalled Hindsight memories:")
            records_by_id = {ev.record["id"]: ev.record for ev in report.retrieval.evidence if ev.record}
            for rec_item in report.recommendations:
                # Only citations that name a deal Hindsight actually recalled count as evidence.
                real_cites, generic_cites = split_citations(rec_item.historical_evidence, records_by_id)
                with st.container(border=True):
                    icon = "🎯" if "Primary" in rec_item.action_type else "⚠️" if "Avoid" in rec_item.action_type else "🤝" if "Stakeholder" in rec_item.action_type else "💰"
                    st.markdown("##### 🎯 Recommendation")
                    st.markdown(f"### {icon} {rec_item.action_type}: {rec_item.headline}")
                    st.markdown(rec_item.detailed_guidance)
                    if rec_item.why_it_works:
                        st.markdown(f"**Why this works:** {rec_item.why_it_works}")

                    st.divider()
                    st.markdown("##### 📚 Historical Evidence")
                    if real_cites:
                        for cite_text, _record in real_cites:
                            st.markdown(f"- {cite_text}")
                    else:
                        st.caption("No recalled historical deal backs this recommendation; it is generic playbook guidance.")

                    st.markdown("##### 🔗 Why This Evidence Is Relevant")
                    if real_cites:
                        for _cite_text, record in real_cites:
                            st.markdown(f"**{record['customer']}** ({record['id']}, {normalize_outcome(record['outcome'])})")
                            for reason in record_relevance(st.session_state["current_deal"], record):
                                st.markdown(f"- {reason}")
                    else:
                        st.caption("Nothing to explain: no historical deal is cited here.")

            # 4. Hindsight Memory Evidence (Transparency)
            st.subheader("5. Hindsight Memory Evidence & Citations")
            ev_left, ev_right = st.columns(2)
            with ev_left:
                st.subheader(f"Recalled memories ({len(report.retrieval.memories)})")
                for m in report.retrieval.memories:
                    with st.container(border=True):
                        st.write(m.text)
                        tags = [t for t in (m.type, m.metadata.get("deal_id") or m.document_id) if t]
                        if tags:
                            st.caption(" · ".join(tags))

            with ev_right:
                st.subheader(f"Historical evidence ({len(report.retrieval.evidence)} deals)")
                outcomes_list = [ev.record["outcome"] for ev in report.retrieval.evidence if ev.record]
                if outcomes_list:
                    st.write(
                        f"Of the {len(outcomes_list)} past deals recalled: "
                        f"**{outcomes_list.count('Won')} won**, {outcomes_list.count('Lost')} lost, "
                        f"{outcomes_list.count('Stalled') + outcomes_list.count('No Decision')} stalled."
                    )
                for ev in report.retrieval.evidence:
                    r = ev.record
                    with st.container(border=True):
                        if r:
                            norm_o = normalize_outcome(r.get("outcome", ""))
                            color = OUTCOME_COLOR.get(norm_o, "gray")
                            st.markdown(
                                f"**{r['customer']}** · {r['industry']} · {r['product']} · "
                                f"${r['value']:,} · {r['date']}  \n:{color}[**{norm_o.upper()}**] "
                                f"({ev.deal_id}, stage: {r['stage']})"
                            )
                            st.markdown(
                                f"- **Competitor:** {r['competitor']}\n"
                                f"- **Objection:** {r['objection']}\n"
                                f"- **Stakeholder concern:** {r['stakeholder_concern']}\n"
                                f"- **Pricing discussion:** {r['pricing_discussion']}\n"
                                f"- **Approach used:** {r['approach']}\n"
                                f"- **Why it {norm_o.lower()}:** {r['outcome_reason']}"
                            )
                        else:
                            st.markdown(f"**Deal ID:** {ev.deal_id}")
                        with st.expander(f"Recalled facts for this deal ({len(ev.memories)})"):
                            for m in ev.memories:
                                st.write(f"- {m.text}")


# ===========================================================================
# TAB 3: RECORD CUSTOM DEAL OUTCOME (WON / LOST / STALLED)
# ===========================================================================
with tab_outcome:
    st.subheader("Record Deal Outcome & Retain into Hindsight")
    st.markdown(
        "Closing a deal? Record whether it was **WON**, **LOST**, or **STALLED**, along with the actual "
        "approach used and outcome reason. Saving will immediately retain the experience into Hindsight memory, "
        "enabling future deals to learn from this precedent."
    )

    curr = st.session_state["current_deal"]

    with st.form("outcome_recording_form"):
        oc1, oc2, oc3 = st.columns(3)
        deal_id = oc1.text_input("Deal ID", value=f"D-{len(index) + 1:03d}")
        out_customer = oc2.text_input("Customer Name", value=curr.customer)
        out_outcome = oc3.selectbox("Deal Outcome", ["Won", "Lost", "Stalled"], index=0)

        oc4, oc5, oc6 = st.columns(3)
        out_industry = oc4.selectbox("Industry", option_values(deals, "industry"), index=option_values(deals, "industry").index(curr.industry) if curr.industry in option_values(deals, "industry") else 0)
        out_product = oc5.selectbox("Product", option_values(deals, "product"), index=option_values(deals, "product").index(curr.product) if curr.product in option_values(deals, "product") else 0)
        out_value = oc6.number_input("Final Value (USD)", min_value=0, value=int(curr.value), step=5000)

        oc7, oc8, oc9 = st.columns(3)
        out_stage = oc7.selectbox("Final Stage", STAGES, index=STAGES.index(curr.stage) if curr.stage in STAGES else 0)
        out_comp = oc8.text_input("Competitor", value=curr.competitor)
        out_date = oc9.date_input("Closing Date")

        st.markdown("##### 🗣️ Customer side: what the customer said")
        out_objection = st.text_area(
            "Customer's Final Objection",
            value=curr.objection,
            help="The last objection the CUSTOMER raised before the deal ended.",
            height=65,
        )
        out_concern = st.text_area(
            "Customer Stakeholder Concern",
            value=curr.stakeholder_concern,
            help="A concern raised by someone on the CUSTOMER's side (e.g. their CISO, VP Ops or procurement lead).",
            height=65,
        )
        st.markdown("##### 🧑‍💼 Salesperson side: what your team did")
        out_approach = st.text_area(
            "Sales Approach Used",
            value="Presented 3-year TCO model comparing add-on fees and engaged executive sponsor.",
            placeholder="What strategy or tactic did the sales rep actually execute?",
            help="What YOUR sales team did in response to the customer.",
            height=70,
        )
        st.markdown("##### 🏁 Result")
        out_pricing = st.text_area("Final Pricing Terms", value=curr.pricing_discussion, height=65)
        out_reason = st.text_area(
            "Outcome Reason (Why did it win, lose, or stall?)",
            value="TCO model proved competitor was 15% more expensive over 3 years; executive meeting resolved viability concerns.",
            placeholder="Explain specifically why the customer decided to buy, go elsewhere, or pause.",
            height=70,
        )

        save_submitted = st.form_submit_button(
            "💾 Save Outcome to Hindsight Memory",
            type="primary",
            disabled=not config_ok,
            use_container_width=True,
        )

    if save_submitted:
        try:
            outcome_obj = DealOutcome(
                id=deal_id.strip(),
                customer=out_customer.strip(),
                industry=out_industry,
                product=out_product,
                value=out_value,
                stage=out_stage,
                competitor=out_comp.strip(),
                objection=out_objection.strip(),
                stakeholder_concern=out_concern.strip(),
                pricing_discussion=out_pricing.strip(),
                approach=out_approach.strip(),
                outcome=out_outcome,
                outcome_reason=out_reason.strip(),
                date=out_date.strftime("%Y-%m-%d"),
            )
            with st.spinner("Retaining outcome into Hindsight memory bank..."):
                res = save_deal_outcome(client, settings.bank_id, outcome_obj, index=st.session_state["index"])
                st.session_state["deals"].append(res["record"])
                st.session_state["last_saved_outcome"] = res

            st.success(f"✅ Deal **{deal_id}** ({out_customer} - {out_outcome}) successfully saved to Hindsight!")
            with st.expander("View Retained Hindsight Memory Document"):
                st.code(res["memory_text"], language="markdown")
                st.caption(f"Document ID: {res['document_id']} · Bank: {settings.bank_id}")
            st.info("💡 You can now verify that future deals recall this newly stored memory in the 'Verify Learning Loop' tab.")
        except Exception as exc:
            st.error(f"Failed to save outcome: {type(exc).__name__}: {exc}")


# ===========================================================================
# TAB 4: VERIFY LEARNING LOOP
# ===========================================================================
with tab_loop:
    st.subheader("🔄 Demonstrate the Complete Memory-Learning Loop")
    st.markdown(
        "This interactive test proves that DealMind learns over time:  \n"
        "1. **Record & Retain**: Save an outcome for Deal A into Hindsight.  \n"
        "2. **Query Future Deal**: Submit Deal B with similar competitor and objection.  \n"
        "3. **Hindsight Recall**: Verify that Hindsight retrieves Deal A from memory.  \n"
        "4. **Grounded Playbook**: Deal B's recommendations immediately incorporate Deal A's outcome."
    )

    lc1, lc2 = st.columns(2)
    with lc1:
        st.markdown("#### Step 1: Newly Completed Deal A")
        test_deal_id = st.text_input("Demo Deal ID", value="D-099")
        test_customer = st.text_input("Demo Customer", value="Vanguard Freight Logistics")
        test_outcome = st.selectbox("Demo Outcome", ["Won", "Lost", "Stalled"], index=0, key="demo_outcome")
        test_comp = st.text_input("Demo Competitor", value="FreightIQ", key="demo_comp")
        test_obj = st.text_input("Demo Objection", value="FreightIQ is cheaper by 20%", key="demo_obj")
        test_app = st.text_input("Demo Approach", value="TCO model showing hidden integration fees + reference call", key="demo_app")
        test_reas = st.text_input("Demo Reason", value="Customer realized FreightIQ add-ons made it more expensive; signed list price", key="demo_reas")

    with lc2:
        st.markdown("#### Step 2: Future Deal B (Subsequent Evaluation)")
        fut_cust = st.text_input("Future Customer", value="Pacific Fleet Transport")
        fut_ind = st.selectbox("Future Industry", option_values(deals, "industry"), index=option_values(deals, "industry").index("Logistics") if "Logistics" in option_values(deals, "industry") else 0, key="fut_ind")
        fut_prod = st.selectbox("Future Product", option_values(deals, "product"), index=option_values(deals, "product").index("Enterprise Platform") if "Enterprise Platform" in option_values(deals, "product") else 0, key="fut_prod")
        fut_comp = st.text_input("Future Competitor", value="FreightIQ", key="fut_comp")
        fut_obj = st.text_input("Future Objection", value="Buyer claims FreightIQ quote is 20% lower", key="fut_obj")

    if st.button("🚀 Run End-to-End Learning Loop Test", type="primary", disabled=not config_ok, use_container_width=True):
        with st.spinner("Executing end-to-end memory retention and future deal recall..."):
            try:
                demo_outcome_obj = DealOutcome(
                    id=test_deal_id,
                    customer=test_customer,
                    industry="Logistics",
                    product="Enterprise Platform",
                    value=160000,
                    stage="Negotiation",
                    competitor=test_comp,
                    objection=test_obj,
                    stakeholder_concern="Operations fears disruption",
                    pricing_discussion="Buyer asked for discount",
                    approach=test_app,
                    outcome=test_outcome,
                    outcome_reason=test_reas,
                )
                fut_deal_obj = CurrentDeal(
                    customer=fut_cust,
                    industry=fut_ind,
                    product=fut_prod,
                    value=155000,
                    stage="Negotiation",
                    competitor=fut_comp,
                    objection=fut_obj,
                    stakeholder_concern="Wants fast go-live",
                    pricing_discussion="Buyer pushing to match FreightIQ",
                )

                loop_report = verify_learning_loop(
                    client=client,
                    bank_id=settings.bank_id,
                    recorded_outcome=demo_outcome_obj,
                    future_deal=fut_deal_obj,
                    index=st.session_state["index"],
                )
                st.session_state["loop_report"] = loop_report

            except Exception as exc:
                st.error(f"Learning loop failed: {type(exc).__name__}: {exc}")

    loop_report = st.session_state.get("loop_report")
    if loop_report:
        st.markdown("---")
        st.subheader("Learning Loop Test Results")
        if loop_report["recalled_in_future_deal"]:
            st.success(
                f"🎉 **Learning Loop Confirmed!**  \n"
                f"The newly saved deal **{loop_report['saved_deal_id']} ({loop_report['saved_customer']})** was "
                f"successfully recalled from Hindsight memory when evaluating future deal **{loop_report['future_customer']}**!"
            )
        else:
            st.warning(
                f"Saved deal **{loop_report['saved_deal_id']}** was retained, but was not among the top recall results. "
                "Hindsight memory may need a few moments to finish asynchronous fact extraction."
            )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Saved Deal Retained:** `{loop_report['saved_deal_id']}` ({loop_report['saved_customer']} - {loop_report['saved_outcome']})")
            st.markdown(f"**Total Memories Recalled in Future Deal:** {loop_report['total_recalled_memories']}")
            st.markdown(f"**Evidence Deal IDs Recalled:** {', '.join(loop_report['recalled_evidence_ids'])}")

        with col_b:
            rep = loop_report["intelligence_report"]
            st.markdown(f"**Future Deal Risk Level:** :{RISK_COLOR.get(rep.risk_analysis.level, 'gray')}[{rep.risk_analysis.level}]")
            st.markdown(f"**Primary Action Recommended:** {rep.recommendations[0].headline}")


# ===========================================================================
# TAB 5: NATURAL-LANGUAGE CHAT
# ===========================================================================
with tab_chat:
    st.subheader("💬 DealMind Assistant Chat")
    st.caption("Ask questions about the current deal or historical deal memories. Answers are grounded in Hindsight recall.")

    # Quick prompt buttons
    st.markdown("**Quick Prompts:**")
    qc1, qc2, qc3 = st.columns(3)
    if qc1.button("What is our best move against FreightIQ?", use_container_width=True):
        st.session_state["pending_chat_prompt"] = "What is our best move against FreightIQ when they undercut on price?"
    if qc2.button("Why did Harborline Freight lose?", use_container_width=True):
        st.session_state["pending_chat_prompt"] = "Why did Harborline Freight lose, and what should the rep have done differently?"
    if qc3.button("How should we handle CISO HIPAA concerns?", use_container_width=True):
        st.session_state["pending_chat_prompt"] = "How should we handle CISO security and HIPAA compliance concerns in healthcare deals?"

    # Display chat history
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("query_sent"):
                with st.expander(f"🧠 Hindsight Recall Details ({len(msg.get('memories', []))} memories recalled)"):
                    st.caption(f"**Query Sent:** `{msg['query_sent']}`")
                    for m in msg.get("memories", []):
                        st.markdown(f"- {m.text}")

    # Handle pending prompt or chat input
    user_prompt = st.chat_input("Ask about deals, competitors, objections, or playbook strategies...")
    if not user_prompt and "pending_chat_prompt" in st.session_state:
        user_prompt = st.session_state.pop("pending_chat_prompt")

    if user_prompt:
        st.session_state["chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching Hindsight memory bank..."):
                try:
                    resp = chat_with_memory(
                        client=client,
                        bank_id=settings.bank_id,
                        user_message=user_prompt,
                        current_deal=st.session_state.get("current_deal"),
                        index=index,
                        llm_api_key=settings.llm_api_key,
                    )
                    st.markdown(resp.answer)
                    with st.expander(f"🧠 Hindsight Recall Details ({len(resp.recalled_memories)} memories recalled)"):
                        st.caption(f"**Query Sent:** `{resp.query_sent}`")
                        for m in resp.recalled_memories:
                            st.markdown(f"- {m.text}")

                    st.session_state["chat_history"].append({
                        "role": "assistant",
                        "content": resp.answer,
                        "query_sent": resp.query_sent,
                        "memories": resp.recalled_memories,
                    })
                except Exception as exc:
                    st.error(f"Chat failed: {type(exc).__name__}: {exc}")
