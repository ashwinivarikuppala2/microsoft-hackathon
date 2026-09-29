"""Tests for the UI-only changes: labels, evidence sections, guided progress, flow.

Uses the same recording Streamlit stand-in as test_app_smoke, so these run
without Streamlit installed. `st.rerun()` is a no-op in the stub, so state
changes made by a click show up in the *next* run (same as the real app).
"""
import os
import runpy
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.engine import experience_metadata, experience_text, make_lesson  # noqa: E402
from dealmind.memory import MemoryFacade  # noqa: E402
from dealmind.retrieval import CurrentDeal  # noqa: E402
from dealmind.scenarios import DEAL_A, DEAL_B, QUESTION, SEED_MEMORIES  # noqa: E402
from dealmind.seed import seed_historical_deals  # noqa: E402
from dealmind.ui_helpers import (  # noqa: E402
    FLOW_STAGES,
    evidence_relevance,
    flow_markdown,
    guided_steps,
    record_relevance,
    split_citations,
)
from tests.test_app_smoke import FORM, ROOT, StreamlitStub  # noqa: E402

SAVE_LABEL = "💾 Save outcome to Hindsight"


class DrivenStub(StreamlitStub):
    """Stub whose buttons fire only when listed in `click`, and which records field labels."""

    def __init__(self, click=(), inputs=None, submit=()):
        super().__init__(inputs or {})
        self.click, self.submit = set(click), set(submit)
        self.labels: list[str] = []
        self.column_config = SimpleNamespace(ProgressColumn=lambda *a, **k: None)

    def button(self, label, *a, **kw):
        return label in self.click

    def form_submit_button(self, label, *a, **kw):
        return label in self.submit

    def radio(self, label, options, index=0, **kw):
        return options[index]

    def text_input(self, label, **kw):
        self.labels.append(label)
        return self.inputs.get(label, kw.get("value", ""))

    def text_area(self, label, **kw):
        self.labels.append(label)
        return self.inputs.get(label, kw.get("value", ""))


def drive(state, click=(), submit=(), inputs=None, client=None):
    stub = DrivenStub(click, inputs, submit)
    stub.session_state = state
    env = {"HINDSIGHT_API_KEY": "test-key", "HINDSIGHT_BANK_ID": "ui"}
    with mock.patch.dict(sys.modules, {"streamlit": stub}), \
         mock.patch.dict(os.environ, env, clear=False), \
         mock.patch("dealmind.memory.get_client", return_value=client or FakeHindsight()), \
         mock.patch("dealmind.memory.load_dotenv"):
        runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    return stub


def progress_marks(stub):
    """The 9 sidebar lines as (checked?, number)."""
    return [(line.startswith("✅"), line.split("**")[1]) for line in stub.out if line[:1] in "✅⬜" and "**" in line]


def checked(stub):
    return [num for done, num in progress_marks(stub) if done]


