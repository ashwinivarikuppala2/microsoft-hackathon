import unittest
from datetime import datetime

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.deals import (  # noqa: E402
    REQUIRED_FIELDS, deal_index, deal_metadata, deal_timestamp, deal_to_memory_text,
    load_deals, validate_deals,
)
from dealmind.memory import recall_memories  # noqa: E402
from dealmind.retrieval import CurrentDeal, find_similar_deals, resolve_deal_id  # noqa: E402
from dealmind.seed import seed_historical_deals  # noqa: E402

BANK = "test-bank"


class TestDeals(unittest.TestCase):
    def setUp(self):
        self.deals = load_deals()

    def test_count_in_range(self):
        self.assertTrue(10 <= len(self.deals) <= 20, len(self.deals))

    def test_all_required_fields_present(self):
        for d in self.deals:
            for f in REQUIRED_FIELDS:
                self.assertTrue(d.get(f), f"{d['id']} missing {f}")

    def test_variety_of_outcomes_industries_competitors(self):
        self.assertEqual({d["outcome"] for d in self.deals}, {"Won", "Lost", "No Decision"})
        self.assertGreaterEqual(len({d["industry"] for d in self.deals}), 5)
        self.assertGreaterEqual(len({d["competitor"] for d in self.deals}), 4)

    def test_dates_are_past_and_valid(self):
        for d in self.deals:
            self.assertLess(datetime.strptime(d["date"], "%Y-%m-%d"), datetime(2026, 9, 28))

    def test_memory_text_names_customer_and_id_in_every_fact(self):
        for d in self.deals:
            text = deal_to_memory_text(d)
            # the 8 template statements each carry the deal id (7 also carry "(customer)")
            self.assertEqual(text.count(d["id"]), 8, d["id"])
            self.assertGreaterEqual(text.count(d["customer"]), 8, d["id"])
            for key in ("objection", "stakeholder_concern", "pricing_discussion", "approach",
                        "outcome_reason", "competitor", "product", "industry", "stage"):
                self.assertIn(d[key], text)

    def test_metadata_is_string_only(self):
        for d in self.deals:
            self.assertTrue(all(isinstance(v, str) for v in deal_metadata(d).values()))
        self.assertIsNotNone(deal_timestamp(self.deals[0]).tzinfo)

    def test_validation_rejects_bad_data(self):
        bad = [dict(self.deals[0], outcome="Maybe")]
        with self.assertRaises(ValueError):
            validate_deals(bad)
        with self.assertRaises(ValueError):
            validate_deals([self.deals[0], self.deals[0]])
        with self.assertRaises(ValueError):
            validate_deals([dict(self.deals[0], objection="")])


class TestSeeding(unittest.TestCase):
    def test_seeds_every_deal_via_retain(self):
        client = FakeHindsight()
        report = seed_historical_deals(client, BANK)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.retained), len(load_deals()))
        self.assertEqual(client.calls["retain"], len(report.retained))
        # deal id is used as document id and metadata travels with it
        self.assertEqual(client.docs["D-001"]["metadata"]["deal_id"], "D-001")

    def test_reseeding_is_idempotent(self):
        client = FakeHindsight()
        seed_historical_deals(client, BANK)
        n = len(client.docs)
        seed_historical_deals(client, BANK)
        self.assertEqual(len(client.docs), n)

    def test_failures_are_reported_not_hidden(self):
        client = FakeHindsight()
        client.fail_on = {"D-003"}
        report = seed_historical_deals(client, BANK)
        self.assertFalse(report.ok)
        self.assertIn("D-003", report.failed)
        self.assertNotIn("D-003", report.retained)
        self.assertEqual(len(report.retained), len(load_deals()) - 1)

    def test_progress_callback(self):
        seen = []
        seed_historical_deals(FakeHindsight(), BANK, on_progress=lambda n, t, name: seen.append((n, t)))
        self.assertEqual(seen[-1][0], seen[-1][1])


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.deals = load_deals()
        self.index = deal_index(self.deals)
        self.client = FakeHindsight()
        seed_historical_deals(self.client, BANK, self.deals)

    def logistics_price_deal(self):
        return CurrentDeal(
            customer="Acme Freight", industry="Logistics", product="Enterprise Platform",
            value=150000, stage="Negotiation", competitor="FreightIQ",
            objection="FreightIQ is cheaper than our quote",
            stakeholder_concern="Operations wants a fast go-live",
            pricing_discussion="Buyer wants a discount to match FreightIQ",
        )

    def test_validation(self):
        self.assertEqual(len(CurrentDeal(industry="Retail", product="Team Plan").validate()), 1)
        self.assertEqual(len(CurrentDeal().validate()), 3)
        self.assertEqual(self.logistics_price_deal().validate(), [])

    def test_query_contains_form_fields(self):
        q = self.logistics_price_deal().to_query()
        for s in ("Logistics", "Enterprise Platform", "FreightIQ", "$150,000", "Negotiation", "discount"):
            self.assertIn(s, q)

    def test_retrieval_goes_through_hindsight_recall(self):
        before = self.client.calls["recall"]
        result = find_similar_deals(self.client, BANK, self.logistics_price_deal(), self.index)
        self.assertEqual(self.client.calls["recall"], before + 1)
        self.assertEqual(result.memories and len(result.memories) > 0, True)

    def test_finds_relevant_freightiq_deals(self):
        result = find_similar_deals(self.client, BANK, self.logistics_price_deal(), self.index)
        ids = [e.deal_id for e in result.evidence]
        self.assertTrue({"D-001", "D-006"} & set(ids), ids)
        for ev in result.evidence:
            self.assertIsNotNone(ev.record)
            self.assertTrue(ev.memories)

    def test_empty_bank_returns_empty_not_local_fallback(self):
        empty = FakeHindsight()
        result = find_similar_deals(empty, BANK, self.logistics_price_deal(), self.index)
        self.assertEqual(result.memories, [])
        self.assertEqual(result.evidence, [])

    def test_evidence_groups_by_deal_and_preserves_all_memories(self):
        result = find_similar_deals(self.client, BANK, self.logistics_price_deal(), self.index)
        grouped = sum(len(e.memories) for e in result.evidence) + len(result.unattributed)
        self.assertEqual(grouped, len(result.memories))
        self.assertEqual(len({e.deal_id for e in result.evidence}), len(result.evidence))

    def test_resolve_deal_id_fallbacks(self):
        from dealmind.memory import RecalledMemory as RM
        self.assertEqual(resolve_deal_id(RM("x", metadata={"deal_id": "D-002"}), self.index), "D-002")
        self.assertEqual(resolve_deal_id(RM("x", document_id="D-003"), self.index), "D-003")
        self.assertEqual(resolve_deal_id(RM("In deal D-005 something"), self.index), "D-005")
        self.assertEqual(resolve_deal_id(RM("Northgate Energy signed"), self.index), "D-011")
        self.assertIsNone(resolve_deal_id(RM("unrelated fact"), self.index))

    def test_recall_tolerates_dict_and_list_shapes(self):
        class C:
            def recall(self, bank_id, query):
                return [{"text": "a", "document_id": "D-001", "metadata": None}]
        m = recall_memories(C(), BANK, "q")
        self.assertEqual((m[0].text, m[0].document_id, m[0].metadata), ("a", "D-001", {}))


if __name__ == "__main__":
    unittest.main()
