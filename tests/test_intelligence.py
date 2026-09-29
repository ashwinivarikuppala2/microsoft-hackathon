import unittest

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.deals import deal_index, load_deals
from dealmind.intelligence import (
    analyze_deal_risk,
    detect_competitor_patterns,
    detect_objection_patterns,
    generate_recommendations,
    run_deal_intelligence,
)
from dealmind.retrieval import CurrentDeal
from dealmind.seed import seed_historical_deals

BANK = "test-intel-bank"


class TestIntelligence(unittest.TestCase):
    def setUp(self):
        self.deals = load_deals()
        self.index = deal_index(self.deals)
        self.client = FakeHindsight()
        seed_historical_deals(self.client, BANK, self.deals)

    def logistics_freightiq_deal(self):
        return CurrentDeal(
            customer="Acme Freight Systems",
            industry="Logistics",
            product="Enterprise Platform",
            value=150000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="FreightIQ is quoting 20% lower for their cloud license.",
            stakeholder_concern="VP of Operations is concerned about go-live disruption.",
            pricing_discussion="Buyer wants a 15% discount to match FreightIQ.",
        )

    def healthcare_compliance_deal(self):
        return CurrentDeal(
            customer="Ascension Health Alliance",
            industry="Healthcare",
            product="Enterprise Platform",
            value=230000,
            stage="Security Review",
            competitor="Corvex",
            objection="No evidence of HIPAA compliance and audit readiness available.",
            stakeholder_concern="CISO is worried about patient record exposure.",
            pricing_discussion="Fixed quote presented; no discount requested.",
        )

    def test_run_deal_intelligence_pipeline(self):
        deal = self.logistics_freightiq_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        self.assertIsNotNone(report.retrieval)
        self.assertTrue(len(report.retrieval.memories) > 0)
        self.assertTrue(len(report.retrieval.evidence) > 0)
        self.assertTrue(len(report.objection_patterns) > 0)
        self.assertTrue(len(report.competitor_patterns) > 0)
        self.assertIsNotNone(report.risk_analysis)
        self.assertEqual(len(report.recommendations), 4)

    def test_objection_patterns_detection(self):
        deal = self.logistics_freightiq_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        patterns = report.objection_patterns
        # Primary category for price objection
        self.assertEqual(patterns[0].category, "Price & Commercial Terms")
        self.assertGreaterEqual(patterns[0].similar_deals_count, 1)
        self.assertTrue(patterns[0].winning_approaches or patterns[0].pitfalls_and_traps)

    def test_competitor_patterns_detection(self):
        deal = self.logistics_freightiq_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        patterns = report.competitor_patterns
        # Competitor FreightIQ should be prioritized first
        freightiq_pat = next((p for p in patterns if "FreightIQ" in p.competitor_name), None)
        self.assertIsNotNone(freightiq_pat)
        self.assertGreater(freightiq_pat.matchups_count, 0)
        self.assertIn("FreightIQ", freightiq_pat.playbook)

    def test_deal_risk_analysis_high_risk_on_discount_trap(self):
        deal = self.logistics_freightiq_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        risk = report.risk_analysis
        self.assertIn(risk.level, ("MEDIUM", "HIGH"))
        self.assertGreaterEqual(risk.score, 35)
        # Verify discounting trap is identified
        trap_factor = next((rf for rf in risk.risk_factors if "Discount" in rf.title), None)
        self.assertIsNotNone(trap_factor)
        self.assertIn("D-001", trap_factor.evidence_citation)

    def test_evidence_based_recommendations_have_citations(self):
        deal = self.logistics_freightiq_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        recs = report.recommendations
        self.assertEqual(len(recs), 4)
        types = [r.action_type for r in recs]
        self.assertIn("Primary Strategy", types)
        self.assertIn("Pitfall to Avoid", types)
        self.assertIn("Stakeholder Alignment", types)
        self.assertIn("Pricing & Negotiation", types)

        # Ensure all recommendations carry historical evidence citations
        for r in recs:
            self.assertTrue(len(r.historical_evidence) > 0, f"{r.action_type} missing evidence")
            self.assertTrue(r.why_it_works, f"{r.action_type} missing why_it_works")

    def test_healthcare_deal_identifies_compliance_patterns(self):
        deal = self.healthcare_compliance_deal()
        report = run_deal_intelligence(self.client, BANK, deal, self.index)
        self.assertTrue(any(p.category == "Security, Privacy & Compliance" for p in report.objection_patterns))
        # Corvex competitor pattern
        corvex_pat = next((p for p in report.competitor_patterns if "Corvex" in p.competitor_name), None)
        self.assertIsNotNone(corvex_pat)


if __name__ == "__main__":
    unittest.main()
