import unittest

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.deals import deal_index, load_deals
from dealmind.outcomes import DealOutcome, save_deal_outcome, verify_learning_loop
from dealmind.retrieval import CurrentDeal
from dealmind.seed import seed_historical_deals

BANK = "test-learning-bank"


class TestLearningLoop(unittest.TestCase):
    def setUp(self):
        self.deals = load_deals()
        self.index = deal_index(self.deals)
        self.client = FakeHindsight()
        seed_historical_deals(self.client, BANK, self.deals)

    def test_save_deal_outcome_won(self):
        outcome = DealOutcome(
            id="D-017",
            customer="Titan Cold Chain",
            industry="Logistics",
            product="Enterprise Platform",
            value=175000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="FreightIQ offered a 25% discount.",
            stakeholder_concern="Logistics director was worried about integration with dispatch.",
            pricing_discussion="Rep refused discount and offered custom TMS connector build.",
            approach="Live demo on customer's own freight data and free TMS connector.",
            outcome="Won",
            outcome_reason="Customer verified 2x faster query speed on their live data and connector sealed the deal.",
            date="2026-06-15",
        )
        res = save_deal_outcome(self.client, BANK, outcome, index=self.index)
        self.assertTrue(res["success"])
        self.assertEqual(res["deal_id"], "D-017")
        self.assertIn("D-017", self.client.docs)
        self.assertIn("D-017", self.index)
        self.assertIn("Titan Cold Chain", self.client.docs["D-017"]["content"])
        self.assertIn("Won", self.client.docs["D-017"]["content"])

    def test_save_deal_outcome_stalled(self):
        outcome = DealOutcome(
            id="D-018",
            customer="Zenith Freight",
            industry="Logistics",
            product="Enterprise Platform",
            value=110000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="Uncertainty about software ROI in Q4.",
            stakeholder_concern="CFO paused all new software evaluation.",
            pricing_discussion="Buyer asked for price freeze until Q1.",
            approach="Agreed to price freeze but failed to establish executive champion.",
            outcome="Stalled",
            outcome_reason="Deal delayed into following fiscal year due to lack of economic buyer sponsorship.",
            date="2026-07-20",
        )
        res = save_deal_outcome(self.client, BANK, outcome, index=self.index)
        self.assertEqual(res["outcome"], "Stalled")
        self.assertIn("Stalled", self.client.docs["D-018"]["content"])

    def test_complete_memory_learning_loop_for_future_deals(self):
        """Test the end-to-end memory-learning loop:
        1. Deal A outcome is recorded and saved to Hindsight.
        2. Future Deal B (facing the same competitor & objection) is submitted.
        3. Deal A is recalled by Hindsight and influences Deal B's intelligence report.
        """
        # Step 1: Record outcome for Deal A
        deal_a_outcome = DealOutcome(
            id="D-099",
            customer="Vanguard Freight Logistics",
            industry="Logistics",
            product="Enterprise Platform",
            value=180000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="FreightIQ quoted 20% lower price.",
            stakeholder_concern="Operations fears disruption during peak season.",
            pricing_discussion="Offered 3-year TCO comparison instead of discount.",
            approach="TCO comparison plus executive sponsor meeting with CEO.",
            outcome="Won",
            outcome_reason="TCO proved FreightIQ add-ons made it more expensive; executive meeting won the deal.",
            date="2026-08-10",
        )

        # Step 2: Future Deal B facing similar FreightIQ challenge
        future_deal_b = CurrentDeal(
            customer="Pacific Haulers Group",
            industry="Logistics",
            product="Enterprise Platform",
            value=165000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="Buyer claims FreightIQ quote is 20% lower.",
            stakeholder_concern="Operations wants fast go-live.",
            pricing_discussion="Buyer wants a discount to match FreightIQ.",
        )

        # Step 3: Run verify_learning_loop
        verification = verify_learning_loop(
            client=self.client,
            bank_id=BANK,
            recorded_outcome=deal_a_outcome,
            future_deal=future_deal_b,
            index=self.index,
        )

        # Assertions:
        self.assertTrue(verification["recalled_in_future_deal"], "Future deal must recall newly saved Deal A!")
        self.assertIn("D-099", verification["recalled_evidence_ids"])
        
        report = verification["intelligence_report"]
        # Confirm that D-099 appears in the evidence
        evidence_ids = [ev.deal_id for ev in report.retrieval.evidence]
        self.assertIn("D-099", evidence_ids)

        # Confirm that D-099 is cited in the evidence-based recommendations
        all_citations = " ".join(
            c for rec in report.recommendations for c in rec.historical_evidence
        )
        self.assertTrue(
            "D-099" in all_citations or "Vanguard" in all_citations,
            f"Expected D-099 or Vanguard in citations, got: {all_citations}",
        )


if __name__ == "__main__":
    unittest.main()