class TestGuidedStepsLogic(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEALMIND_DATA_DIR": tempfile.mkdtemp()})
        patcher.start()
        self.addCleanup(patcher.stop)  # restore env afterwards so other tests are unaffected
        os.environ.pop("HINDSIGHT_BASE_URL", None)
        self.mem = MemoryFacade()
        self.mem.reset(SEED_MEMORIES)

    def flags(self, results, saved, scene):
        return [done for _, done in guided_steps(results, saved, scene)]

    def test_nothing_checked_before_any_action(self):
        self.assertEqual(self.flags({}, {}, 1), [False] * 9)

    def test_cold_start_ask_checks_only_steps_1_to_3(self):
        results = {1: {"query": QUESTION, "memories": self.mem.recall(QUESTION, DEAL_A)}}
        self.assertEqual(self.flags(results, {}, 1), [True, True, True] + [False] * 6)

    def test_full_journey_checks_each_step_only_when_it_happens(self):
        results = {1: {"query": QUESTION, "memories": self.mem.recall(QUESTION, DEAL_A)}}
        lesson = make_lesson(DEAL_A, "discount", "LOST")
        self.mem.retain(experience_text(DEAL_A, "discount", "LOST", lesson),
                        experience_metadata(DEAL_A, "discount", "LOST", lesson), DEAL_A.deal_id)
        saved = {1: {"tactic": "discount", "outcome": "LOST"}}
        # saved, but still in scene 1: 6 and 7 done, 8 and 9 not
        self.assertEqual(self.flags(results, saved, 1), [True, True, True, False, False, True, True, False, False])
        # moved to scene 2 but has not asked yet
        self.assertEqual(self.flags(results, saved, 2), [True, True, True, False, False, True, True, True, False])
        # scene-2 recall uses the saved deal
        results[2] = {"query": QUESTION, "memories": self.mem.recall(QUESTION, DEAL_B)}
        self.assertEqual(self.flags(results, saved, 2), [True] * 9)

    def test_step_9_needs_the_saved_experience_to_be_used(self):
        # scene 2 asked WITHOUT the scene-1 outcome ever saved to memory: not "new experience used"
        results = {1: {"query": QUESTION, "memories": self.mem.recall(QUESTION, DEAL_A)},
                   2: {"query": QUESTION, "memories": self.mem.recall(QUESTION, DEAL_B)}}
        self.assertFalse(self.flags(results, {}, 2)[8])


class TestEvidenceHelpers(unittest.TestCase):
    RECORD = {"id": "D-001", "customer": "Old Co", "industry": "Logistics", "product": "Enterprise Platform",
              "stage": "Negotiation", "competitor": "FreightIQ", "objection": "FreightIQ is cheaper by 20%",
              "stakeholder_concern": "Operations fears go-live disruption", "outcome": "Won"}

    def test_generic_playbook_text_is_not_evidence(self):
        real, generic = split_citations(
            ["Deal D-001 (Old Co, Won): TCO model", "Deal D-999 (Ghost, Won): never retrieved",
             "General Playbook from Hindsight memory bank: ROI"],
            {"D-001": self.RECORD})
        self.assertEqual([r[1]["id"] for r in real], ["D-001"])
        self.assertEqual(len(generic), 2)  # unretrieved deal id and playbook text both excluded

    def test_relevance_lists_only_real_matches(self):
        cur = CurrentDeal(industry="Healthcare", product="Enterprise Platform", stage="Negotiation",
                          competitor="Corvex", objection="No HIPAA evidence", stakeholder_concern="")
        text = " ".join(record_relevance(cur, self.RECORD))
        self.assertIn("Same product", text)
        self.assertIn("Same deal stage", text)
        self.assertNotIn("Same competitor", text)
        self.assertNotIn("Same industry", text)

    def test_relevance_falls_back_honestly_when_nothing_matches(self):
        cur = CurrentDeal(industry="Retail", product="Team Plan", stage="Discovery", competitor="X", objection="")
        reasons = record_relevance(cur, self.RECORD)
        self.assertEqual(len(reasons), 1)
        self.assertIn("no exact match", reasons[0])

    def test_engine_evidence_reasons_use_match_data(self):
        ev = {"outcome": "LOST", "tactic": "Discount up front", "signal": "supports",
              "matched": ["competitor", "industry"], "similarity": 0.35}
        reasons = evidence_relevance(ev, "Phased rollout / flexible terms")
        self.assertIn("same competitor", reasons[0])
        self.assertIn("same industry", reasons[0])
        self.assertIn("argues against", reasons[1])


class TestFlow(unittest.TestCase):
    def test_flow_has_the_seven_requested_stages_in_order(self):
        self.assertEqual(FLOW_STAGES, ["Current Deal", "Customer Objection", "Hindsight Memories",
                                       "Historical Evidence", "Recommendation", "Record Outcome", "Learning Loop"])
        md = flow_markdown()
        positions = [md.index(s) for s in FLOW_STAGES]
        self.assertEqual(positions, sorted(positions))


class TestAppUi(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DEALMIND_DATA_DIR": tempfile.mkdtemp()})
        patcher.start()
        self.addCleanup(patcher.stop)  # restore env afterwards so other tests are unaffected
        os.environ.pop("HINDSIGHT_BASE_URL", None)

    def test_record_outcome_labels_and_sections(self):
        stub = drive({})
        for label in ("Customer's Final Objection", "Customer Stakeholder Concern", "Sales Approach Used"):
            self.assertIn(label, stub.labels)
        self.assertNotIn("Final Objection", stub.labels)
        self.assertNotIn("Stakeholder Concern", stub.labels)
        text = "\n".join(stub.out)
        self.assertIn("Customer side", text)
        self.assertIn("Salesperson side", text)

    def test_flow_strip_and_deal_sections_render(self):
        text = "\n".join(drive({}).out)
        for stage in FLOW_STAGES:
            self.assertIn(stage, text)

    def test_nothing_is_checked_on_page_load(self):
        stub = drive({})
        marks = progress_marks(stub)
        self.assertEqual(len(marks), 9)
        self.assertEqual(checked(stub), [])

    def test_progress_follows_the_real_actions(self):
        state = {}
        drive(state)                                              # load
        drive(state, click={"Ask DealMind"}, inputs={"Ask DealMind": QUESTION})   # ask (state applies next run)
        self.assertEqual(checked(drive(state, inputs={"Ask DealMind": QUESTION})), ["1.", "2.", "3."])

        drive(state, submit={SAVE_LABEL}, inputs={"Ask DealMind": QUESTION})      # save outcome
        self.assertEqual(checked(drive(state, inputs={"Ask DealMind": QUESTION})),
                         ["1.", "2.", "3.", "6.", "7."])

        drive(state, click={"➡️ Create a future similar deal"}, inputs={"Ask DealMind": QUESTION})
        self.assertEqual(checked(drive(state, inputs={"Ask DealMind": QUESTION})),
                         ["1.", "2.", "3.", "6.", "7.", "8."])

        drive(state, click={"Ask DealMind"}, inputs={"Ask DealMind": QUESTION})   # scene-2 ask
        final = drive(state, inputs={"Ask DealMind": QUESTION})
        self.assertEqual(len(checked(final)), 9)

        drive(state, click={"↺ Restart Demo (Clear Memory)"})
        self.assertEqual(checked(drive(state)), [])

    def test_scene1_shows_three_evidence_sections_without_inventing_evidence(self):
        state = {}
        drive(state, click={"Ask DealMind"}, inputs={"Ask DealMind": QUESTION})
        text = "\n".join(drive(state, inputs={"Ask DealMind": QUESTION}).out)
        self.assertIn("Historical Evidence", text)
        self.assertIn("Why This Evidence Is Relevant", text)
        self.assertIn("Recommendation", text)
        self.assertIn("No historical evidence supports a specific tactic yet", text)
        self.assertIn("Playbook default", text)

    def test_scene2_explains_relevance_from_recalled_deal(self):
        state = {}
        q = {"Ask DealMind": QUESTION}
        drive(state, click={"Ask DealMind"}, inputs=q)
        drive(state, submit={SAVE_LABEL}, inputs=q)
        drive(state, click={"➡️ Create a future similar deal"}, inputs=q)
        text = "\n".join(drive(state, click={"Ask DealMind"}, inputs=q).out)
        self.assertIn("Northwind Logistics", text)                 # the saved deal is the evidence
        self.assertIn("Matched on:", text)
        self.assertIn("same competitor", text)

    def test_tab2_recommendations_separate_the_three_parts(self):
        client = FakeHindsight()
        seed_historical_deals(client, "ui")
        stub = drive({}, submit={"Find similar deals"}, inputs=FORM, client=client)
        text = "\n".join(stub.out)
        self.assertIn("Recommendation", text)
        self.assertIn("Historical Evidence", text)
        self.assertIn("Why This Evidence Is Relevant", text)
        self.assertIn("Evidence-Based Recommendations", text)


if __name__ == "__main__":
    unittest.main()
