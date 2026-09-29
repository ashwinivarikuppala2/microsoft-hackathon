import unittest

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.chat import chat_with_memory
from dealmind.deals import deal_index, load_deals
from dealmind.retrieval import CurrentDeal
from dealmind.seed import seed_historical_deals

BANK = "test-chat-bank"


class TestChat(unittest.TestCase):
    def setUp(self):
        self.deals = load_deals()
        self.index = deal_index(self.deals)
        self.client = FakeHindsight()
        seed_historical_deals(self.client, BANK, self.deals)

    def test_chat_freightiq_queries_hindsight_and_cites_deals(self):
        deal = CurrentDeal(
            customer="Acme Freight Systems",
            industry="Logistics",
            product="Enterprise Platform",
            value=150000,
            stage="Negotiation",
            competitor="FreightIQ",
            objection="FreightIQ is quoting 20% lower.",
        )
        response = chat_with_memory(
            client=self.client,
            bank_id=BANK,
            user_message="What is our best move against FreightIQ?",
            current_deal=deal,
            index=self.index,
        )
        self.assertTrue(len(response.recalled_memories) > 0)
        self.assertTrue("FreightIQ" in response.query_sent)
        self.assertTrue(len(response.cited_deal_ids) > 0)
        self.assertTrue("recalled facts" in response.answer.lower())

    def test_chat_empty_bank_handles_gracefully(self):
        empty_client = FakeHindsight()
        response = chat_with_memory(
            client=empty_client,
            bank_id=BANK,
            user_message="What happened in logistics deals?",
            index=self.index,
        )
        self.assertEqual(len(response.recalled_memories), 0)
        self.assertIn("found no matching", response.answer)


if __name__ == "__main__":
    unittest.main()
